import pgtrigger
from django.db import connection
from django.db.transaction import atomic

from pgpubsub.channel import locate_channel
from pgpubsub.models import Notification


# process_once would probably be better just at the channel level
@atomic
def notify(channel, **kwargs):
    channel = locate_channel(channel)
    channel = channel(**kwargs)
    serialized = channel.serialize()
    with connection.cursor() as cursor:
        name = channel.name()
        print(f'Notifying channel {name} with payload {serialized}')
        cursor.execute(f"select pg_notify('{name}', '{serialized}');")
        if channel.process_once:
            Notification.objects.create(
                channel=name,
                payload=serialized,
                uuid=channel.uuid,
            )
    return serialized


class Notify(pgtrigger.Trigger):
    """A trigger which notifies a channel"""

    process_once = False

    def get_func(self, model):
        # gen_random_uuid requires postgres 13
        return f'''
            {self._build_payload(model)}
            {self._pre_notify()}
            perform pg_notify('{self.name}', payload);
            RETURN NEW;
        '''

    def get_declare(self, model):
        return [('payload', 'TEXT'), ('uuid', 'UUID')]

    def _pre_notify(self):
        return ''

    def _build_payload(self, model):
        return  f'''
            uuid := gen_random_uuid();
            payload := json_build_object(
                'app', '{model._meta.app_label}',
                'model', '{model.__name__}',
                'old', row_to_json(OLD),
                'new', row_to_json(NEW),
                'pgpubsub_notification_uuid', uuid,
                'process_once', {self.process_once}
              );
        '''


class ProcessOnceNotify(Notify):

    process_once = True

    def _pre_notify(self):
        return f'''
            INSERT INTO pgpubsub_notification
             (channel, payload, uuid, creation_datetime)
            VALUES ('{self.name}', to_json(payload::text),
                    uuid, (now() at time zone 'utc'));
            '''
