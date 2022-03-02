import datetime
import inspect
import json
from abc import abstractmethod
from collections import defaultdict
from dataclasses import dataclass
from pydoc import locate

import django
from django.apps import apps
from django.db import connection

registry = defaultdict(list)


@dataclass
class _Channel:

    def __post_init__(self):
        self.callbacks = []

    @classmethod
    def name(cls):
        # TODO: check channel name limits
        module_name = inspect.getmodule(cls).__name__
        name =  f'{module_name}_{cls.__name__}'
        # TODO: pg_notify accepts ., but LISTEN does not.
        # What's the best way to build a channel name?
        name = name.replace('.', '_')
        return name.lower()

    @classmethod
    def get(cls, name):
        for channel_cls, callbacks in registry.items():
            if channel_cls.name() == name:
                return channel_cls, callbacks

    @classmethod
    def register(cls, callback):
        registry[cls].append(callback)

    @classmethod
    @abstractmethod
    def deserialize(cls, payload):
        return

    @classmethod
    def build_from_payload(cls, notification_payload, callbacks):
        deserialized = cls.deserialize(notification_payload)
        channel = cls(**deserialized)
        channel.callbacks.extend(callbacks)
        return channel

    @property
    def signature(self):
        return {k: v for k, v in self.__dict__.items()
                if k in self.__dataclass_fields__}

    def execute_callbacks(self):
        for callback in self.callbacks:
            callback(**self.signature)


@dataclass
class Channel(_Channel):

    @classmethod
    def deserialize(cls, payload):
        payload = json.loads(payload)
        serialized_kwargs = payload['kwargs']
        kwargs = {}
        for kwarg_name, val in serialized_kwargs.items():
            deserialized_val = val
            kwarg_type = cls.__dataclass_fields__[kwarg_name].type
            origin_type = getattr(kwarg_type, '__origin__', kwarg_type)
            if origin_type is dict:
                key_type, val_type = kwarg_type.__args__
                deserialized_val = {
                    cls._deserialize_arg(key, key_type):
                        cls._deserialize_arg(val, val_type)
                    for key, val in val.items()
                }
            elif origin_type in (list, tuple, set):
                element_type, = kwarg_type.__args__
                deserialized_val = origin_type(
                    cls._deserialize_arg(x, element_type) for x in val)
            kwargs[kwarg_name] = cls._deserialize_arg(
                deserialized_val, origin_type)
        return kwargs

    def notify(self):
        serialized = self._serialize()
        with connection.cursor() as cursor:
            name = self.name()
            print(f'Notifying channel {self.name()} with payload {serialized}')
            cursor.execute(f"select pg_notify('{name}', '{serialized}');")
        return serialized

    def _serialize(self):
        serialized_kwargs = {}
        for kwarg, val in self.signature.items():
            serialized_val = val
            kwarg_type = self.__dataclass_fields__[kwarg].type
            origin_type = getattr(kwarg_type, '__origin__', kwarg_type)
            if origin_type is dict:
                serialized_val = {
                    self._date_serial(k): self._date_serial(v) for k, v in val.items()}
            elif origin_type in (list, tuple, set):
                serialized_val = [self._date_serial(x) for x in val]
            serialized_kwargs[kwarg] = serialized_val
        return json.dumps({'kwargs': serialized_kwargs}, default=self._date_serial)

    @staticmethod
    def _date_serial(obj):
        if isinstance(obj, (datetime.datetime, datetime.date)):
            return obj.isoformat()
        return obj

    @classmethod
    def _deserialize_arg(cls, arg, arg_type):
        if arg_type in (datetime.datetime, datetime.date):
            return arg_type.fromisoformat(arg)
        else:
            return arg_type(arg)


class TriggerPayload:
    def __init__(self, payload):
        self._json_payload = json.loads(payload)
        self._model = apps.get_model(
            app_label=self._json_payload['app'],
            model_name=self._json_payload['model'],
        )
        self._old_row_data = self._json_payload['old']
        self._new_row_data = self._json_payload['new']

    @property
    def old(self):
        if self._old_row_data:
            return self._model(**self._old_row_data)

    @property
    def new(self):
        if self._new_row_data:
            return self._model(**self._new_row_data)


@dataclass
class TriggerChannel(_Channel):
    model = NotImplementedError
    old: django.db.models.Model
    new: django.db.models.Model

    @classmethod
    def deserialize(cls, payload):
        trigger_payload = TriggerPayload(payload)
        return {'old': trigger_payload.old, 'new': trigger_payload.new}


def locate_channel(channel):
    if isinstance(channel, str):
        channel = locate(channel)
    if channel is None:
        raise ChannelNotFound()
    return channel


class ChannelNotFound(Exception):
    def __str__(self):
        return 'Channel not found!'
