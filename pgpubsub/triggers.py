from typing import Type

import pgtrigger
from django.db.models import Model


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
