from django.core.management.base import BaseCommand
from django.contrib.auth import get_user_model
from kanjilearner.utils import initialize_user_dictionary_entries
from kanjilearner.models import UserDictionaryEntry
from kanjilearner.constants import SRSStage
from kanjilearner.models import DictionaryEntry
from django.db.models import Q


User = get_user_model()

class Command(BaseCommand):
    help = "Initialize dictionary entries for the admin user"

    def handle(self, *args, **kwargs):
        # code goes here to run
        # run it like $ python manage.py run_init

        self.stdout.write(str(DictionaryEntry.objects.filter(level=0).filter(Q(type__isnull=True) | Q(type="")).count()))
        
        self.stdout.write(self.style.SUCCESS("Initialization complete."))