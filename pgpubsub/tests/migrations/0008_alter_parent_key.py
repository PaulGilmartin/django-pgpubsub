# Generated by Django 3.2.12 on 2023-05-19 14:03

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('tests', '0007_child_pgpubsub_89ef9'),
    ]

    operations = [
        migrations.AlterField(
            model_name='parent',
            name='key',
            field=models.AutoField(editable=False, primary_key=True, serialize=False),
        ),
    ]