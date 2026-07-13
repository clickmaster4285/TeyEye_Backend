"""Journey ingestion — assign Person UUID, tracks, and timeline events."""

from __future__ import annotations

import logging
from datetime import timedelta
from typing import Any

from django.conf import settings
from django.db import transaction
from django.utils import timezone

from cameras.models import Camera

from .matching import find_best_match, resolve_staff_from_face_label
from .models import (
    CameraTrack,
    JourneyEvent,
    JourneyEventType,
    JourneyPerson,
    PersonStatus,
    PersonType,
    TrackStatus,
)

logger = logging.getLogger(__name__)

_WEAPON_CLASSES = frozenset(
    {
        "weapon",
        "gun",
        "knife",
        "pistol",
        "rifle",
        "firearm",
        "sword",
        "machete",
    }
)


def _code_prefix(person_type: str) -> str:
    return {"staff": "P", "visitor": "V", "unknown": "U"}.get(person_type, "U")


def _allocate_code_lock(person_type: str) -> None:
    """Serialize code generation across concurrent ingest workers."""
    from django.db import connection

    if connection.vendor == "postgresql":
        with connection.cursor() as cursor:
            cursor.execute(
                "SELECT pg_advisory_xact_lock(hashtext(%s))",
                [f"journey_person_code:{person_type}"],
            )
        return

    JourneyPerson.objects.select_for_update().filter(person_type=person_type).order_by("-id").first()


def _max_code_seq(prefix: str) -> int:
    max_seq = 0
    for code in JourneyPerson.objects.filter(code__startswith=prefix).values_list("code", flat=True):
        try:
            n = int("".join(c for c in code if c.isdigit()) or "0")
        except ValueError:
            continue
        max_seq = max(max_seq, n)
    return max_seq


def _next_code(person_type: str) -> str:
    """Allocate the next person code (must run inside the caller's transaction)."""
    prefix = _code_prefix(person_type)
    _allocate_code_lock(person_type)
    return f"{prefix}{_max_code_seq(prefix) + 1}"


def create_journey_person(*, person_type: str, max_attempts: int = 12, **fields) -> JourneyPerson:
    """Create a journey person, retrying if two workers race on the same code."""
    import time

    from django.db import IntegrityError

    if "code" in fields:
        return JourneyPerson.objects.create(person_type=person_type, **fields)

    last_exc: IntegrityError | None = None
    for attempt in range(max_attempts):
        try:
            create_fields = {**fields, "code": _next_code(person_type)}
            return JourneyPerson.objects.create(person_type=person_type, **create_fields)
        except IntegrityError as exc:
            last_exc = exc
            err = str(exc).lower()
            if "code" not in err and "journeyperson" not in err:
                raise
            if attempt >= max_attempts - 1:
                raise
            logger.warning(
                "Journey person code collision (attempt %s/%s, type=%s): %s",
                attempt + 1,
                max_attempts,
                person_type,
                exc,
            )
            time.sleep(0.025 * (attempt + 1))
    raise RuntimeError("Could not allocate unique journey person code") from last_exc


def _camera_zone(camera: Camera | None) -> str:
    if camera is None:
        return ""
    return (camera.zone or camera.name or "").strip()


