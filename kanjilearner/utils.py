from django.utils import timezone
from .models import DictionaryEntry, UserDictionaryEntry  # Adjust the import path if needed
from .constants import EntryType, SRSStage  # Adjust path as needed

def initialize_user_dictionary_entries(user):
    entries = DictionaryEntry.objects.all()
    bulk_entries = []

    now = timezone.now()

    for entry in entries:
        if entry.level == 0:
            # Level 0 entries → burned
            bulk_entries.append(UserDictionaryEntry(
                user=user,
                entry=entry,
                srs_stage=SRSStage.BURNED.value,
                unlocked_at=now,
                next_review_at=None,
                last_reviewed_at=now,
                review_history=[],
            ))
        else:
            # Everything else → locked
            bulk_entries.append(UserDictionaryEntry(
                user=user,
                entry=entry,
                srs_stage=SRSStage.LOCKED.value,
                unlocked_at=None,
                next_review_at=None,
                last_reviewed_at=None,
                review_history=[],
            ))

    UserDictionaryEntry.objects.bulk_create(bulk_entries, ignore_conflicts=True)
