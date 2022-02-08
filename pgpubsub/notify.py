import pgtrigger

from pgpubsub.channel import locate_channel


def notify(channel, **kwargs):
    channel = locate_channel(channel)
    payload = channel(**kwargs).notify()
    return payload


class Notify(pgtrigger.Trigger):
    """A trigger which notifies a channel"""

    def get_func(self, model):
        return f'''
            payload := json_build_object(
                'app', '{model._meta.app_label}',
                'model', '{model.__name__}',
                'old', row_to_json(OLD),
                'new', row_to_json(NEW)
              );
            perform pg_notify('{self.name}', payload);
            RETURN NEW;
        '''

    def get_declare(self, model):
        return [('payload', 'TEXT')]
