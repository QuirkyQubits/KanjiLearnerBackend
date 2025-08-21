from collections import defaultdict
from datetime import datetime, timedelta
from datetime import timezone as dt_timezone
from django.utils import timezone as dj_timezone
from kanjilearner.constants import SRSStage
from rest_framework.decorators import api_view, permission_classes
from rest_framework.permissions import IsAuthenticated, AllowAny
from rest_framework.response import Response
from kanjilearner.models import DictionaryEntry, RecentMistake, UserDictionaryEntry
from kanjilearner.serializers import DictionaryEntrySerializer
from zoneinfo import ZoneInfo
from django.contrib.auth import authenticate, login
from django.views.decorators.csrf import ensure_csrf_cookie


@api_view(['GET'])
@ensure_csrf_cookie
def get_csrf_token(request):
    return Response({"message": "CSRF cookie set"})


@api_view(['POST'])
@permission_classes([AllowAny])
def login_view(request):
    username = request.data.get("username")
    password = request.data.get("password")

    user = authenticate(request, username=username, password=password)

    if user is not None:
        login(request, user)
        return Response({"message": "Logged in"})
    else:
        return Response({"error": "Invalid credentials"}, status=400)


@api_view(['GET'])
@permission_classes([IsAuthenticated])
def get_lessons(request):
    """
    Return lessons for the user that have been unlocked but not yet started (srs_stage == "L").
    Supports ?limit=... query param.
    """

    limit = int(request.query_params.get("limit", 100))

    # Step 1: Load all UDEs with dictionary entries
    user_entries = (
        UserDictionaryEntry.objects
        .filter(user=request.user, srs_stage=SRSStage.LESSON)
        .select_related("entry")
    )

    # Step 2: Extract and sort dictionary entries
    entries = [ude.entry for ude in user_entries]
    entries.sort(key=lambda e: (e.level, e.priority))

    # Step 3: Apply limit
    limited_entries = entries[:limit]

    # Step 4: Build a filtered entry map for serializer context
    entry_map = {
        entry.id: ude
        for ude in user_entries
        for entry in [ude.entry]
        if entry.id in {e.id for e in limited_entries}
    }

    # Step 5: Serialize with context
    serializer = DictionaryEntrySerializer(
        limited_entries,
        many=True,
        context={
            "request": request,
            "user_entry_map": entry_map
        }
    )
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
    now = datetime.now(dt_timezone.utc)

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
    Return up to 50 recent mistakes from the past 24 hours for the user.
    These are pre-tracked in the RecentMistake table.
    """
    now = datetime.now(dt_timezone.utc)
    cutoff = now - timedelta(hours=24)

    recent_mistakes = (
        RecentMistake.objects
        .filter(user=request.user, timestamp__gte=cutoff)
        .order_by('-timestamp')[:50]
    )

    entries = [rm.entry for rm in recent_mistakes]
    serializer = DictionaryEntrySerializer(entries, many=True)
    return Response(serializer.data)


@api_view(['POST'])
@permission_classes([IsAuthenticated])
def result_success(request):
    """
    Mark a review as successful and promote the corresponding SRS stage.
    Payload:
        {
            "entry_id": <int>
        }
    """
    entry_id = request.data.get("entry_id")
    if entry_id is None:
        return Response({"error": "Missing entry_id"}, status=400)

    try:
        entry = DictionaryEntry.objects.get(id=entry_id)
        user_entry = UserDictionaryEntry.objects.get(user=request.user, entry=entry)
    except (DictionaryEntry.DoesNotExist, UserDictionaryEntry.DoesNotExist):
        return Response({"error": "Entry not found or not unlocked."}, status=404)

    user_entry.promote()
    return Response({
        "message": f"{entry.literal} promoted",
        "new_stage": user_entry.srs_stage,
        "next_review_at": user_entry.next_review_at,
    })


@api_view(['POST'])
@permission_classes([IsAuthenticated])
def result_failure(request):
    """
    Mark a review as failed and demote the corresponding SRS stage.
    Also appends to RecentMistake.
    Payload:
        {
            "entry_id": <int>
        }
    """
    entry_id = request.data.get("entry_id")
    if entry_id is None:
        return Response({"error": "Missing entry_id"}, status=400)

    try:
        entry = DictionaryEntry.objects.get(id=entry_id)
        user_entry = UserDictionaryEntry.objects.get(user=request.user, entry=entry)
    except (DictionaryEntry.DoesNotExist, UserDictionaryEntry.DoesNotExist):
        return Response({"error": "Entry not found or not unlocked."}, status=404)

    user_entry.demote()
    UserDictionaryEntry.record_recent_mistake(user=request.user, entry=entry)

    return Response({
        "message": f"{entry.literal} demoted",
        "new_stage": user_entry.srs_stage,
        "next_review_at": user_entry.next_review_at,
    })



@api_view(['GET'])
@permission_classes([IsAuthenticated])
def get_review_forecast(request):
    """
    Return upcoming reviews from now until 11:59 PM today,
    bucketed by local hour (0-23) in the user's timezone.
    """
    user_tz_str = request.query_params.get("tz")  # e.g. "America/Los_Angeles"
    if not user_tz_str:
        return Response({"error": "Missing 'tz' timezone parameter"}, status=400)

    try:
        user_tz = ZoneInfo(user_tz_str)
    except Exception:
        return Response({"error": f"Unknown timezone: {user_tz_str}"}, status=400)

    now_utc = dj_timezone.now()
    now_local = now_utc.astimezone(user_tz)

    # Build local end of day
    local_day_end = datetime(
        year=now_local.year,
        month=now_local.month,
        day=now_local.day,
        hour=23,
        minute=59,
        second=59,
        tzinfo=user_tz
    )

    utc_start = now_local.astimezone(dt_timezone.utc)
    utc_end = local_day_end.astimezone(dt_timezone.utc)

    # Get upcoming reviews between now and 11:59 PM local time
    upcoming_reviews = (
        UserDictionaryEntry.objects
        .filter(user=request.user)
        .exclude(srs_stage__in=[SRSStage.LOCKED, SRSStage.LESSON])
        .filter(next_review_at__gt=utc_start, next_review_at__lte=utc_end)
        .values_list("next_review_at", flat=True)
    )

    # Bucket by local hour
    buckets = defaultdict(int)
    for dt in upcoming_reviews:
        local_hour = dt.astimezone(user_tz).hour
        buckets[local_hour] += 1

    # Build result with cumulative totals
    result = {}
    cumulative = 0
    for hour in sorted(buckets):
        count = buckets[hour]
        cumulative += count
        result[str(hour)] = {"count": count, "cumulative": cumulative}

    return Response(result)
