import uuid

import pgtrigger
from django.db import connection
from django.db.transaction import atomic

from pgpubsub.channel import locate_channel
from pgpubsub.models import Notification


@atomic
def notify(channel, **kwargs):
    channel = locate_channel(channel)
    channel = channel(**kwargs)
    serialized = channel.serialize()
    with connection.cursor() as cursor:
        name = channel.name()
        print(f'Notifying channel {name} with payload {serialized}')
        cursor.execute(f"select pg_notify('{name}', '{serialized}');")
        if channel.lock_notifications:
            Notification.objects.create(
                channel=name,
                payload=serialized,
                creation_datetime=channel.creation_datetime,
                uuid=uuid.uuid4(),  # remove once we can remove the field
            )
    return serialized


class Notify(pgtrigger.Trigger):
    """A trigger which notifies a channel"""

    lock_notifications = False

    def get_func(self, model):
        # gen_random_uuid requires postgres 13
        return f'''
            {self._build_payload(model)}
            {self._pre_notify()}
            perform pg_notify('{self.name}', payload);
            RETURN NEW;
        '''

    def get_declare(self, model):
        return [('payload', 'TEXT')]

    def _build_payload(self, model):
        # remove uuid code once we can remove the field
        return  f'''
            {self._define_payload_variables()}
            payload := json_build_object(
                {self._base_payload(model)}
                {self._payload_variables()}
              );
        '''

    def _define_payload_variables(self):
        return ''

    def _base_payload(self, model):
        return f'''
            'app', '{model._meta.app_label}',
            'model', '{model.__name__}',
            'old', row_to_json(OLD),
            'new', row_to_json(NEW)
        '''

    def _payload_variables(self):
        return ''

    def _pre_notify(self):
        return ''


class ProcessOnceNotify(Notify):

    lock_notifications = True

    def get_declare(self, model):
        return super().get_declare(model) + [
            ('creation_datetime', 'timestamptz'),
        ]

    def _define_payload_variables(self):
        # remove uuid code
        return f'''
            creation_datetime := (now() at time zone 'utc');
        '''
    def _base_payload(self, model):
        return super()._base_payload(model) + ','

    def _payload_variables(self):
        return "'pgpubsub_notification_creation_datetime', creation_datetime"

    def _pre_notify(self):
        # remove uuid code
        return f'''
            INSERT INTO pgpubsub_notification
             (channel, payload, uuid, creation_datetime)
            VALUES ('{self.name}', to_json(payload::text),
                    gen_random_uuid(), creation_datetime);
            '''
