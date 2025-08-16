from django.utils import timezone
from .models import DictionaryEntry, UserDictionaryEntry  # Adjust the import path if needed
from .constants import SRSStage  # Adjust path as needed

def initialize_user_dictionary_entries(user):
    entries = DictionaryEntry.objects.prefetch_related("constituents").all()
    bulk_entries = []

    now = timezone.now()

    for entry in entries:
        # Default
        srs_stage = SRSStage.LOCKED.value
        unlocked_at = None

        # Rule 1: Unlock level 1 radicals
        if entry.level == 1 and entry.type == "RADICAL":
            srs_stage = SRSStage.LESSON.value
            unlocked_at = now

        # Rule 2: Unlock level 1 kanji with only level 0 constituents
        elif entry.level == 1 and entry.type == "KANJI":
            constituents = entry.constituents.all()
            if all(c.level < 1 for c in constituents):
                srs_stage = SRSStage.LESSON.value
                unlocked_at = now

        bulk_entries.append(UserDictionaryEntry(
            user=user,
            entry=entry,
            unlocked_at=unlocked_at,
            srs_stage=srs_stage,
            next_review_at=None,
            review_history=[],
        ))

    UserDictionaryEntry.objects.bulk_create(bulk_entries)