@transaction.atomic
def ingest_track_observation(payload: dict[str, Any]) -> dict[str, Any]:
    """
    Process one tracked person observation from the ML journey pipeline.

    Expected payload keys:
      camera_id, camera_key, track_id, track_status, bbox, confidence,
      face_embedding, reid_embedding, face_label, face_match_score,
      detections (list of extra class detections e.g. weapon),
      snapshot_path, frame_timestamp
    """
    camera_id = payload.get("camera_id")
    camera_key = str(payload.get("camera_key") or "").strip()
    track_id = int(payload.get("track_id") or 0)
    track_status = str(payload.get("track_status") or "active").strip().lower()
    bbox = payload.get("bbox") or []
    confidence = float(payload.get("confidence") or 0)
    face_embedding = payload.get("face_embedding") or []
    reid_embedding = payload.get("reid_embedding") or []
    face_label = str(payload.get("face_label") or "").strip()
    face_match_score = payload.get("face_match_score")
    extra_detections = payload.get("detections") or []
    snapshot_path = str(payload.get("snapshot_path") or "").strip()
    now = timezone.now()

    camera: Camera | None = None
    if camera_id:
        camera = Camera.objects.filter(pk=camera_id, is_active=True).first()
    if camera is None and camera_key:
        key = camera_key.replace("cam-", "")
        if key.isdigit():
            camera = Camera.objects.filter(pk=int(key), is_active=True).first()

    staff_id, staff_name = resolve_staff_from_face_label(face_label)
    person_type_hint = PersonType.STAFF if staff_id else PersonType.UNKNOWN

    person: JourneyPerson | None = None
    created_person = False

    if camera and track_id:
        active_track = (
            CameraTrack.objects.filter(
                camera=camera,
                track_id=track_id,
                status=TrackStatus.ACTIVE,
                journey_person__status=PersonStatus.ACTIVE,
            )
            .select_related("journey_person")
            .order_by("-started_at")
            .first()
        )
        if active_track:
            person = active_track.journey_person

    match = None
    if person is None:
        match = find_best_match(
            face_embedding=face_embedding or None,
            reid_embedding=reid_embedding or None,
            camera_id=camera.pk if camera else None,
            person_type_hint=person_type_hint if not staff_id else None,
            staff_id=staff_id,
        )
        person = match.person if match else None

    if person is None and staff_id:
        person = JourneyPerson.objects.filter(staff_id=staff_id, status=PersonStatus.ACTIVE).first()

    if person is None:
        person_type = PersonType.STAFF if staff_id else PersonType.UNKNOWN
        display = staff_name or face_label or f"Unknown — {track_id}"
        if person_type == PersonType.UNKNOWN:
            display = "Unknown"
        person = create_journey_person(
            person_type=person_type,
            display_name=display,
            staff_id=staff_id,
            face_embedding=face_embedding or [],
            reid_embedding=reid_embedding or [],
            latest_camera=camera,
            latest_zone=_camera_zone(camera),
            latest_seen_at=now,
            status=PersonStatus.ACTIVE,
        )
        if person_type == PersonType.UNKNOWN:
            person.display_name = f"Unknown — {person.code}"
            person.save(update_fields=["display_name", "updated_at"])
        created_person = True
        created_event = JourneyEvent.objects.create(
            journey_person=person,
            event_type=JourneyEventType.UNKNOWN_CREATED
            if person_type == PersonType.UNKNOWN
            else JourneyEventType.STAFF_RECOGNIZED,
            title="Unknown person created" if person_type == PersonType.UNKNOWN else f"Staff recognized: {staff_name}",
            camera=camera,
            zone=_camera_zone(camera),
            confidence=confidence,
            match_score=match.combined_score if match else None,
            bbox=bbox,
            snapshot_path=snapshot_path,
            metadata={"track_id": track_id, "face_label": face_label, "source": "journey_pipeline"},
        )
        if camera:
            from .snapshot_capture import schedule_journey_snapshot

            schedule_journey_snapshot(created_event.pk, None, camera.pk)
    else:
        updates: list[str] = ["latest_seen_at", "updated_at"]
        person.latest_seen_at = now
        if camera:
            person.latest_camera = camera
            person.latest_zone = _camera_zone(camera)
            updates.extend(["latest_camera", "latest_zone"])
        if face_embedding and (not person.face_embedding or staff_id):
            person.face_embedding = face_embedding
            updates.append("face_embedding")
        if reid_embedding:
            person.reid_embedding = reid_embedding
            updates.append("reid_embedding")
        if staff_id and person.staff_id is None:
            person.staff_id = staff_id
            person.person_type = PersonType.STAFF
            person.display_name = staff_name or person.display_name
            updates.extend(["staff_id", "person_type", "display_name"])
        person.save(update_fields=list(dict.fromkeys(updates)))

    track = (
        CameraTrack.objects.filter(
            camera=camera,
            track_id=track_id,
            status=TrackStatus.ACTIVE,
            journey_person=person,
        )
        .order_by("-started_at")
        .first()
    )
    if track is None:
        track = CameraTrack.objects.create(
            journey_person=person,
            camera=camera,
            track_id=track_id,
            status=TrackStatus.ACTIVE if track_status == "active" else TrackStatus.FINISHED,
            started_at=now,
            ended_at=None if track_status == "active" else now,
            last_bbox=bbox,
            metadata={"camera_key": camera_key},
        )
    else:
        track.last_bbox = bbox
        if track_status == "finished":
            track.status = TrackStatus.FINISHED
            track.ended_at = now
            track.save(update_fields=["last_bbox", "status", "ended_at"])
        else:
            track.save(update_fields=["last_bbox"])

    event_type = JourneyEventType.CAMERA_DETECTION
    title = f"Seen at {camera.name if camera else camera_key}"
    if staff_id:
        event_type = JourneyEventType.STAFF_RECOGNIZED
        title = f"Recognized: {staff_name}"

    dedup_seconds = float(getattr(settings, "PERSON_JOURNEY_INGEST_DEDUP_SECONDS", 3))
    recent_exists = False
    if person and camera and track:
        recent_exists = JourneyEvent.objects.filter(
            journey_person=person,
            camera=camera,
            track=track,
            created_at__gte=now - timedelta(seconds=dedup_seconds),
        ).exists()

    if not recent_exists:
        detection_event = JourneyEvent.objects.create(
            journey_person=person,
            event_type=event_type,
            title=title,
            description=f"Track {track_id} on {camera.name if camera else camera_key}",
            camera=camera,
            zone=_camera_zone(camera),
            track=track,
            confidence=confidence,
            match_score=match.combined_score if match else face_match_score,
            bbox=bbox,
            snapshot_path=snapshot_path,
            metadata={
                "track_id": track_id,
                "track_status": track_status,
                "face_label": face_label,
                "face_match_score": face_match_score,
                "match_face": match.face_score if match else None,
                "match_reid": match.reid_score if match else None,
                "created_person": created_person,
                "source": "journey_pipeline",
            },
        )
        if camera:
            from .snapshot_capture import schedule_journey_snapshot

            schedule_journey_snapshot(detection_event.pk, None, camera.pk)

    for det in extra_detections:
        cls = str(det.get("class_name") or det.get("label") or "").strip().lower()
        if cls in _WEAPON_CLASSES or det.get("alert"):
            JourneyEvent.objects.create(
                journey_person=person,
                event_type=JourneyEventType.WEAPON_DETECTED if cls in _WEAPON_CLASSES else JourneyEventType.ALERT,
                title=f"Weapon detected: {cls}" if cls in _WEAPON_CLASSES else f"Alert: {cls}",
                camera=camera,
                zone=_camera_zone(camera),
                track=track,
                confidence=float(det.get("confidence") or 0),
                bbox=det.get("bbox") or [],
                metadata={"detection": det},
            )

    if track_status == "finished":
        pass

    return {
        "person_uuid": str(person.uuid),
        "person_code": person.code,
        "person_type": person.person_type,
        "display_name": person.display_name,
        "track_id": track_id,
        "created_person": created_person,
        "match_score": match.combined_score if match else None,
    }


