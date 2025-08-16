from django.core.management.base import BaseCommand
from django.contrib.auth import get_user_model
from kanjilearner.utils import initialize_user_dictionary_entries
from kanjilearner.models import UserDictionaryEntry
from kanjilearner.constants import EntryType, SRSStage
from kanjilearner.models import DictionaryEntry


User = get_user_model()

class Command(BaseCommand):
    help = "Initialize dictionary entries for the admin user"

    def handle(self, *args, **kwargs):
        # code goes here to run
        # run it like $ python manage.py run_init

        # Fetch all level 0 entries
        level_0_entries = DictionaryEntry.objects.filter(level=0)

        # Update their entry_type to RADICAL
        updated_count = level_0_entries.update(entry_type=EntryType.RADICAL)
        
        self.stdout.write(self.style.SUCCESS("Initialization complete."))