import datetime
import json

from django.db import connection
import pgtrigger


def notify(channel_name: str, **kwargs):
    payload = _serialize(**kwargs)
    print(payload)
    with connection.cursor() as cursor:
        cursor.execute("select pg_notify('{}', '{}');".format(
            channel_name, payload))


class Notify(pgtrigger.Trigger):
    """A trigger which notifies a channel"""

    def get_func(self, model):
        return f'''
            payload := json_build_object(
                'app', '{model._meta.app_label}',
                'model','{model.__name__}',
                'old',row_to_json(OLD),
                'new',row_to_json(NEW)
              );
            perform pg_notify('{self.name}', payload);
            RETURN NEW;
        '''

    def get_declare(self, model):
        return [('payload', 'TEXT')]


def _serialize(**kwargs):
    serialized_kwargs = {}
    for kwarg, val in kwargs.items():
        serialized_val = val
        if isinstance(val, dict):
            serialized_val = {
                _date_serial(k): _date_serial(v)
                for k, v in val.items()
            }
        elif isinstance(val, (list, tuple, set)):
            serialized_val = [_date_serial(x) for x in val]
        serialized_kwargs[kwarg] = serialized_val
    return json.dumps(
        {'kwargs': serialized_kwargs},
        default=_date_serial,
    )


def _date_serial(obj):
    if isinstance(obj, (datetime.datetime, datetime.date)):
        return obj.isoformat()
    return obj
