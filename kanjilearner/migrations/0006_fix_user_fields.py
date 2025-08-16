from django.db import migrations
import django.contrib.postgres.fields
from django.db import models

class Migration(migrations.Migration):

    dependencies = [
        ('kanjilearner', '0005_alter_userdictionaryentry_srs_stage'),
    ]

    operations = [
        migrations.AlterField(
            model_name='userdictionaryentry',
            name='user_synonyms',
            field=django.contrib.postgres.fields.ArrayField(
                base_field=models.CharField(max_length=100), size=None, blank=True, default=list
            ),
        ),
        migrations.AlterField(
            model_name='userdictionaryentry',
            name='user_sentences',
            field=django.contrib.postgres.fields.ArrayField(
                base_field=models.CharField(max_length=300), size=None, blank=True, default=list
            ),
        ),
    ]
