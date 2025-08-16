from kanjilearner.constants import SRSStage
from rest_framework.decorators import api_view, permission_classes
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from django.utils import timezone
from kanjilearner.models import DictionaryEntry, UserDictionaryEntry
from kanjilearner.serializers import DictionaryEntrySerializer
import json


@api_view(['GET'])
@permission_classes([IsAuthenticated])
def get_lessons(request):
    """
    Return lessons for the user that have been unlocked but not yet started (srs_stage == "L").
    Supports ?limit=... query param.
    """
    limit = int(request.query_params.get("limit", 100))  # default to 100 if not specified

    user_entries = (
        UserDictionaryEntry.objects
        .filter(user=request.user, srs_stage=SRSStage.LESSON)  # Already filtered to unlocked lessons
        .select_related("entry")
    )

    entries = [ude.entry for ude in user_entries]
    entries.sort(key=lambda e: (e.level, e.priority))

    serializer = DictionaryEntrySerializer(entries[:limit], many=True, context={"request": request})
    return Response(serializer.data)


@api_view(['GET'])
@permission_classes([IsAuthenticated])
def get_reviews(request):
    """
    Return reviewable UserDictionaryEntries:
    - Unlocked (not LOCKED)
    - Not in LESSON stage
    - Due for review (next_review_at <= now)
    Supports ?limit=... query param.
    """
    limit = int(request.query_params.get("limit", 100))
    now = timezone.now()

    user_entries = (
        UserDictionaryEntry.objects
        .filter(user=request.user)
        .exclude(srs_stage__in=[SRSStage.LOCKED, SRSStage.LESSON])  # exclude LOCKED and LESSON
        .filter(next_review_at__lte=now)
        .select_related("entry")
    )

    entries = [ude.entry for ude in user_entries]
    entries.sort(key=lambda e: (e.level, e.priority))

    serializer = DictionaryEntrySerializer(entries[:limit], many=True)
    return Response(serializer.data)



@api_view(['GET'])
@permission_classes([IsAuthenticated])
def get_recent_mistakes(request):
    """
    Return up to 50 most recent mistakes across all UserDictionaryEntries.
    Mistakes are timestamps stored in wrong_history (JSON array of ISO strings).
    """
    user_entries = (
        UserDictionaryEntry.objects
        .filter(user=request.user)
        .exclude(srs_stage__in=[SRSStage.LOCKED, SRSStage.LESSON])
        .select_related('entry')
    )

    mistakes = []

    for ude in user_entries:
        try:
            wrongs = json.loads(ude.wrong_history or "[]")
            for ts in wrongs:
                try:
                    timestamp = timezone.datetime.fromisoformat(ts)
                    if timezone.is_naive(timestamp):
                        timestamp = timezone.make_aware(timestamp)
                    mistakes.append((timestamp, ude.entry))
                except Exception:
                    continue
        except Exception:
            continue

    # Sort all mistake timestamps descending (most recent first)
    mistakes.sort(key=lambda x: x[0], reverse=True)

    # Return the most recent 50 dictionary entries with mistakes
    recent_entries = [entry for _, entry in mistakes[:50]]

    serializer = DictionaryEntrySerializer(recent_entries, many=True)
    return Response(serializer.data)