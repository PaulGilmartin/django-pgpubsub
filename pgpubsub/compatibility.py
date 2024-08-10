import os

try:
    if os.getenv('PGPUBSUB_USE_PSYCOPG_V3', 'False') == 'True':
        raise ImportError()

    from psycopg2._psycopg import Notify

    class ConnectionWrapper:
        def __init__(self, conn):
            self.connection = conn

        def poll(self):
            self.connection.poll()

        @property
        def notifies(self):
            return self.connection.notifies

        @notifies.setter
        def notifies(self, value: Notify) -> None:
            self.connection.notifies = value

        def stop(self):
            pass

except ImportError:
    from psycopg import Notify

    class ConnectionWrapper:
        def __init__(self, conn):
            self.connection = conn
            self.notifies = []
            self.connection.add_notify_handler(self._notify_handler)

        def _notify_handler(self, notification):
            self.notifies.append(notification)

        def poll(self):
            self.connection.execute("SELECT 1")

        def stop(self):
            self.connection.remove_notify_handler(self._notify_handler)
