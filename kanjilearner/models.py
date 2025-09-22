from typing import Type
from django.db import models

# Create your models here.

from django.contrib.auth import get_user_model
from django.core.exceptions import ValidationError
from django.contrib.postgres.fields import ArrayField
from django.db import models
from datetime import timedelta
from django.utils import timezone
from django.contrib.auth.models import User
from django.db.models import QuerySet
from typing import Type
from kanjilearner.constants import SRSStage, SRS_INTERVALS, EntryType


User = get_user_model()


class DictionaryEntry(models.Model):
    entry_type = models.CharField(
        max_length=10,
        choices=EntryType.choices,
        null=False,
        blank=False,
        default=EntryType.RADICAL
    )

    literal = models.CharField(max_length=10, help_text="The character or string (e.g. 水, 食べる)")

    meaning = models.CharField(max_length=255)
    # Only applies to kanji entries
    kunyomi_readings = ArrayField(models.CharField(max_length=50), blank=True, default=list)
    onyomi_readings = ArrayField(models.CharField(max_length=50), blank=True, default=list)

    # Only applies to vocab entries
    readings = ArrayField(
        models.CharField(max_length=50),
        blank=True,
        default=list,
        help_text="Kana readings for vocab (e.g. たべる, みず)"
    )

    explanation = models.TextField(
        blank=True,
        help_text="Explain the definition in context and reading distinctions if multiple readings exist."
    )

    level = models.PositiveIntegerField()

    # Dependencies and usage
    constituents = models.ManyToManyField("self", symmetrical=False, blank=True, related_name="used_in")

    # Optional audio clip (for vocab entries)
    audio = models.FileField(upload_to="audio/", blank=True, null=True)

    # Mnemonics
    reading_mnemonic = models.TextField(
        blank=True,
        help_text="Explanation to help remember the reading"
    )
    meaning_mnemonic = models.TextField(
        blank=True,
        help_text="Explanation to help remember the meaning"
    )

    PARTS_OF_SPEECH_CHOICES = [
        ("noun", "Noun"),
        ("suru_noun", "する-Noun"),
        ("i_adj", "い-Adjective"),
        ("na_adj", "な-Adjective"),
        ("godan_verb", "Godan Verb (五段動詞)"),
        ("ichidan_verb", "Ichidan Verb (一段動詞)"),
        ("transitive_verb", "Transitive Verb"),
        ("intransitive_verb", "Intransitive Verb"),
        ("adverb", "Adverb"),
        ("expression", "Expression"),
        ("conjunction", "Conjunction"),
        ("prefix", "Prefix"),
        ("suffix", "Suffix"),
    ]

    parts_of_speech = ArrayField(
        models.CharField(max_length=30, choices=PARTS_OF_SPEECH_CHOICES),
        blank=True,
        default=list,
        help_text="Multiple parts of speech allowed (e.g. noun, suru_noun)"
    )

    class Meta:
        ordering = ["level"]
        
        constraints = [
            models.CheckConstraint(
                check=models.Q(entry_type__in=[e.value for e in EntryType]),
                name="valid_entry_type_only"
            ),
        ]

    def __str__(self):
        return f"{self.literal} ({self.get_entry_type_display()})"



class RecentMistake(models.Model):
    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name='recent_mistakes')
    entry = models.ForeignKey(DictionaryEntry, on_delete=models.CASCADE)
    timestamp = models.DateTimeField(auto_now_add=True)

    class Meta:
        indexes = [
            models.Index(fields=['user', 'timestamp']),
        ]
        ordering = ['-timestamp']


