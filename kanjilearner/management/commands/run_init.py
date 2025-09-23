from django.core.management.base import BaseCommand
from django.contrib.auth import get_user_model
from kanjilearner.utils import initialize_user_dictionary_entries
from kanjilearner.models import UserDictionaryEntry
from kanjilearner.constants import EntryType, SRSStage
from kanjilearner.models import DictionaryEntry
from django.contrib.auth.models import User
from django.db.models import Count


User = get_user_model()


def delete_last_n_entries():
    # Delete them
    DictionaryEntry.objects.filter(id__gte=500, id__lte=570).delete()


def insert_radicals():
    radicals = [
        # Level 51
        {"literal": "胃", "meaning": "Stomach"},
        # Level 52
        {"literal": "夌", "meaning": "Frostbite"},
        # Level 53
        {"literal": "高", "meaning": "Tall"},
        # Level 54
        # (no radicals)
        # Level 55
        {"literal": "疑", "meaning": "Doubt"},
        {"literal": "感", "meaning": "Feeling"},
        # Level 56
        # (no radicals)
        # Level 57
        {"literal": "凹", "meaning": "Concave"},
        {"literal": "凸", "meaning": "Convex"},
        # Level 58
        # (no radicals)
        # Level 59
        {"literal": "下", "meaning": "Below"},
        # Level 60
        # (no radicals)

        # glitches
        # (none in this batch)
    ]

    entries = [
        DictionaryEntry(
            literal=r["literal"],
            meaning=r["meaning"],
            entry_type=EntryType.RADICAL,
            level=0,
        )
        for r in radicals
    ]

    DictionaryEntry.objects.bulk_create(entries, ignore_conflicts=True)
    print(f"Inserted {len(entries)} radicals into level 0.")


def check_dupes():
    dupes = (
        DictionaryEntry.objects
        .filter(level=0, entry_type=EntryType.RADICAL)        # only level 0 radicals
        .exclude(literal="")                                  # ignore blanks
        .values("literal")
        .annotate(count=Count("id"))
        .filter(count__gt=1)                                  # only duplicates
    )
    
    total_dupes = dupes.count()
    print(f"Found {total_dupes} duplicate radicals in level 0.")

    for d in dupes:
        print(f"Literal: {d['literal'].encode('utf-8', errors='replace')}, Count: {d['count']}")


class Command(BaseCommand):
    help = "Initialize dictionary entries for the admin user"

    def handle(self, *args, **kwargs):
        # code goes here to run
        # run it like $ python manage.py run_init

        user = User.objects.get(username="testuser")
        
        # initialize_user_dictionary_entries(user)

        # check_dupes()

        self.stdout.write(self.style.SUCCESS("Initialization complete."))