import json
from django.test import TestCase
from django.contrib.auth import get_user_model
from django.utils import timezone
from datetime import timedelta
from kanjilearner.models import DictionaryEntry, UserDictionaryEntry, PlannedEntry
from .utils import initialize_user_dictionary_entries  # adjust if in another module
from kanjilearner.constants import SRSStage, SRS_INTERVALS, EntryType
from django.urls import reverse
from kanjilearner.services.plan import plan_entry, process_planned_entries

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


class DictionarySearchTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(username="testuser", password="pw")
        self.client.force_login(self.user)   # <— add this

        self.entry_kanji = DictionaryEntry.objects.create(
            entry_type=EntryType.KANJI,
            literal="負",
            meaning="defeat",
            kunyomi_readings=["まける"],
            onyomi_readings=["フ"],
            level=10,
            priority=1
        )
        self.entry_vocab = DictionaryEntry.objects.create(
            entry_type=EntryType.VOCAB,
            literal="雨",
            meaning="rain",
            readings=["あめ"],
            level=5,
            priority=1
        )
        self.entry_kanji = DictionaryEntry.objects.create(
            entry_type=EntryType.KANJI,
            literal="負け犬",
            meaning="loser, failure",
            kunyomi_readings=["まける"],
            onyomi_readings=["フ"],
            level=10,
            priority=2
        )

    def test_search_by_literal(self):
        url = reverse("search")
        resp = self.client.get(url, {"q": "負"})
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(resp.data[0]["entry"]["literal"], "負")
        self.assertEqual(resp.data[1]["entry"]["literal"], "負け犬")

    def test_search_by_kunyomi(self):
        url = reverse("search")
        resp = self.client.get(url, {"q": "まける"})
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(resp.data[0]["entry"]["literal"], "負")

    def test_search_by_onyomi(self):
        url = reverse("search")
        resp = self.client.get(url, {"q": "フ"})
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(resp.data[0]["entry"]["literal"], "負")

    def test_search_by_vocab_reading(self):
        url = reverse("search")
        resp = self.client.get(url, {"q": "あめ"})
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(resp.data[0]["entry"]["literal"], "雨")

    def test_search_by_meaning(self):
        url = reverse("search")
        resp = self.client.get(url, {"q": "rain"})
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(resp.data[0]["entry"]["literal"], "雨")

    def test_search_no_results(self):
        url = reverse("search")
        resp = self.client.get(url, {"q": "banana"})
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(len(resp.data), 0)

    def test_missing_query(self):
        url = reverse("search")
        resp = self.client.get(url)
        self.assertEqual(resp.status_code, 400)
        self.assertIn("error", resp.data)


class EntryDetailViewTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(username="testuser", password="pw")
        self.client.force_login(self.user)   # <— add this

        self.entry = DictionaryEntry.objects.create(
            literal="景",
            meaning="scenery",
            kunyomi_readings=["けい"],
            onyomi_readings=[],
            readings=[],
            entry_type=EntryType.KANJI,
            level=1,
            priority=1,
        )

    def test_entry_detail_success(self):
        url = reverse("entry_detail", args=[self.entry.pk])
        response = self.client.get(url)

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data["entry"]["literal"], self.entry.literal)
        self.assertEqual(response.data["entry"]["meaning"], self.entry.meaning)

    def test_entry_detail_not_found(self):
        url = reverse("entry_detail", args=[9999])  # pk that doesn't exist
        response = self.client.get(url)

        self.assertEqual(response.status_code, 404)
        self.assertIn("error", response.data)
        self.assertEqual(response.data["error"], "Not found")


class PlanEntryTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(username="testuser", password="pw")

    def test_recursive_plan_unlocks_with_dependencies(self):
        """
        Simulate vocab XYZ, where X depends on radicals A,B,C.
        """

        # Build radicals A, B, C
        A = DictionaryEntry.objects.create(entry_type="RADICAL", literal="A", meaning="radical A", level=1, priority=1)
        B = DictionaryEntry.objects.create(entry_type="RADICAL", literal="B", meaning="radical B", level=1, priority=2)
        C = DictionaryEntry.objects.create(entry_type="RADICAL", literal="C", meaning="radical C", level=1, priority=3)

        # Build kanji X (needs A,B,C)
        X = DictionaryEntry.objects.create(entry_type="KANJI", literal="X", meaning="kanji X", level=2, priority=1)
        X.constituents.add(A, B, C)

        # Build kanji Y and Z (no dependencies for simplicity)
        Y = DictionaryEntry.objects.create(entry_type="KANJI", literal="Y", meaning="kanji Y", level=2, priority=2)
        Z = DictionaryEntry.objects.create(entry_type="KANJI", literal="Z", meaning="kanji Z", level=2, priority=3)

        # Build vocab XYZ (needs X, Y, Z)
        XYZ = DictionaryEntry.objects.create(entry_type="VOCAB", literal="XYZ", meaning="word XYZ", level=3, priority=1)
        XYZ.constituents.add(X, Y, Z)

        # Plan to learn XYZ
        plan_entry(self.user, XYZ)

        # Expect: A,B,C,Y,Z in lessons; X and XYZ in planned
        lessons = UserDictionaryEntry.objects.filter(user=self.user, srs_stage=SRSStage.LESSON)
        planned = PlannedEntry.objects.filter(user=self.user)

        self.assertSetEqual({e.entry.literal for e in lessons}, {"A", "B", "C", "Y", "Z"})
        self.assertSetEqual({p.entry.literal for p in planned}, {"X", "XYZ"})

        # Guru A, B, C manually
        for radical in [A, B, C]:
            ude = UserDictionaryEntry.objects.get(user=self.user, entry=radical)
            ude.srs_stage = SRSStage.GURU_1
            ude.save()

        # Process planned
        process_planned_entries(self.user)

        # X should unlock, XYZ still waiting
        self.assertEqual(UserDictionaryEntry.objects.get(user=self.user, entry=X).srs_stage, SRSStage.LESSON)
        self.assertFalse(PlannedEntry.objects.filter(user=self.user, entry=X).exists())
        self.assertTrue(PlannedEntry.objects.filter(user=self.user, entry=XYZ).exists())

        # Guru X, Y, Z
        for kanji in [X, Y, Z]:
            ude = UserDictionaryEntry.objects.get(user=self.user, entry=kanji)
            ude.srs_stage = SRSStage.GURU_1
            ude.save()

        process_planned_entries(self.user)

        # XYZ should now unlock
        self.assertEqual(UserDictionaryEntry.objects.get(user=self.user, entry=XYZ).srs_stage, SRSStage.LESSON)
        self.assertFalse(PlannedEntry.objects.filter(user=self.user, entry=XYZ).exists())

    def test_plan_entry_no_duplicate(self):
        """
        If entry is already in lessons, planning it should do nothing.
        """
        A = DictionaryEntry.objects.create(entry_type="RADICAL", literal="A", meaning="radical A", level=1)
        UserDictionaryEntry.objects.create(user=self.user, entry=A, srs_stage=SRSStage.LESSON)

        plan_entry(self.user, A)

        self.assertEqual(PlannedEntry.objects.filter(user=self.user).count(), 0)
        self.assertEqual(UserDictionaryEntry.objects.filter(user=self.user, entry=A).count(), 1)

    def test_plan_entry_already_gurued(self):
        """
        If entry is already Guru, it should not go to PlannedEntry.
        """
        A = DictionaryEntry.objects.create(entry_type="RADICAL", literal="A", meaning="radical A", level=1)
        UserDictionaryEntry.objects.create(user=self.user, entry=A, srs_stage=SRSStage.GURU_1)

        plan_entry(self.user, A)

        self.assertEqual(PlannedEntry.objects.filter(user=self.user).count(), 0)
        self.assertEqual(UserDictionaryEntry.objects.get(user=self.user, entry=A).srs_stage, SRSStage.GURU_1)


class PlannedEntriesAPITests(TestCase):
    def setUp(self):
        # Create user + login
        self.user = User.objects.create_user(username="testuser", password="pw")
        self.client.login(username="testuser", password="pw")

        # Create another user to confirm isolation
        self.other_user = User.objects.create_user(username="otheruser", password="pw")

        # Create dictionary entries
        self.kanji1 = DictionaryEntry.objects.create(
            literal="火", meaning="fire", entry_type=EntryType.KANJI, level=1, priority=1
        )
        self.kanji2 = DictionaryEntry.objects.create(
            literal="水", meaning="water", entry_type=EntryType.KANJI, level=1, priority=2
        )

        # Give user UDE for kanji1
        self.ude1 = UserDictionaryEntry.objects.create(
            user=self.user, entry=self.kanji1, srs_stage=SRSStage.LOCKED, review_history=[]
        )

        # Plan kanji1 for current user
        PlannedEntry.objects.create(user=self.user, entry=self.kanji1)

        # Plan kanji2 for other user
        PlannedEntry.objects.create(user=self.other_user, entry=self.kanji2)

    def test_get_planned_returns_only_user_entries(self):
        url = reverse("get_planned")  # make sure your urls.py names this
        resp = self.client.get(url)

        self.assertEqual(resp.status_code, 200)
        self.assertEqual(len(resp.data), 1)

        ude = resp.data[0]
        self.assertEqual(ude["entry"]["literal"], "火")
        self.assertEqual(ude["in_plan"], True)  # serializer should add this flag

    def test_get_planned_empty_if_none(self):
        # Clear user’s planned entries
        PlannedEntry.objects.filter(user=self.user).delete()

        url = reverse("get_planned")
        resp = self.client.get(url)

        self.assertEqual(resp.status_code, 200)
        self.assertEqual(resp.data, [])

    def test_get_planned_includes_srs_stage(self):
        url = reverse("get_planned")
        resp = self.client.get(url)
        self.assertEqual(resp.status_code, 200)

        ude = resp.data[0]
        # Should include current SRS stage of user’s entry
        self.assertIn("srs_stage", ude)
        self.assertEqual(ude["srs_stage"], SRSStage.LOCKED)


