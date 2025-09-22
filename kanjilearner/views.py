from collections import defaultdict
from datetime import datetime, timedelta
from datetime import timezone as dt_timezone
from django.utils import timezone as dj_timezone
from kanjilearner.constants import SRSStage
from kanjilearner.services.plan import process_planned_entries
from rest_framework.decorators import api_view, permission_classes
from rest_framework.permissions import IsAuthenticated, AllowAny
from rest_framework.response import Response
from kanjilearner.models import DictionaryEntry, PlannedEntry, RecentMistake, UserDictionaryEntry
from kanjilearner.serializers import DictionaryEntrySerializer, UserDictionaryEntrySerializer
from kanjilearner.services.plan import plan_entry
from zoneinfo import ZoneInfo
from django.contrib.auth import authenticate, login
from django.views.decorators.csrf import ensure_csrf_cookie
from django.db.models import Q


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
    Return lessons for the user that have been unlocked but not yet started (srs_stage == LESSON).
    Supports ?limit=... query param.
    """
    limit = int(request.query_params.get("limit", 100))

    udes = (
        UserDictionaryEntry.objects
        .filter(user=request.user, srs_stage=SRSStage.LESSON)
        .select_related("entry")
        .order_by("entry__level", "entry__priority")[:limit]
    )

    serializer = UserDictionaryEntrySerializer(udes, many=True)
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

    udes = (
        UserDictionaryEntry.objects
        .filter(user=request.user)
        .exclude(srs_stage__in=[SRSStage.LOCKED, SRSStage.LESSON])
        .filter(next_review_at__lte=now)
        .select_related("entry")
        .order_by("entry__level", "entry__priority")[:limit]
    )

    serializer = UserDictionaryEntrySerializer(udes, many=True)
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

    # Map mistakes back into UDEs
    udes = [
        UserDictionaryEntry.objects.get_or_create(user=request.user, entry=rm.entry)[0]
        for rm in recent_mistakes
    ]

    serializer = UserDictionaryEntrySerializer(udes, many=True)
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

    process_planned_entries(request.user)

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


@api_view(['GET'])
def search(request):
    """
    Search DictionaryEntry by kanji, kana reading, or meaning.
    Supports ?q=<query>&limit=...
    """
    query = request.query_params.get("q", "").strip()
    limit = int(request.query_params.get("limit", 50)) # change this if necessary

    if not query:
        return Response({"error": "Missing 'q' parameter"}, status=400)

    entries = (
        DictionaryEntry.objects
        .filter(
            Q(literal__icontains=query) |
            Q(meaning__icontains=query) |
            Q(kunyomi_readings__icontains=query) |
            Q(onyomi_readings__icontains=query) |
            Q(readings__icontains=query)
        )
        .order_by("level", "priority")[:limit]
    )

    # For each result, get/create the corresponding UDE
    udes = [
        UserDictionaryEntry.objects.get_or_create(user=request.user, entry=e)[0]
        for e in entries
    ]

    serializer = UserDictionaryEntrySerializer(udes, many=True)
    return Response(serializer.data)


@api_view(['GET'])
def entry_detail(request, pk):
    try:
        entry = DictionaryEntry.objects.get(pk=pk)
    except DictionaryEntry.DoesNotExist:
        return Response({"error": "Not found"}, status=404)

    ude, _ = UserDictionaryEntry.objects.get_or_create(user=request.user, entry=entry)
    serializer = UserDictionaryEntrySerializer(ude)
    return Response(serializer.data)


@api_view(['POST'])
@permission_classes([IsAuthenticated])
def plan_add(request):
    entry_id = request.data.get("entry_id")
    if not entry_id:
        return Response({"error": "Missing entry_id"}, status=400)

    try:
        entry = DictionaryEntry.objects.get(id=entry_id)
    except DictionaryEntry.DoesNotExist:
        return Response({"error": "Entry not found"}, status=404)

    plan_entry(request.user, entry)
    return Response({"message": f"{entry.literal} planned"})


@api_view(['GET'])
@permission_classes([IsAuthenticated])
def get_planned(request):
    planned = PlannedEntry.objects.filter(user=request.user).select_related("entry")

    # Convert planned entries into UDEs for this user
    udes = [
        UserDictionaryEntry.objects.get_or_create(user=request.user, entry=p.entry)[0] for p in planned
    ]

    serializer = UserDictionaryEntrySerializer(udes, many=True)
    return Response(serializer.data)
