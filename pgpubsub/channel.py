import datetime
import inspect
import json
import select
from abc import abstractmethod

from django.apps import apps
from django.db import connection


class ChannelBase:
    registry = {}

    def __init__(self, callback, name=None):
        self.callback = callback
        self.name = name or self._create_name()

    @classmethod
    def get(cls, channel_name):
        return cls.registry[channel_name]

    @classmethod
    def register(cls, callback, name=None):
        channel = cls(callback, name=name)
        cls.registry[channel.name] = cls(callback, name=name)
        return channel

    @abstractmethod
    def deserialize(self, payload):
        return

    def listen(self):
        cursor = connection.cursor()
        pg_connection = connection.connection
        print('Starting listen')
        cursor.execute('LISTEN {};'.format(self.name))
        print('Listening on channel {}'.format(self.name))
        while True:
            if select.select([pg_connection], [], [], 5) == ([], [], []):
                print('Timeout')
            else:
                pg_connection.poll()
                while pg_connection.notifies:
                    notification = pg_connection.notifies.pop(0)
                    deserialized = self.deserialize(notification.payload)
                    self.callback(**deserialized)

    def _create_name(self):
        # TODO: check channel name limits
        name =  '{}_{}'.format(
            inspect.getmodule(self.callback).__name__,
            self.callback.__name__,
        )
        # TODO: pg_notify accepts ., but LISTEN does not.
        # What's the best way to build a channel name?
        name = name.replace('.', '_')
        return name


class CustomPayloadChannel(ChannelBase):
    def __init__(self, callback, name=None):
        super().__init__(callback, name=name)
        self.signature = self.callback.__annotations__

    def deserialize(self, payload):
        payload = json.loads(payload)
        serialized_kwargs = payload['kwargs']
        kwargs = {}
        for kwarg_name, val in serialized_kwargs.items():
            deserialized_val = val
            kwarg_type = self.signature[kwarg_name]
            origin_type = getattr(kwarg_type, '__origin__', kwarg_type)
            if origin_type is dict:
                key_type, val_type = kwarg_type.__args__
                deserialized_val = {
                    self._deserialize_arg(key, key_type):
                        self._deserialize_arg(val, val_type)
                    for key, val in val.items()
                }
            elif origin_type in (list, tuple, set):
                element_type, = kwarg_type.__args__
                deserialized_val = origin_type(
                    self._deserialize_arg(x, element_type) for x in val)
            kwargs[kwarg_name] = self._deserialize_arg(
                deserialized_val, origin_type)
        return kwargs

    @staticmethod
    def _deserialize_arg(arg, arg_type):
        if arg_type in (datetime.datetime, datetime.date):
            return arg_type.fromisoformat(arg)
        else:
            return arg_type(arg)


class TriggerPayloadChannel(ChannelBase):
    def deserialize(self, payload):
        return {'trigger_payload': TriggerPayload(payload)}


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
