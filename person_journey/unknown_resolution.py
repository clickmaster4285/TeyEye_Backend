"""Resolve unknown persons — track, bbox, and appearance matching."""

from __future__ import annotations

from datetime import timedelta

from django.conf import settings
from django.utils import timezone

from .matching import find_best_match
from .models import CameraTrack, JourneyEvent, JourneyPerson, PersonStatus, PersonType, TrackStatus
from .services import _camera_zone, create_journey_person

_BBOX_IOU_THRESHOLD = 0.22
_BBOX_CENTER_THRESHOLD = 0.55
_BBOX_MATCH_SECONDS = 900
_TRACK_MATCH_MINUTES = 20


def bbox_iou(a: list, b: list) -> float:
    if not a or not b or len(a) < 4 or len(b) < 4:
        return 0.0
    try:
        ax1, ay1, ax2, ay2 = (float(v) for v in a[:4])
        bx1, by1, bx2, by2 = (float(v) for v in b[:4])
    except (TypeError, ValueError):
        return 0.0
    ix1 = max(ax1, bx1)
    iy1 = max(ay1, by1)
    ix2 = min(ax2, bx2)
    iy2 = min(ay2, by2)
    inter = max(0.0, ix2 - ix1) * max(0.0, iy2 - iy1)
    if inter <= 0:
        return 0.0
    area_a = max(0.0, ax2 - ax1) * max(0.0, ay2 - ay1)
    area_b = max(0.0, bx2 - bx1) * max(0.0, by2 - by1)
    union = area_a + area_b - inter
    return inter / union if union > 0 else 0.0


def bbox_center_distance(a: list, b: list) -> float:
    """Normalized center distance (0 = same spot, 1+ = far apart)."""
    if not a or not b or len(a) < 4 or len(b) < 4:
        return 999.0
    try:
        ax1, ay1, ax2, ay2 = (float(v) for v in a[:4])
        bx1, by1, bx2, by2 = (float(v) for v in b[:4])
    except (TypeError, ValueError):
        return 999.0
    acx, acy = (ax1 + ax2) / 2.0, (ay1 + ay2) / 2.0
    bcx, bcy = (bx1 + bx2) / 2.0, (by1 + by2) / 2.0
    diag = max(
        ((ax2 - ax1) ** 2 + (ay2 - ay1) ** 2) ** 0.5,
        ((bx2 - bx1) ** 2 + (by2 - by1) ** 2) ** 0.5,
        80.0,
    )
    return (((acx - bcx) ** 2 + (acy - bcy) ** 2) ** 0.5) / diag


def bboxes_match(a: list, b: list) -> bool:
    if bbox_iou(a, b) >= _BBOX_IOU_THRESHOLD:
        return True
    return bbox_center_distance(a, b) <= _BBOX_CENTER_THRESHOLD


def journey_pipeline_handles_unknowns() -> bool:
    return bool(getattr(settings, "PERSON_JOURNEY_WORKER_ENABLED", False))


def journey_pipeline_active() -> bool:
    """True when ML journey API is reachable (ByteTrack+ReID pipelines running)."""
    if not journey_pipeline_handles_unknowns():
        return False
    try:
        from ml.client import _request, ml_service_enabled

        if not ml_service_enabled():
            return False
        res = _request("GET", "/journey/status", timeout=(1.0, 2.0))
        return res.status_code == 200
    except Exception:
        return False


def live_ingest_unknowns_enabled() -> bool:
    explicit = str(getattr(settings, "PERSON_JOURNEY_LIVE_INGEST_UNKNOWN_ENABLED", "")).strip().lower()
    if explicit in ("true", "1", "yes"):
        return True
    if explicit in ("false", "0", "no"):
        return False
    if journey_pipeline_active():
        return False
    return bool(getattr(settings, "PERSON_JOURNEY_LIVE_INGEST_ENABLED", True))


def generic_unknown_handled_elsewhere() -> bool:
    return live_ingest_unknowns_enabled() or journey_pipeline_active()


