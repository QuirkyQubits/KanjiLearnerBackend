from kanjilearner.models import DictionaryEntry, UserDictionaryEntry, PlannedEntry
from kanjilearner.constants import SRSStage

def is_gurued(user_entry: UserDictionaryEntry) -> bool:
    return user_entry.srs_stage in {
        SRSStage.GURU_1,
        SRSStage.GURU_2,
        SRSStage.MASTER,
        SRSStage.ENLIGHTENED,
        SRSStage.BURNED,
    }

def plan_entry(user, entry: DictionaryEntry):
    """
    Recursively add entry to lessons or plan queue.
    """

    try:
        ude = UserDictionaryEntry.objects.get(user=user, entry=entry)
        if is_gurued(ude):
            return  # already gurued, no need to plan
        if ude.srs_stage != SRSStage.LOCKED:
            return  # already in lessons or apprentices
    except UserDictionaryEntry.DoesNotExist:
        ude = UserDictionaryEntry.objects.create(user=user, entry=entry)

    # Check prerequisites
    all_ready = True
    for prereq in entry.constituents.all():
        try:
            prereq_ude = UserDictionaryEntry.objects.get(user=user, entry=prereq)
            if not is_gurued(prereq_ude):
                all_ready = False
                if prereq_ude.srs_stage == SRSStage.LOCKED:
                    prereq_ude.unlock()
        except UserDictionaryEntry.DoesNotExist:
            # Recursively plan prereq
            plan_entry(user, prereq)
            all_ready = False

    if all_ready:
        ude.unlock()
    else:
        PlannedEntry.objects.get_or_create(user=user, entry=entry)


"""
Check all planned entries for a user. If every constituent of a planned entry
is Gurued (or higher), unlock the entry (move to LESSON) and remove it from
the plan queue. Run after successful reviews to auto-promote items whose
prerequisites are now satisfied.
"""
def process_planned_entries(user):
    planned = PlannedEntry.objects.filter(user=user)
    for planned_entry in planned:
        entry = planned_entry.entry
        if all(
            UserDictionaryEntry.objects.filter(user=user, entry=c).exists() and
            is_gurued(UserDictionaryEntry.objects.get(user=user, entry=c))
            for c in entry.constituents.all()
        ):
            ude, _ = UserDictionaryEntry.objects.get_or_create(user=user, entry=entry)
            ude.unlock()
            planned_entry.delete()
