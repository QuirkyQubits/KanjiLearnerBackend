from collections import defaultdict
from datetime import datetime, timedelta
from datetime import timezone as dt_timezone
from django.utils import timezone as dj_timezone
from kanjilearner.constants import SRSStage
from kanjilearner.pagination import SearchPagination
from kanjilearner.services.plan import process_planned_entries
from rest_framework.decorators import api_view, permission_classes, throttle_classes
from rest_framework.permissions import IsAuthenticated, AllowAny
from rest_framework.response import Response
from rest_framework.throttling import AnonRateThrottle
from kanjilearner.models import DictionaryEntry, PlannedEntry, RecentMistake, UserDictionaryEntry
from kanjilearner.serializers import UserDictionaryEntrySerializer
from kanjilearner.services.plan import plan_entry
from zoneinfo import ZoneInfo
from django.contrib.auth import authenticate, login, logout
from django.contrib.auth.tokens import default_token_generator
from django.views.decorators.csrf import ensure_csrf_cookie
from django.db.models import Q
from django.middleware.csrf import get_token
from django.core.mail import send_mail
from django.contrib.auth.models import User
from django.conf import settings


class SignupRateThrottle(AnonRateThrottle):
    rate = "5/hour"  # limit to 5 attempts per IP per hour


@api_view(['GET'])
@ensure_csrf_cookie
def get_csrf_token(request):
    token = get_token(request)  # sets the CSRF cookie and returns the value
    return Response({"csrfToken": token})


@api_view(['GET'])
@permission_classes([IsAuthenticated])
def whoami(request):
    return Response({
        "username": request.user.username,
        "id": request.user.id,
    })


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


@api_view(['POST'])
@permission_classes([AllowAny])
def logout_view(request):
    logout(request)
    return Response({"message": "Logged out"})


@api_view(["POST"])
@permission_classes([AllowAny])
@throttle_classes([SignupRateThrottle])
def register_view(request):
    username = request.data.get("username")
    password = request.data.get("password")
    email = request.data.get("email")

    if not username or not password or not email:
        return Response({"error": "Username, password, and email required"}, status=400)

    if User.objects.filter(username=username).exists():
        return Response({"error": "Username already taken"}, status=400)

    if User.objects.filter(email=email).exists():
        return Response({"error": "Email already in use"}, status=400)

    # Create inactive user
    user = User.objects.create_user(username=username, password=password, email=email)
    user.is_active = False
    user.save()

    # Initialize all level=0 entries as burned
    level0_entries = DictionaryEntry.objects.filter(level=0)
    UserDictionaryEntry.objects.bulk_create([
        UserDictionaryEntry(
            user=user,
            entry=entry,
            srs_stage=SRSStage.BURNED,
            unlocked_at=dj_timezone.now(),
            next_review_at=None,
            last_reviewed_at=dj_timezone.now(),
        )
        for entry in level0_entries
    ], ignore_conflicts=True)

    # Generate a verification token
    token = default_token_generator.make_token(user)
    verification_link = f"{settings.FRONTEND_URL}/verify-email/{user.pk}/{token}/"

    # Send email (using Django’s email backend)
    send_mail(
        "Verify your KanjiLearner account",
        f"Click the link to verify your account: {verification_link}",
        settings.DEFAULT_FROM_EMAIL,
        [email],
        fail_silently=False,
    )

    return Response({"message": "User registered. Please check your email to verify your account."})


@api_view(["GET"])
@permission_classes([AllowAny])
def verify_email(request, uid, token):
    try:
        user = User.objects.get(pk=uid)
    except User.DoesNotExist:
        return Response({"error": "Invalid user"}, status=400)

    if user.is_active:
        return Response(
            {"error": "This verification link has already been used. Please log in instead."},
            status=400,
        )

    if default_token_generator.check_token(user, token):
        user.is_active = True
        user.save()

        #  Ensure level 0 entries are initialized as burned
        level0_entries = DictionaryEntry.objects.filter(level=0)
        for entry in level0_entries:
            # See if one already exists for this (user, entry)
            exists = UserDictionaryEntry.objects.filter(user=user, entry=entry).exists()
            if not exists:
                UserDictionaryEntry.objects.create(
                    user=user,
                    entry=entry,
                    srs_stage=SRSStage.BURNED,
                    unlocked_at=dj_timezone.now(),
                    last_reviewed_at=dj_timezone.now(),
                )

        login(request, user)  # auto-login after verification
        return Response({"message": "Email verified, account activated"})
    else:
        return Response({"error": "Invalid or expired verification link"}, status=400)


