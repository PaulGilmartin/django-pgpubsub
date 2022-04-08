from typing import Type, Union

import pgtrigger
from django.db import connection
from django.db.models import Model
from django.db.transaction import atomic

from pgpubsub.channel import locate_channel, Channel
from pgpubsub.models import Notification


@atomic
def notify(channel: Union[Type[Channel], str], **kwargs):
    channel_cls = locate_channel(channel)
    channel = channel_cls(**kwargs)
    serialized = channel.serialize()
    with connection.cursor() as cursor:
        name = channel_cls.name()
        print(f'Notifying channel {name} with payload {serialized}')
        cursor.execute(
            f"select pg_notify('{channel_cls.listen_safe_name()}', '{serialized}');")
        if channel_cls.lock_notifications:
            Notification.objects.create(
                channel=name,
                payload=serialized,
            )
    return serialized


class Notify(pgtrigger.Trigger):
    """A trigger which notifies a channel"""

    def get_func(self, model: Type[Model]):
        return f'''
            {self._build_payload(model)}
            {self._pre_notify()}
            perform pg_notify('{self.name}', payload);
            RETURN NEW;
        '''

    def get_declare(self, model: Type[Model]):
        return [('payload', 'TEXT')]

    def _pre_notify(self):
        return ''

    def _build_payload(self, model):
        return  f'''
            payload := json_build_object(
                'app', '{model._meta.app_label}',
                'model', '{model.__name__}',
                'old', row_to_json(OLD),
                'new', row_to_json(NEW)
              );
        '''


class LockableNotify(Notify):

    def _pre_notify(self):
        return f'''
            INSERT INTO pgpubsub_notification (channel, payload)
            VALUES ('{self.name}', to_json(payload::text));
        '''
