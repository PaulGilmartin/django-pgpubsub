import hashlib
from abc import abstractmethod
from collections import defaultdict
from dataclasses import dataclass
from decimal import Decimal
import datetime
import inspect
import json
from pydoc import locate
from typing import Any, Callable, Dict, Union, List, Type

from django.apps import apps
from django.core import serializers
from django.core.serializers.json import DjangoJSONEncoder
from django.db import models
from django.db.migrations.recorder import MigrationRecorder


registry = defaultdict(list)


@dataclass
class BaseChannel:
    lock_notifications = False

    def __post_init__(self):
        self.callbacks = []

    @classmethod
    def name(cls):
        module_name = inspect.getmodule(cls).__name__
        return f'{module_name}.{cls.__name__}'

    @classmethod
    def listen_safe_name(cls):
        # Postgres LISTEN protocol accepts channel names
        # which are at most 63 characters long.
        model_hash = hashlib.sha1(
            cls.name().encode()).hexdigest()[:5]
        return f'pgpubsub_{model_hash}'

    @classmethod
    def get(cls, name: str):
        for channel_cls, callbacks in registry.items():
            if channel_cls.listen_safe_name() == name:
                return channel_cls, callbacks

    @classmethod
    def register(cls, callback: Callable):
        registry[cls].append(callback)

    @classmethod
    @abstractmethod
    def deserialize(cls, payload: Union[Dict, str]):
        if isinstance(payload, str):
            payload = json.loads(payload, parse_float=Decimal)
        return payload

    @classmethod
    def build_from_payload(
        cls,
        notification_payload: Union[Dict, str],
        callbacks: List[Callable],
    ):
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
class Channel(BaseChannel):
    @classmethod
    def deserialize(cls, payload: Union[Dict, str]):
        payload = super().deserialize(payload)
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
                (element_type,) = kwarg_type.__args__
                deserialized_val = origin_type(
                    cls._deserialize_arg(x, element_type) for x in val)
            kwargs[kwarg_name] = cls._deserialize_arg(
                deserialized_val, origin_type)
        return kwargs

    def serialize(self):
        serialized_kwargs = {}
        for kwarg, val in self.signature.items():
            serialized_val = val
            kwarg_type = self.__dataclass_fields__[kwarg].type
            origin_type = getattr(kwarg_type, '__origin__', kwarg_type)
            if origin_type is dict:
                serialized_val = {
                    self._date_serial(k): self._date_serial(v)
                    for k, v in val.items()
                }
            elif origin_type in (list, tuple, set):
                serialized_val = [self._date_serial(x) for x in val]
            serialized_kwargs[kwarg] = serialized_val
        return json.dumps(
            {'kwargs': serialized_kwargs},
            default=self._date_serial,
            cls=DjangoJSONEncoder,
        )

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


@dataclass
class TriggerChannel(BaseChannel):

    model = NotImplementedError
    old: models.Model
    new: models.Model

    @classmethod
    def deserialize(cls, payload: Union[Dict, str]):
        payload_dict = super().deserialize(payload)
        old = cls._deserialize_from_state(payload_dict, state='old')
        new = cls._deserialize_from_state(payload_dict, state='new')
        return {'old': old, 'new': new}

    @classmethod
    def _is_up_to_date(cls, app: str, db_version_id: int) -> bool:
        """Check if the db version id from django migrations is the latest for the given app"""
        newer_migration_exists = MigrationRecorder.Migration.objects.filter(
            app=app, id__gt=db_version_id
        ).exists()
        return not newer_migration_exists

    @classmethod
    def _deserialize_from_state(cls, payload: Dict, state: str) -> Any:
        app = payload['app']
        model_name = payload['model']
        model_cls = apps.get_model(
            app_label=payload['app'],
            model_name=payload['model'],
        )
        db_version = payload.get('db_version', None)
        if db_version is None or cls._is_up_to_date(app, db_version):
            model_data = cls._build_model_serializer_data(model_cls, payload[state])

            deserialized_objects = serializers.deserialize(
                'json',
                json.dumps(model_data, cls=DjangoJSONEncoder),
                ignorenonexistent=True,
            )

            obj = next(deserialized_objects, None)
            if obj is not None:
                obj = obj.object
        else:
            if payload[state]:
                try:
                    obj = model_cls.objects.get(pk=payload[state][model_cls._meta.pk.name])
                except model_cls.DoesNotExist:
                    obj = None
            else:
                obj = None

        return obj

    @classmethod
    def _build_model_serializer_data(cls, model_cls: Type[Any], original_state: Dict) -> List[Any]:
        """Reformat serialized data into shape as expected
        by the Django model deserializer.
        """
        fields = {field.name: field for field in model_cls._meta.fields}
        db_fields = {field.db_column: field for field in model_cls._meta.fields}

        new_state = {}
        model_data = []
        if original_state is not None:
            for field in list(original_state):
                # Triggers serialize the notification payload with
                # respect to how the model fields look as columns
                # in the database. We therefore need to take
                # care to map xxx_id named columns to the corresponding
                # xxx model field and also to account for model fields
                # with alternative database column names as declared
                # by the db_column attribute.
                value = original_state.pop(field)
                if field.endswith('_id'):
                    field = field.rsplit('_id')[0]
                if field in fields:
                    new_state[field] = value
                elif field in db_fields:
                    field = db_fields[field].name
                    new_state[field] = value

            model_data.append(
                {
                    'fields': new_state,
                    'id': new_state['id'],
                    'model': f'{model_cls._meta.app_label}.{model_cls.__name__}',
                },
            )
        return model_data


def locate_channel(channel):
    if isinstance(channel, str):
        channel = locate(channel)
    if channel is None:
        raise ChannelNotFound()
    return channel


class ChannelNotFound(Exception):
    def __str__(self):
        return 'Channel not found!'
