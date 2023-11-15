import os
import dj_database_url

SECRET_KEY = 'django-pgpubsub'
# Install the tests as an app so that we can make test models
INSTALLED_APPS = [
    'django.contrib.auth',
    'django.contrib.contenttypes',
    'pgpubsub',
    'pgpubsub.tests',
    'pgtrigger',
]

# Database url comes from the DATABASE_URL env var
DATABASES = {'default': dj_database_url.config()}
DATABASES['default']['DISABLE_SERVER_SIDE_CURSORS'] = False

DEFAULT_AUTO_FIELD = 'django.db.models.AutoField'

ALLOWED_HOSTS = ['localhost', '127.0.0.1', '0.0.0.0:8000']

PGPUBSUB_ENABLE_PAYLOAD_EXTRAS = os.environ.get('PGPUBSUB_ENABLE_PAYLOAD_EXTRAS', "False") == "True"