class PlanAddAPITests(TestCase):
    def setUp(self):
        self.user = get_user_model().objects.create_user(
            username="tester", password="password"
        )
        self.client.login(username="tester", password="password")

        # Simple kanji entry with no constituents
        self.kanji = DictionaryEntry.objects.create(
            literal="勝",
            meaning="win",
            entry_type=EntryType.KANJI,
            level=1,
            priority=1,
        )

    def test_plan_add_success(self):
        """Entries with no prereqs should be unlocked immediately, not planned."""
        url = reverse("plan_add")
        resp = self.client.post(
            url,
            data=json.dumps({"entry_id": self.kanji.id}),
            content_type="application/json",
        )
        self.assertEqual(resp.status_code, 200)

        ude = UserDictionaryEntry.objects.get(user=self.user, entry=self.kanji)
        # It should be unlocked into LESSON stage
        self.assertEqual(ude.srs_stage, SRSStage.LESSON)
        # No PlannedEntry created
        self.assertEqual(PlannedEntry.objects.count(), 0)

    def test_plan_add_no_duplicates(self):
        """Calling plan_add twice should not create duplicates."""
        url = reverse("plan_add")

        # First call unlocks
        self.client.post(
            url,
            data=json.dumps({"entry_id": self.kanji.id}),
            content_type="application/json",
        )
        # Second call should do nothing
        self.client.post(
            url,
            data=json.dumps({"entry_id": self.kanji.id}),
            content_type="application/json",
        )

        ude = UserDictionaryEntry.objects.get(user=self.user, entry=self.kanji)
        self.assertEqual(ude.srs_stage, SRSStage.LESSON)
        # Still no PlannedEntry created
        self.assertEqual(PlannedEntry.objects.count(), 0)

    def test_plan_add_with_prerequisites_goes_to_planned(self):
        """Entries with locked prereqs should go into PlannedEntry, not unlock immediately."""
        # Create radical prerequisite
        radical = DictionaryEntry.objects.create(
            literal="力",
            meaning="power",
            entry_type=EntryType.RADICAL,
            level=1,
            priority=2,
        )

        # Create a kanji that depends on radical
        dependent_kanji = DictionaryEntry.objects.create(
            literal="効",
            meaning="effect",
            entry_type=EntryType.KANJI,
            level=2,
            priority=1,
        )
        dependent_kanji.constituents.add(radical)

        url = reverse("plan_add")
        resp = self.client.post(
            url,
            data=json.dumps({"entry_id": dependent_kanji.id}),
            content_type="application/json",
        )
        self.assertEqual(resp.status_code, 200)

        ude = UserDictionaryEntry.objects.get(user=self.user, entry=dependent_kanji)
        # Should still be locked
        self.assertEqual(ude.srs_stage, SRSStage.LOCKED)
        # Should be tracked in PlannedEntry
        self.assertEqual(PlannedEntry.objects.filter(user=self.user, entry=dependent_kanji).count(), 1)

    def test_process_planned_entries_unlocks_after_prereq_guru(self):
        """Planned entries unlock once prerequisites are gurued and process_planned_entries is called."""
        # Create radical prerequisite
        radical = DictionaryEntry.objects.create(
            literal="木",
            meaning="tree",
            entry_type=EntryType.RADICAL,
            level=1,
            priority=3,
        )

        # Create a kanji that depends on radical
        dependent_kanji = DictionaryEntry.objects.create(
            literal="林",
            meaning="woods",
            entry_type=EntryType.KANJI,
            level=2,
            priority=4,
        )
        dependent_kanji.constituents.add(radical)

        # Plan the dependent kanji
        url = reverse("plan_add")
        self.client.post(
            url,
            data=json.dumps({"entry_id": dependent_kanji.id}),
            content_type="application/json",
        )

        # Initially, kanji is in PlannedEntry
        self.assertTrue(PlannedEntry.objects.filter(user=self.user, entry=dependent_kanji).exists())

        # Promote the radical step by step until it reaches GURU_1
        radical_ude = UserDictionaryEntry.objects.get(user=self.user, entry=radical)
        while radical_ude.srs_stage != SRSStage.GURU_1:
            radical_ude.promote()
            radical_ude.refresh_from_db()

        # Run process_planned_entries
        process_planned_entries(self.user)

        # Dependent kanji should now be unlocked (LESSON)
        ude = UserDictionaryEntry.objects.get(user=self.user, entry=dependent_kanji)
        self.assertEqual(ude.srs_stage, SRSStage.LESSON)

        # PlannedEntry for it should be removed
        self.assertFalse(PlannedEntry.objects.filter(user=self.user, entry=dependent_kanji).exists())


