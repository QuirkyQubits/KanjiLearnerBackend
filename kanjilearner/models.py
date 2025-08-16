from django.db import models

# Create your models here.

from django.contrib.auth import get_user_model
from django.core.exceptions import ValidationError
from django.contrib.postgres.fields import ArrayField
from django.db import models
from datetime import timedelta
from django.utils import timezone


User = get_user_model()


class DictionaryEntry(models.Model):
    ENTRY_TYPES = [
        ("RADICAL", "Radical"),
        ("KANJI", "Kanji"),
        ("VOCAB", "Vocab"),
    ]

    type = models.CharField(max_length=10, choices=ENTRY_TYPES)
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

    # priority for with a level, for front-end ordering and lessons priority
    priority = models.PositiveIntegerField(default=1, help_text="Ordering within a level")

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
        ordering = ["level", "priority"]
        
        constraints = [
            models.UniqueConstraint(fields=["level", "priority"], name="unique_priority_per_level")
        ]

    def __str__(self):
        return f"{self.literal} ({self.get_type_display()})"


class UserDictionaryEntry(models.Model):
    SRS_STAGES = [
        ("L", "Lesson"),
        ("A1", "Apprentice 1"),
        ("A2", "Apprentice 2"),
        ("A3", "Apprentice 3"),
        ("A4", "Apprentice 4"),
        ("G1", "Guru 1"),
        ("G2", "Guru 2"),
        ("M", "Master"),
        ("E", "Enlightened"),
        ("B", "Burned"),
    ]

    SRS_INTERVALS = {
        "A1": timedelta(hours=4),
        "A2": timedelta(hours=8),
        "A3": timedelta(days=1),
        "A4": timedelta(days=2),
        "G1": timedelta(days=7),
        "G2": timedelta(days=14),
        "M": timedelta(days=30),
        "E": timedelta(days=120),
        # "B": no interval; it's final
    }

    user = models.ForeignKey("auth.User", on_delete=models.CASCADE)
    entry = models.ForeignKey("DictionaryEntry", on_delete=models.CASCADE)
    unlocked = models.BooleanField(default=False)
    unlocked_at = models.DateTimeField(null=True, blank=True)

    # L, Apprentice 1/2/3/4, Guru 1/2, Master, Enlightened, Burned
    srs_stage = models.CharField(max_length=2, choices=SRS_STAGES, default="L")
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

    def unlock(self):
        if not self.unlocked:
            self.unlocked = True
            self.unlocked_at = timezone.now()
            self.srs_stage = "L"
            self.next_review_at = None  # Waits for lesson to be completed
            self.save()

    def complete_lesson(self):
        if self.srs_stage == "L":
            self.srs_stage = "A1"
            self.next_review_at = timezone.now() + self.SRS_INTERVALS["A1"]
            self.save()

    def promote(self):
        stage_order = ["L", "A1", "A2", "A3", "A4", "G1", "G2", "M", "E", "B"]
        try:
            index = self.SRS_STAGES.index(self.srs_stage)
        except ValueError:
            raise ValueError(f"Invalid stage value: {self.srs_stage}")
        
        if index < len(stage_order) - 1:
            self.srs_stage = stage_order[index + 1]
            self.last_reviewed_at = timezone.now()
            self.next_review_at = (
                timezone.now() + self.SRS_INTERVALS.get(self.srs_stage) if self.srs_stage != "B" else None
            )
            self.save()

    
    def demote(self):
        """Demote item based on SRS rules when user gets it wrong."""
        if self.srs_stage == "L" or self.srs_stage == "B":
            return  # No demotion for Lessons or Burned

        # Unified demotion map, including A1 → A1 fallback
        demotion_map = {
            "A1": "A1",
            "A2": "A1",
            "A3": "A1",
            "A4": "A1",
            "G1": "A4",
            "G2": "A4",
            "M":  "G1",
            "E":  "G1"
        }

        new_stage = demotion_map.get(self.srs_stage, "A1")  # Safety fallback
        self.srs_stage = new_stage
        self.last_reviewed_at = timezone.now()
        self.next_review_at = timezone.now() + self.SRS_INTERVALS[new_stage]
        self.save()