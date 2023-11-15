from typing import Type

import pgtrigger
from django.db.models import Model


class Notify(pgtrigger.Trigger):
    """A trigger which notifies a channel"""

    def get_func(self, model: Type[Model]):
        return f'''
            {self._build_payload(model)}
            {self._pre_notify()}
            perform pg_notify('{self.name}', payload::text);
            RETURN NEW;
        '''

    def get_declare(self, model: Type[Model]):
        return [
            ('payload', 'JSONB'),
            ('get_payload_extras_func', 'TEXT'),
            ('extras', 'JSONB')
        ]

    def _pre_notify(self):
        return ''

    def _build_payload(self, model):
        return f'''
            payload := '{{"app": "{model._meta.app_label}", "model": "{model.__name__}"}}'::jsonb;
            payload := jsonb_insert(payload, '{{old}}', COALESCE(to_jsonb(OLD), 'null'));
            payload := jsonb_insert(payload, '{{new}}', COALESCE(to_jsonb(NEW), 'null'));
            SELECT current_setting('pgpubsub.get_payload_extras_func', True)
                INTO get_payload_extras_func;
            IF get_payload_extras_func IS NOT NULL THEN
                EXECUTE 'SELECT ' || quote_ident(get_payload_extras_func) || '()'
                    INTO extras;
                payload := jsonb_insert(payload, '{{extras}}', extras);
            END IF;
        '''


class LockableNotify(Notify):
    def _pre_notify(self):
        return f'''
            INSERT INTO pgpubsub_notification (channel, payload)
            VALUES ('{self.name}', payload);
        '''
