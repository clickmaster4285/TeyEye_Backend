from __future__ import annotations

from datetime import timedelta

from django.db.models import Count, Q
from django.utils import timezone
from rest_framework import generics, permissions, status
from rest_framework.response import Response
from rest_framework.views import APIView

from .models import JourneyEvent, JourneyPerson, PersonStatus, PersonType
from .serializers import (
    IngestObservationSerializer,
    JourneyEventSerializer,
    JourneyPersonDetailSerializer,
    JourneyPersonListSerializer,
    MergeVisitorSerializer,
)
from .services import ingest_track_observation, merge_person_to_visitor
from .snapshot_utils import person_camera_captures, serializer_context_for_events


def _clip_context_for_events(events, person=None) -> dict:
    return serializer_context_for_events(list(events), person=person)


class JourneyIngestAPIView(APIView):
    """POST /api/person-journey/ingest/ — ML pipeline observation intake."""

    permission_classes = [permissions.AllowAny]

    def post(self, request):
        from django.conf import settings

        expected = getattr(settings, "PERSON_JOURNEY_INGEST_TOKEN", "").strip()
        if expected:
            token = (request.headers.get("X-Journey-Ingest-Token") or "").strip()
            if token != expected:
                return Response({"detail": "Invalid ingest token."}, status=status.HTTP_403_FORBIDDEN)

        ser = IngestObservationSerializer(data=request.data)
        if not ser.is_valid():
            return Response(ser.errors, status=status.HTTP_400_BAD_REQUEST)
        result = ingest_track_observation(ser.validated_data)
        return Response(result, status=status.HTTP_201_CREATED)


class JourneyPersonListAPIView(generics.ListAPIView):
    permission_classes = [permissions.IsAuthenticated]
    serializer_class = JourneyPersonListSerializer

    def get_queryset(self):
        qs = JourneyPerson.objects.select_related("staff", "visitor", "latest_camera").all()
        person_type = self.request.query_params.get("person_type")
        if person_type:
            qs = qs.filter(person_type=person_type.strip())
        status_param = self.request.query_params.get("status")
        if status_param:
            qs = qs.filter(status=status_param.strip())
        active_only = self.request.query_params.get("active_only")
        if active_only and str(active_only).lower() in ("1", "true", "yes"):
            qs = qs.filter(status=PersonStatus.ACTIVE)
        q = self.request.query_params.get("q", "").strip()
        if q:
            qs = qs.filter(
                Q(code__icontains=q)
                | Q(display_name__icontains=q)
                | Q(latest_zone__icontains=q)
            )
        return qs.order_by("-latest_seen_at", "-created_at")


class JourneyPersonDetailAPIView(generics.RetrieveAPIView):
    permission_classes = [permissions.IsAuthenticated]
    serializer_class = JourneyPersonDetailSerializer
    lookup_field = "uuid"

    def get_queryset(self):
        return JourneyPerson.objects.select_related(
            "staff", "visitor", "latest_camera"
        ).prefetch_related("events__camera", "tracks__camera")

    def retrieve(self, request, *args, **kwargs):
        instance = self.get_object()
        events = list(instance.events.all())
        context = self.get_serializer_context()
        context.update(_clip_context_for_events(events, person=instance))
        serializer = self.get_serializer(instance, context=context)
        return Response(serializer.data)


class JourneyPersonTimelineAPIView(APIView):
    permission_classes = [permissions.IsAuthenticated]

    def get(self, request, uuid):
        try:
            person = JourneyPerson.objects.get(uuid=uuid)
        except JourneyPerson.DoesNotExist:
            return Response({"detail": "Person not found."}, status=status.HTTP_404_NOT_FOUND)

        from .snapshot_utils import backfill_snapshot_paths_for_person

        backfill_snapshot_paths_for_person(person)

        refresh = str(request.query_params.get("refresh", "")).lower() in ("1", "true", "yes")
        if refresh:
            from .snapshot_capture import capture_missing_for_person

            capture_missing_for_person(person, since=None, limit=15, timeout=35.0)

        events = JourneyEvent.objects.filter(journey_person=person).select_related("camera")
        date_from = request.query_params.get("date_from")
        date_to = request.query_params.get("date_to")
        if date_from:
            events = events.filter(created_at__date__gte=date_from)
        if date_to:
            events = events.filter(created_at__date__lte=date_to)

        events = events.order_by("created_at")
        events_list = list(events)
        ctx = _clip_context_for_events(events_list, person=person)
        return Response(
            {
                "person": JourneyPersonListSerializer(person).data,
                "events": JourneyEventSerializer(events_list, many=True, context=ctx).data,
            }
        )


