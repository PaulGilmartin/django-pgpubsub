# Generated by Django 3.2.12 on 2022-04-03 07:06

from django.db import migrations, models


class Migration(migrations.Migration):

    initial = True

    dependencies = [
    ]

    operations = [
        migrations.CreateModel(
            name='Notification',
            fields=[
                ('id', models.AutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('creation_datetime', models.DateTimeField(auto_now_add=True)),
                ('channel', models.CharField(db_index=True, max_length=63)),
                ('payload', models.JSONField()),
                ('uuid', models.UUIDField(db_index=True)),
            ],
        ),
    ]
