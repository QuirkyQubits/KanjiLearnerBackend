from django.db.models.signals import post_save
from django.dispatch import receiver
from django.contrib.auth import get_user_model
from .models import UserDictionaryEntry, DictionaryEntry
from django.utils import timezone
from .utils import initialize_user_dictionary_entries

User = get_user_model()

@receiver(post_save, sender=User)
def create_user_dictionary_entries(sender, instance, created, **kwargs):
    if created:
        initialize_user_dictionary_entries(instance)