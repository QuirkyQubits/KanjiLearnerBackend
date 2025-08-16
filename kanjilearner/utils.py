from django.utils import timezone
from .models import DictionaryEntry, UserDictionaryEntry  # Adjust the import path if needed

def initialize_user_dictionary_entries(user):
    entries = DictionaryEntry.objects.prefetch_related("constituents").all()
    bulk_entries = []

    now = timezone.now()

    for entry in entries:
        is_unlocked = False

        # Rule 1: Unlock level 1 radicals
        if entry.level == 1 and entry.type == "RADICAL":
            is_unlocked = True

        # Rule 2: Unlock level 1 kanji with no level 1 constituents
        elif entry.level == 1 and entry.type == "KANJI":
            constituents = entry.constituents.all()
            if all(c.level < 1 for c in constituents):
                is_unlocked = True

        bulk_entries.append(UserDictionaryEntry(
            user=user,
            entry=entry,
            unlocked=is_unlocked,
            unlocked_at=now if is_unlocked else None,
            srs_stage="L" if is_unlocked else "INIT",
            next_review_at=None,
            review_history=[],
        ))

    UserDictionaryEntry.objects.bulk_create(bulk_entries)