@transaction.atomic
def merge_person_to_visitor(
    person_uuid: str,
    visitor_id: int,
    *,
    face_match_score: float | None = None,
) -> JourneyPerson | None:
    """Step 15 — link unknown journey person to a registered visitor."""
    from visitors.models import Visitor

    person = JourneyPerson.objects.filter(uuid=person_uuid).select_for_update().first()
    if person is None:
        return None
    visitor = Visitor.objects.filter(pk=visitor_id).first()
    if visitor is None:
        return None

    old_code = person.code
    person.visitor_id = visitor.pk
    person.person_type = PersonType.VISITOR
    person.display_name = visitor.full_name
    person.code = f"V{visitor.pk}"
    person.save(update_fields=["visitor_id", "person_type", "display_name", "code", "updated_at"])

    JourneyEvent.objects.create(
        journey_person=person,
        event_type=JourneyEventType.PERSON_MERGED,
        title=f"Linked to visitor {visitor.full_name}",
        description=f"Unknown {old_code} merged to visitor V{visitor.pk}",
        confidence=face_match_score,
        match_score=face_match_score,
        metadata={"previous_code": old_code, "visitor_id": visitor.pk},
    )
    return person


@transaction.atomic
def register_staff_journey_person(staff) -> JourneyPerson:
    """Ensure a staff member has a journey person registry entry."""
    existing = JourneyPerson.objects.filter(staff_id=staff.pk, status=PersonStatus.ACTIVE).first()
    if existing:
        return existing

    face_emb = []
    if isinstance(staff.face_embedding, list):
        face_emb = staff.face_embedding

    return JourneyPerson.objects.create(
        code=f"P{staff.pk}",
        person_type=PersonType.STAFF,
        display_name=staff.full_name or "",
        staff_id=staff.pk,
        face_embedding=face_emb,
        status=PersonStatus.ACTIVE,
    )
