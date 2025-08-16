from django.test import TestCase
from django.contrib.auth.models import User
from django.utils import timezone
from datetime import timedelta
from kanjilearner.models import DictionaryEntry, UserDictionaryEntry


class UserDictionaryEntryTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(username="testuser", password="testpass")

        # Radical
        self.radical = DictionaryEntry.objects.create(
            literal="⼈", meaning="person", type="RADICAL", level=1, priority=1
        )

        # Kanji that depends on radical
        self.kanji = DictionaryEntry.objects.create(
            literal="人", meaning="person", type="KANJI", level=1, priority=2
        )
        self.kanji.constituents.add(self.radical)

        # Vocab that depends on kanji
        self.vocab = DictionaryEntry.objects.create(
            literal="人々", meaning="people", type="VOCAB", level=1, priority=3
        )
        self.vocab.constituents.add(self.kanji)

        # Radical unlocked and reviewed, not due yet
        UserDictionaryEntry.objects.create(
            user=self.user,
            entry=self.radical,
            unlocked=True,
            unlocked_at=timezone.now() - timedelta(days=3),
            srs_stage="G2",
            last_reviewed_at=timezone.now(),
            next_review_at=timezone.now() + UserDictionaryEntry.SRS_INTERVALS["G2"],
            review_history=[],
)

        # Kanji unlocked, review is due
        UserDictionaryEntry.objects.create(
            user=self.user,
            entry=self.kanji,
            unlocked=True,
            unlocked_at=timezone.now() - timedelta(days=2),
            srs_stage="A1",
            last_reviewed_at = timezone.now() - timedelta(hours=5),
            next_review_at = timezone.now() - timedelta(hours=1),
            review_history=[],
        )

        # Vocab still locked
        UserDictionaryEntry.objects.create(
            user=self.user,
            entry=self.vocab,
            unlocked=False,
            review_history=[],
        )

    def test_pending_reviews_helper(self):
        pending = UserDictionaryEntry.get_pending_reviews(self.user)
        self.assertEqual(pending.count(), 1)
        self.assertEqual(pending.first().entry.literal, "人")

    def test_locked_items_still_locked(self):
        locked = UserDictionaryEntry.objects.filter(user=self.user, unlocked=False)
        self.assertEqual(locked.count(), 1)
        self.assertEqual(locked.first().entry.literal, "人々")

    def test_unlocked_items_count(self):
        unlocked = UserDictionaryEntry.objects.filter(user=self.user, unlocked=True)
        self.assertEqual(unlocked.count(), 2)
