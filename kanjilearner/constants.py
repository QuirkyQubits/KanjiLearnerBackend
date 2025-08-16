# kanjilearner/constants.py or kanjilearner/enums.py
from django.db import models
from datetime import timedelta


class SRSStage(models.TextChoices):
    LOCKED = "LOCKED", "Locked"
    LESSON = "LESSON", "Lesson"
    APPRENTICE_1 = "APPRENTICE_1", "Apprentice 1"
    APPRENTICE_2 = "APPRENTICE_2", "Apprentice 2"
    APPRENTICE_3 = "APPRENTICE_3", "Apprentice 3"
    APPRENTICE_4 = "APPRENTICE_4", "Apprentice 4"
    GURU_1 = "GURU_1", "Guru 1"
    GURU_2 = "GURU_2", "Guru 2"
    MASTER = "MASTER", "Master"
    ENLIGHTENED = "ENLIGHTENED", "Enlightened"
    BURNED = "BURNED", "Burned"


# Maps SRSStage enum values to timedelta intervals
SRS_INTERVALS = {
    SRSStage.APPRENTICE_1: timedelta(hours=4),
    SRSStage.APPRENTICE_2: timedelta(hours=8),
    SRSStage.APPRENTICE_3: timedelta(days=1),
    SRSStage.APPRENTICE_4: timedelta(days=2),
    SRSStage.GURU_1: timedelta(days=7),
    SRSStage.GURU_2: timedelta(days=14),
    SRSStage.MASTER: timedelta(days=30),
    SRSStage.ENLIGHTENED: timedelta(days=120),
    # SRSStage.BURNED: no interval – final stage
}