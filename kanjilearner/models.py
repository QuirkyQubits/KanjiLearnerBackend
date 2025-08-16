from django.db import models

# Create your models here.

from django.contrib.auth import get_user_model
from django.core.exceptions import ValidationError
from django.contrib.postgres.fields import ArrayField
from django.db import models


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

    level = models.PositiveIntegerField()

    # Dependencies and usage
    constituents = models.ManyToManyField("self", symmetrical=False, blank=True, related_name="used_in")

    # Optional audio clip (for vocab entries)
    audio = models.FileField(upload_to="audio/", blank=True, null=True)

    # priority for with a level, for front-end ordering and lessons priority
    priority = models.PositiveIntegerField(default=1, help_text="Ordering within a level")

    PARTS_OF_SPEECH_CHOICES = [
        ("noun", "Noun"),
        ("transitive_verb", "Transitive Verb"),
        ("intransitive_verb", "Intransitive Verb"),
        ("i_adj", "い-Adjective"),
        ("na_adj", "な-Adjective"),
        ("suru_noun", "する-Noun"),
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

    user = models.ForeignKey(User, on_delete=models.CASCADE)
    entry = models.ForeignKey(DictionaryEntry, on_delete=models.CASCADE)

    # SRS progress
    unlocked = models.BooleanField(default=False)
    unlocked_at = models.DateTimeField(null=True, blank=True)
    srs_stage = models.CharField(max_length=2, choices=SRS_STAGES, default="A1")

    # User custom content
    user_synonyms = models.JSONField(default=list, blank=True)
    user_sentences = models.JSONField(default=list, blank=True)

    # Review log (timestamps + correctness); can be extracted later
    review_history = models.JSONField(default=list, blank=True)

    class Meta:
        unique_together = ("user", "entry")

    def clean(self):
        # Count constraints
        if len(self.user_synonyms) > 10:
            raise ValidationError("You may not have more than 10 user synonyms.")
        if len(self.user_sentences) > 2:
            raise ValidationError("You may not have more than 2 user sentences.")

        # Length constraints
        for synonym in self.user_synonyms:
            if not isinstance(synonym, str):
                raise ValidationError("All synonyms must be strings.")
            if len(synonym) > 50:
                raise ValidationError("Each synonym must be 50 characters or fewer.")

        for sentence in self.user_sentences:
            if not isinstance(sentence, str):
                raise ValidationError("All user sentences must be strings.")
            if len(sentence) > 1000:
                raise ValidationError("Each sentence must be 1000 characters or fewer.")

    def save(self, *args, **kwargs):
        self.full_clean()
        super().save(*args, **kwargs)

    def __str__(self):
        return f"{self.user.username} - {self.entry.literal} ({self.entry.get_type_display()})"