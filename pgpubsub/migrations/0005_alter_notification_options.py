# Generated by Django 3.2.22 on 2023-10-20 00:17

from django.db import migrations


class Migration(migrations.Migration):

    dependencies = [
        ('pgpubsub', '0004_notification_pgpubsub_notification_set_db_version'),
    ]

    operations = [
        migrations.AlterModelOptions(
            name='notification',
            options={'ordering': ['created_at']},
        ),
    ]
