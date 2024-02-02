from typing import Type

import pgtrigger
from django.db.models import Model


class Notify(pgtrigger.Trigger):
    """A trigger which notifies a channel"""

    def get_func(self, model: Type[Model]):
        return f'''
            {self._build_payload(model)}
            {self._build_notify_payload()}
            perform pg_notify('{self.name}', notify_payload);
            RETURN NEW;
        '''

    def get_declare(self, model: Type[Model]):
        return [
            ('notify_payload', 'TEXT'),
            ('payload', 'JSONB'),
            ('notification_context_text', 'TEXT'),
        ]

    def _build_notify_payload(self):
        return 'notify_payload := payload;'

    def _build_payload(self, model):
        return f'''
            payload := '{{"app": "{model._meta.app_label}", "model": "{model.__name__}"}}'::jsonb;
            payload := jsonb_insert(payload, '{{old}}', COALESCE(to_jsonb(OLD), 'null'));
            payload := jsonb_insert(payload, '{{new}}', COALESCE(to_jsonb(NEW), 'null'));
            SELECT current_setting('pgpubsub.notification_context', True) INTO notification_context_text;
            IF COALESCE(notification_context_text, '') = '' THEN
                notification_context_text := '{{}}';
            END IF;
            payload := jsonb_insert(payload, '{{context}}', notification_context_text::jsonb);
        '''


class LockableNotify(Notify):
    def _build_notify_payload(self):
        return f'''
            INSERT INTO pgpubsub_notification (channel, payload)
            VALUES ('{self.name}', payload)
            RETURNING id::text INTO notify_payload;
        '''
