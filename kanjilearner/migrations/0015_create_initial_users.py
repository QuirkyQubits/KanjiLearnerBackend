from django.db import migrations
from django.contrib.auth.hashers import make_password

def create_initial_users(apps, schema_editor):
    User = apps.get_model('auth', 'User')

    # Create admin (superuser)
    if not User.objects.filter(username='admin').exists():
        User.objects.create(
            username='admin',
            email='admin@example.com',
            password=make_password('changeme123'),  # replace with a secure password
            is_superuser=True,
            is_staff=True,
        )

    # Create test user (normal account)
    if not User.objects.filter(username='testuser').exists():
        User.objects.create(
            username='testuser',
            email='test@example.com',
            password=make_password('testpass123'),  # replace with your chosen test password
            is_superuser=False,
            is_staff=False,
        )

def remove_initial_users(apps, schema_editor):
    User = apps.get_model('auth', 'User')
    User.objects.filter(username__in=['admin', 'testuser']).delete()

class Migration(migrations.Migration):

    dependencies = [
        ('kanjilearner', '0014_remove_dictionaryentry_unique_literal_entrytype_and_more'),
    ]

    operations = [
        migrations.RunPython(create_initial_users, remove_initial_users),
    ]