class JourneyLiveAPIView(APIView):
    """Active persons seen in the last N minutes."""

    permission_classes = [permissions.IsAuthenticated]

    def get(self, request):
        minutes = 30
        try:
            minutes = int(request.query_params.get("minutes", 30))
        except (TypeError, ValueError):
            pass
        since = timezone.now() - timedelta(minutes=max(1, minutes))
        qs = (
            JourneyPerson.objects.filter(latest_seen_at__gte=since)
            .select_related("latest_camera", "staff", "visitor")
            .order_by("-latest_seen_at")[:100]
        )
        results = list(qs)
        return Response(
            {
                "count": len(results),
                "results": JourneyPersonListSerializer(results, many=True).data,
            }
        )


class JourneySummaryAPIView(APIView):
    permission_classes = [permissions.IsAuthenticated]

    def get(self, request):
        today = timezone.localdate()
        since = timezone.now() - timedelta(hours=24)
        return Response(
            {
                "active_now": JourneyPerson.objects.filter(status=PersonStatus.ACTIVE).count(),
                "unknown_today": JourneyPerson.objects.filter(
                    person_type=PersonType.UNKNOWN,
                    created_at__date=today,
                ).count(),
                "staff_recognized_24h": JourneyEvent.objects.filter(
                    event_type="staff_recognized",
                    created_at__gte=since,
                ).count(),
                "events_24h": JourneyEvent.objects.filter(created_at__gte=since).count(),
                "by_type": {
                    row["person_type"]: row["c"]
                    for row in JourneyPerson.objects.filter(latest_seen_at__gte=since)
                    .values("person_type")
                    .annotate(c=Count("id"))
                },
            }
        )


class JourneyMergeVisitorAPIView(APIView):
    permission_classes = [permissions.IsAuthenticated]

    def post(self, request):
        ser = MergeVisitorSerializer(data=request.data)
        if not ser.is_valid():
            return Response(ser.errors, status=status.HTTP_400_BAD_REQUEST)
        person = merge_person_to_visitor(
            str(ser.validated_data["person_uuid"]),
            ser.validated_data["visitor_id"],
            face_match_score=ser.validated_data.get("face_match_score"),
        )
        if person is None:
            return Response({"detail": "Merge failed."}, status=status.HTTP_400_BAD_REQUEST)
        return Response(JourneyPersonListSerializer(person).data)


class JourneyPersonCameraCapturesAPIView(APIView):
    """Latest capture image per camera for one journey person."""

    permission_classes = [permissions.IsAuthenticated]

    def get(self, request, uuid):
        try:
            person = JourneyPerson.objects.get(uuid=uuid)
        except JourneyPerson.DoesNotExist:
            return Response({"detail": "Person not found."}, status=status.HTTP_404_NOT_FOUND)

        hours = 48
        try:
            hours = int(request.query_params.get("hours", 48))
        except (TypeError, ValueError):
            pass
        since = timezone.now() - timedelta(hours=max(1, hours))

        from .snapshot_utils import backfill_snapshot_paths_for_person

        backfill_snapshot_paths_for_person(person)

        refresh = str(request.query_params.get("refresh", "")).lower() in ("1", "true", "yes")
        if refresh:
            from .snapshot_capture import capture_missing_for_person

            capture_missing_for_person(person, since=since, limit=12, timeout=30.0)

        captures = person_camera_captures(person, since=since)

        return Response(
            {
                "person": JourneyPersonListSerializer(person).data,
                "count": len(captures),
                "results": captures,
            }
        )


class JourneyCameraSightingsAPIView(APIView):
    """Latest captured sighting per camera (with snapshot)."""

    permission_classes = [permissions.IsAuthenticated]

    def get(self, request):
        hours = 2
        try:
            hours = int(request.query_params.get("hours", 2))
        except (TypeError, ValueError):
            pass
        since = timezone.now() - timedelta(hours=max(1, hours))
        events = (
            JourneyEvent.objects.filter(
                created_at__gte=since,
                camera__isnull=False,
                detection_event_id__isnull=False,
            )
            .select_related("camera", "journey_person")
            .order_by("camera_id", "-created_at")
        )
        seen: set[int] = set()
        latest_per_camera: list[JourneyEvent] = []
        for ev in events:
            if ev.camera_id in seen:
                continue
            seen.add(ev.camera_id)
            latest_per_camera.append(ev)

        ctx = _clip_context_for_events(latest_per_camera)
        return Response(
            {
                "count": len(latest_per_camera),
                "results": JourneyEventSerializer(latest_per_camera, many=True, context=ctx).data,
            }
        )


class JourneyRecentEventsAPIView(APIView):
    """Recent journey events with snapshots (all cameras)."""

    permission_classes = [permissions.IsAuthenticated]

    def get(self, request):
        limit = 40
        try:
            limit = int(request.query_params.get("limit", 40))
        except (TypeError, ValueError):
            pass
        limit = min(max(limit, 1), 100)
        events = list(
            JourneyEvent.objects.filter(
                camera__isnull=False,
                detection_event_id__isnull=False,
            )
            .select_related("camera", "journey_person")
            .order_by("-created_at")[:limit]
        )
        ctx = _clip_context_for_events(events)
        return Response(
            {
                "count": len(events),
                "results": JourneyEventSerializer(events, many=True, context=ctx).data,
            }
        )