def match_unknown_by_track(camera, track_id, now=None) -> JourneyPerson | None:
    if not track_id or not camera:
        return None
    now = now or timezone.now()
    try:
        track_id = int(track_id)
    except (TypeError, ValueError):
        return None

    active = (
        CameraTrack.objects.filter(
            camera=camera,
            track_id=track_id,
            status=TrackStatus.ACTIVE,
            journey_person__person_type=PersonType.UNKNOWN,
            journey_person__status=PersonStatus.ACTIVE,
        )
        .select_related("journey_person")
        .order_by("-started_at")
        .first()
    )
    if active:
        return active.journey_person

    since = now - timedelta(minutes=_TRACK_MATCH_MINUTES)
    recent = (
        CameraTrack.objects.filter(
            camera=camera,
            track_id=track_id,
            journey_person__person_type=PersonType.UNKNOWN,
            journey_person__status=PersonStatus.ACTIVE,
            started_at__gte=since,
        )
        .select_related("journey_person")
        .order_by("-started_at")
        .first()
    )
    return recent.journey_person if recent else None


def match_unknown_by_bbox(
    camera,
    bbox: list,
    now,
    frame_slots: list[tuple[list, JourneyPerson]] | None = None,
) -> JourneyPerson | None:
    for slot_bbox, person in frame_slots or []:
        if bboxes_match(bbox, slot_bbox):
            return person

    if not camera or not bbox:
        return None

    since = now - timedelta(seconds=_BBOX_MATCH_SECONDS)
    tracks = (
        CameraTrack.objects.filter(
            camera=camera,
            status=TrackStatus.ACTIVE,
            journey_person__person_type=PersonType.UNKNOWN,
            journey_person__status=PersonStatus.ACTIVE,
            started_at__gte=since,
        )
        .select_related("journey_person")
        .order_by("-started_at")[:60]
    )
    for track in tracks:
        if bboxes_match(bbox, track.last_bbox or []):
            return track.journey_person

    recent = (
        JourneyEvent.objects.filter(
            journey_person__person_type=PersonType.UNKNOWN,
            journey_person__status=PersonStatus.ACTIVE,
            camera=camera,
            created_at__gte=since,
        )
        .select_related("journey_person")
        .order_by("-created_at")[:120]
    )
    for ev in recent:
        if bboxes_match(bbox, ev.bbox or []):
            return ev.journey_person
    return None


def match_unknown_by_appearance(
    *,
    face_embedding: list[float] | None,
    reid_embedding: list[float] | None,
    camera_id: int | None,
) -> JourneyPerson | None:
    if not face_embedding and not reid_embedding:
        return None
    match = find_best_match(
        face_embedding=face_embedding or None,
        reid_embedding=reid_embedding or None,
        camera_id=camera_id,
        person_type_hint=PersonType.UNKNOWN,
    )
    return match.person if match else None


def resolve_unknown_person(
    *,
    camera,
    bbox: list,
    now,
    frame_slots: list[tuple[list, JourneyPerson]] | None = None,
    track_id=None,
    face_embedding: list[float] | None = None,
    reid_embedding: list[float] | None = None,
    source: str = "live_ingest",
) -> tuple[JourneyPerson, bool]:
    """Return (person, created). Reuse identity via track, bbox, or appearance."""
    matched = match_unknown_by_track(camera, track_id, now)
    if matched is None:
        matched = match_unknown_by_bbox(camera, bbox, now, frame_slots)
    if matched is None:
        matched = match_unknown_by_appearance(
            face_embedding=face_embedding,
            reid_embedding=reid_embedding,
            camera_id=camera.pk if camera else None,
        )

    if matched:
        if reid_embedding and not matched.reid_embedding:
            matched.reid_embedding = reid_embedding
            matched.save(update_fields=["reid_embedding", "updated_at"])
        if face_embedding and not matched.face_embedding:
            matched.face_embedding = face_embedding
            matched.save(update_fields=["face_embedding", "updated_at"])
        return matched, False

    person = create_journey_person(
        person_type=PersonType.UNKNOWN,
        display_name="Unknown",
        face_embedding=face_embedding or [],
        reid_embedding=reid_embedding or [],
        latest_camera=camera,
        latest_zone=_camera_zone(camera),
        latest_seen_at=now,
        status=PersonStatus.ACTIVE,
        metadata={"source": source, "camera_id": camera.pk if camera else None, "track_id": track_id},
    )
    person.display_name = f"Unknown — {person.code}"
    person.save(update_fields=["display_name", "updated_at"])
    return person, True


def update_person_embeddings_from_crop(person: JourneyPerson, crop_bytes: bytes) -> list[float]:
    """Extract ReID from a person crop and store on the journey person."""
    from .reid_utils import extract_reid_embedding_from_bytes

    reid = extract_reid_embedding_from_bytes(crop_bytes)
    if not reid:
        return []
    if not person.reid_embedding:
        person.reid_embedding = reid
        person.save(update_fields=["reid_embedding", "updated_at"])
    return reid