@api_view(["DELETE"])
@permission_classes([IsAuthenticated])
def delete_account(request):
    """
    Delete the authenticated user and cascade delete all related data.
    """
    user = request.user
    username = user.username
    user.delete()  # Cascade deletes UserDictionaryEntry, RecentMistake, PlannedEntry, etc.

    return Response({"message": f"Account '{username}' and all related data deleted."})


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
        .order_by("entry__level")[:limit]
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
        .order_by("entry__level")[:limit]
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

    # Purge old mistakes beyond 24h so they don’t linger in DB
    RecentMistake.objects.filter(user=request.user, timestamp__lt=cutoff).delete()

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
    Return upcoming reviews for the next 7 days,
    bucketed by local date (YYYY-MM-DD) and hour (00-23).
    Counts include a global cumulative total that rolls forward across all days.
    Always includes all 7 days and 24 hours, even if count=0.
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

    # Range: now → 7 days from now (local 23:59:59)
    local_end = (now_local + timedelta(days=7)).replace(
        hour=23, minute=59, second=59, microsecond=0
    )
    utc_start = now_local.astimezone(dt_timezone.utc)
    utc_end = local_end.astimezone(dt_timezone.utc)

    # Get reviews due in this 7-day window
    upcoming_reviews = (
        UserDictionaryEntry.objects
        .filter(user=request.user)
        .exclude(srs_stage__in=[SRSStage.LOCKED, SRSStage.LESSON, SRSStage.BURNED])
        .filter(next_review_at__gt=utc_start, next_review_at__lte=utc_end)
        .values_list("next_review_at", flat=True)
    )

    # Bucket counts by (day, hour)
    raw_buckets = defaultdict(lambda: defaultdict(int))
    for dt in upcoming_reviews:
        local_dt = dt.astimezone(user_tz)
        day_str = local_dt.strftime("%Y-%m-%d")
        hour_str = f"{local_dt.hour:02d}"
        raw_buckets[day_str][hour_str] += 1

    # Build result: always 7 days × 24 hours
    result = {}
    cumulative = 0
    for offset in range(7):
        day = (now_local + timedelta(days=offset)).date()
        day_str = day.strftime("%Y-%m-%d")
        result[day_str] = {}
        for hour in [f"{h:02d}" for h in range(24)]:
            count = raw_buckets.get(day_str, {}).get(hour, 0)
            cumulative += count
            result[day_str][hour] = {"count": count, "cumulative": cumulative}

    return Response(result)


@api_view(['GET'])
@permission_classes([IsAuthenticated])
def search(request):
    """
    Search DictionaryEntry by kanji, kana reading, or meaning.
    Supports ?q=<query>&page=<n>&page_size=<m>.
    """
    query = request.query_params.get("q", "").strip()
    if not query:
        return Response({"error": "Missing 'q' parameter"}, status=400)

    qs = DictionaryEntry.objects.filter(
        Q(literal__icontains=query) |
        Q(meaning__icontains=query) |
        Q(kunyomi_readings__icontains=query) |
        Q(onyomi_readings__icontains=query) |
        Q(reading__icontains=query)
    ).order_by("level", "id")

    paginator = SearchPagination()
    page = paginator.paginate_queryset(qs, request)

    # Map results into UDEs (create if needed)
    udes = [
        UserDictionaryEntry.objects.get_or_create(user=request.user, entry=e)[0]
        for e in page
    ]

    serializer = UserDictionaryEntrySerializer(udes, many=True)
    return paginator.get_paginated_response(serializer.data)


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