class UserDictionaryEntry(models.Model):
    user = models.ForeignKey("auth.User", on_delete=models.CASCADE)
    entry = models.ForeignKey("DictionaryEntry", on_delete=models.CASCADE)
    
    @property
    def is_unlocked(self) -> bool:
        return self.srs_stage != SRSStage.LOCKED

    unlocked_at = models.DateTimeField(null=True, blank=True)

    # L, Apprentice 1/2/3/4, Guru 1/2, Master, Enlightened, Burned
    srs_stage = models.CharField(max_length=30, choices=SRSStage.choices, default=SRSStage.LOCKED)
    next_review_at = models.DateTimeField(null=True, blank=True)
    last_reviewed_at = models.DateTimeField(null=True, blank=True)

    # Review history — structured data (timestamps, results, etc.)
    review_history = models.JSONField(default=list, blank=True)

    # User-provided synonyms — list of plain strings
    user_synonyms = ArrayField(
        models.CharField(max_length=100),
        blank=True,
        default=list
    )

    # User example sentences — list of plain strings
    user_sentences = ArrayField(
        models.CharField(max_length=300),
        blank=True,
        default=list
    )

    @classmethod
    def get_pending_reviews(cls: Type["UserDictionaryEntry"], user: "User") -> QuerySet["UserDictionaryEntry"]:
        return cls.objects.filter(
            user=user,
            srs_stage__in=[
                SRSStage.LESSON,
                SRSStage.APPRENTICE_1,
                SRSStage.APPRENTICE_2,
                SRSStage.APPRENTICE_3,
                SRSStage.APPRENTICE_4,
                SRSStage.GURU_1,
                SRSStage.GURU_2,
                SRSStage.MASTER,
                SRSStage.ENLIGHTENED,
            ],
            next_review_at__lte=timezone.now()
)

    def unlock(self):
        if not self.is_unlocked:
            self.unlocked_at = timezone.now()
            self.srs_stage = SRSStage.LESSON
            self.next_review_at = None  # Waits for lesson to be completed
            self.save()

    def complete_lesson(self):
        if self.srs_stage == SRSStage.LESSON:
            self.srs_stage = SRSStage.APPRENTICE_1
            self.next_review_at = timezone.now() + SRS_INTERVALS[SRSStage.APPRENTICE_1]
            self.save()


    def promote(self):
        stage_order = [
            SRSStage.LOCKED,
            SRSStage.LESSON,
            SRSStage.APPRENTICE_1,
            SRSStage.APPRENTICE_2,
            SRSStage.APPRENTICE_3,
            SRSStage.APPRENTICE_4,
            SRSStage.GURU_1,
            SRSStage.GURU_2,
            SRSStage.MASTER,
            SRSStage.ENLIGHTENED,
            SRSStage.BURNED,
        ]

        try:
            index = stage_order.index(self.srs_stage)
        except ValueError:
            raise ValueError(f"Invalid stage value: {self.srs_stage}")
        
        if index < len(stage_order) - 1:
            self.srs_stage = stage_order[index + 1]
            self.last_reviewed_at = timezone.now()
            self.next_review_at = (
                timezone.now() + SRS_INTERVALS.get(self.srs_stage) if self.srs_stage != SRSStage.BURNED else None
            )
            self.save()

    
    def demote(self):
        """Demote item based on SRS rules when user gets it wrong."""
        if self.srs_stage in {SRSStage.LOCKED, SRSStage.LESSON, SRSStage.BURNED}:
            return  # No demotion for Lessons, Burned, Or Init

        # Unified demotion map, including A1 → A1 fallback
        demotion_map = {
            SRSStage.APPRENTICE_1: SRSStage.APPRENTICE_1,
            SRSStage.APPRENTICE_2: SRSStage.APPRENTICE_1,
            SRSStage.APPRENTICE_3: SRSStage.APPRENTICE_1,
            SRSStage.APPRENTICE_4: SRSStage.APPRENTICE_1,
            SRSStage.GURU_1: SRSStage.APPRENTICE_4,
            SRSStage.GURU_2: SRSStage.APPRENTICE_4,
            SRSStage.MASTER: SRSStage.GURU_1,
            SRSStage.ENLIGHTENED: SRSStage.GURU_1,
        }

        new_stage = demotion_map.get(self.srs_stage, SRSStage.APPRENTICE_1)  # Safety fallback
        self.srs_stage = new_stage
        self.last_reviewed_at = timezone.now()
        self.next_review_at = timezone.now() + SRS_INTERVALS[new_stage]
        self.save()
    
    
    def record_recent_mistake(user, entry):
        now = timezone.now()

        # Delete old ones past 24h
        RecentMistake.objects.filter(user=user, timestamp__lt=now - timedelta(hours=24)).delete()

        # Count how many are left after purge
        count = RecentMistake.objects.filter(user=user).count()

        if count >= 50:
            # Delete the oldest to make room
            oldest = (
                RecentMistake.objects
                .filter(user=user)
                .order_by('timestamp')
                .first()
            )
            if oldest:
                oldest.delete()

        # Create the new mistake
        RecentMistake.objects.create(user=user, entry=entry)



class PlannedEntry(models.Model):
    user = models.ForeignKey(User, on_delete=models.CASCADE)
    entry = models.ForeignKey(DictionaryEntry, on_delete=models.CASCADE)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        unique_together = ("user", "entry")

    def __str__(self):
        return f"{self.user.username} → {self.entry.literal} (planned)"