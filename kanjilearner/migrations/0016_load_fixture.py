from django.db import migrations
from django.core.management import call_command

def load_fixture(apps, schema_editor):
    try:
        call_command("loaddata", "kanjilearner_data.json")
    except Exception as e:
        print(f"⚠️ Could not load fixture: {e}")

class Migration(migrations.Migration):

    dependencies = [
        ('kanjilearner', '0015_create_initial_users'),
    ]

    operations = [
        migrations.RunPython(load_fixture),
    ]
