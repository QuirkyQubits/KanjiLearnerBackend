from django.utils import timezone
from .models import DictionaryEntry, UserDictionaryEntry  # Adjust the import path if needed

def initialize_user_dictionary_entries(user):
    entries = DictionaryEntry.objects.all()
    bulk_entries = []

    now = timezone.now()
    for entry in entries:
        # Unlock only level 1 radicals (or customize as needed)
        is_unlocked = entry.level == 1 and entry.type == "RADICAL"
        bulk_entries.append(UserDictionaryEntry(
            user=user,
            entry=entry,
            unlocked=is_unlocked,
            unlocked_at=now if is_unlocked else None,
            srs_stage="L",
            next_review_at=None,
            review_history=[],
        ))

    UserDictionaryEntry.objects.bulk_create(bulk_entries)
