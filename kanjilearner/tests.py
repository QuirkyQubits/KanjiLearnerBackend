from django.test import TestCase
from django.contrib.auth import get_user_model
from django.utils import timezone
from datetime import timedelta
from kanjilearner.models import DictionaryEntry, UserDictionaryEntry
from .utils import initialize_user_dictionary_entries  # adjust if in another module
from kanjilearner.constants import SRSStage, SRS_INTERVALS, EntryType

# Use the correct user model (default or custom)
User = get_user_model()


class UserDictionaryEntryTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(username="testuser", password="testpass")

        # Radical
        self.radical = DictionaryEntry.objects.create(
            literal="⼈", meaning="person", entry_type=EntryType.RADICAL, level=1, priority=1
        )

        # Kanji that depends on radical
        self.kanji = DictionaryEntry.objects.create(
            literal="人", meaning="person", entry_type=EntryType.KANJI, level=1, priority=2
        )
        self.kanji.constituents.add(self.radical)

        # Vocab that depends on kanji
        self.vocab = DictionaryEntry.objects.create(
            literal="人々", meaning="people", entry_type=EntryType.VOCAB, level=1, priority=3
        )
        self.vocab.constituents.add(self.kanji)

        # Radical unlocked and reviewed, not due yet
        UserDictionaryEntry.objects.create(
            user=self.user,
            entry=self.radical,
            unlocked_at=timezone.now() - timedelta(days=3),
            srs_stage=SRSStage.GURU_2,
            last_reviewed_at=timezone.now(),
            next_review_at=timezone.now() + SRS_INTERVALS[SRSStage.GURU_2],
            review_history=[],
        )

        # Kanji unlocked, review is due
        UserDictionaryEntry.objects.create(
            user=self.user,
            entry=self.kanji,
            unlocked_at=timezone.now() - timedelta(days=2),
            srs_stage=SRSStage.APPRENTICE_1,
            last_reviewed_at=timezone.now() - timedelta(hours=5),
            next_review_at=timezone.now() - timedelta(hours=1),
            review_history=[],
        )

        # Vocab still locked
        UserDictionaryEntry.objects.create(
            user=self.user,
            entry=self.vocab,
            review_history=[],
        )

    def test_pending_reviews_helper(self):
        pending = UserDictionaryEntry.get_pending_reviews(self.user)
        self.assertEqual(pending.count(), 1)
        self.assertEqual(pending.first().entry.literal, "人")

    def test_locked_items_still_locked(self):
        locked = UserDictionaryEntry.objects.filter(user=self.user, srs_stage=SRSStage.LOCKED)
        self.assertEqual(locked.count(), 1)
        self.assertEqual(locked.first().entry.literal, "人々")

    def test_unlocked_items_count(self):
        unlocked = UserDictionaryEntry.objects.filter(user=self.user).exclude(srs_stage=SRSStage.LOCKED)
        self.assertEqual(unlocked.count(), 2)


class AutoUnlockTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(username="testuser", password="testpass")

        # Create radical, kanji, and vocab
        self.radical = DictionaryEntry.objects.create(
            literal="⼈", entry_type=EntryType.RADICAL, level=1, priority=1
        )
        self.kanji = DictionaryEntry.objects.create(
            literal="人", entry_type=EntryType.KANJI, level=1, priority=2
        )
        self.kanji.constituents.add(self.radical)

        self.vocab = DictionaryEntry.objects.create(
            literal="人々", entry_type=EntryType.VOCAB, level=1, priority=3
        )
        self.vocab.constituents.add(self.kanji)

        # Create radical user entry (unlocked, A4)
        self.radical_user_entry = UserDictionaryEntry.objects.create(
            user=self.user,
            entry=self.radical,
            unlocked_at=timezone.now() - timedelta(days=5),
            srs_stage=SRSStage.APPRENTICE_4,
            last_reviewed_at=timezone.now() - timedelta(days=1),
            next_review_at=timezone.now() - timedelta(hours=1),
            review_history=[],
        )

        # Create kanji user entry (locked for now)
        self.kanji_user_entry = UserDictionaryEntry.objects.create(
            user=self.user,
            entry=self.kanji,
            review_history=[],
        )

        # Create vocab user entry (locked for now)
        self.vocab_user_entry = UserDictionaryEntry.objects.create(
            user=self.user,
            entry=self.vocab,
            review_history=[],
        )

    def test_promoting_radical_unlocks_kanji(self):
        # Confirm kanji is initially locked
        kanji_entry = UserDictionaryEntry.objects.get(user=self.user, entry=self.kanji)
        self.assertFalse(kanji_entry.is_unlocked)

        # Promote radical from A4 → G1
        self.radical_user_entry.promote()

        # Confirm the kanji is unlocked
        kanji_entry.refresh_from_db()
        self.assertTrue(kanji_entry.is_unlocked)
        self.assertEqual(kanji_entry.srs_stage, SRSStage.LESSON)
        self.assertIsNone(kanji_entry.next_review_at)

    def test_promoting_kanji_unlocks_vocab(self):
        # Promote radical first so kanji gets unlocked
        self.radical_user_entry.promote()

        # Manually set kanji to A4 and ready to promote
        kanji_entry = UserDictionaryEntry.objects.get(user=self.user, entry=self.kanji)
        kanji_entry.unlocked_at = timezone.now() - timedelta(days=1)
        kanji_entry.srs_stage = SRSStage.APPRENTICE_4
        kanji_entry.last_reviewed_at = timezone.now() - timedelta(hours=8)
        kanji_entry.next_review_at = timezone.now() - timedelta(hours=1)
        kanji_entry.save()

        # Confirm vocab is initially locked
        vocab_entry = UserDictionaryEntry.objects.get(user=self.user, entry=self.vocab)
        self.assertFalse(vocab_entry.is_unlocked)

        # Promote kanji to G1
        kanji_entry.promote()

        # Confirm vocab gets unlocked
        vocab_entry.refresh_from_db()
        self.assertTrue(vocab_entry.is_unlocked)
        self.assertEqual(vocab_entry.srs_stage, SRSStage.LESSON)
        self.assertIsNone(vocab_entry.next_review_at)


class InitializeUserDictionaryEntriesTest(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(username="testuser", password="password")

        # Sample dictionary entries
        DictionaryEntry.objects.create(
            literal="⼀", meaning="One", entry_type=EntryType.RADICAL, level=1, priority=1
        )
        DictionaryEntry.objects.create(
            literal="⼆", meaning="Two", entry_type=EntryType.RADICAL, level=2, priority=1
        )
        DictionaryEntry.objects.create(
            literal="三", meaning="Three", entry_type=EntryType.KANJI, level=1, priority=2
        )

        radical = DictionaryEntry.objects.get(literal="⼀")
        kanji = DictionaryEntry.objects.get(literal="三")
        kanji.constituents.add(radical)

    def test_initialize_user_dictionary_entries(self):
        initialize_user_dictionary_entries(self.user)

        entries = DictionaryEntry.objects.prefetch_related("constituents").all()
        user_entries = UserDictionaryEntry.objects.filter(user=self.user)

        self.assertEqual(user_entries.count(), entries.count())

        for entry in entries:
            user_entry = user_entries.get(entry=entry)

            # Expect unlocked if:
            # - Level 1 radical
            # - OR Level 1 kanji with only level 0 constituents
            should_unlock = False

            if entry.level == 1:
                if entry.entry_type == EntryType.RADICAL:
                    should_unlock = True
                elif entry.entry_type == EntryType.KANJI:
                    if all(c.level < 1 for c in entry.constituents.all()):
                        should_unlock = True

            if should_unlock:
                self.assertNotEqual(user_entry.srs_stage, SRSStage.LOCKED.value)
                self.assertIsNotNone(user_entry.unlocked_at)
            else:
                self.assertEqual(user_entry.srs_stage, SRSStage.LOCKED.value)
                self.assertIsNone(user_entry.unlocked_at)

        for ue in user_entries:
            self.assertEqual(ue.review_history, [])
