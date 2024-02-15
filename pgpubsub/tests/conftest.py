import pytest
from django.db import connection
from pgpubsub.listen import listen_to_channels

@pytest.fixture()
def pg_connection():
    return listen_to_channels()


@pytest.fixture
def tx_start_time(django_db_setup):
    with connection.cursor() as cursor:
        cursor.execute("SELECT now();")
        return cursor.fetchone()[0]
