"""Bridge existing DetectionEvent rows into Person Journey (no changes to cameras app)."""

from __future__ import annotations

import logging
from datetime import timedelta

from django.db import transaction
from django.utils import timezone

from .matching import resolve_staff_from_face_label
from .models import JourneyEvent, JourneyEventType, JourneyPerson, PersonStatus, PersonType
from .services import _camera_zone, create_journey_person, register_staff_journey_person
from .unknown_resolution import generic_unknown_handled_elsewhere, resolve_unknown_person

logger = logging.getLogger(__name__)

_GENERIC_LABELS = frozenset({"unknown", "person", "face", ""})
_NON_PERSON_CLASSES = frozenset(
    {
        "chair",
        "laptop",
        "car",
        "dog",
        "cat",
        "mouse",
        "keyboard",
        "cell phone",
        "bottle",
        "cup",
        "book",
        "clock",
        "tv",
        "monitor",
        "backpack",
        "handbag",
        "suitcase",
        "umbrella",
        "tie",
        "fire",
        "smoke",
        "helmet",
        "vest",
        "hardhat",
    }
)
_WEAPON_CLASSES = frozenset({"weapon", "gun", "knife", "pistol", "rifle", "firearm"})
_BRIDGE_DEDUP_SECONDS = 5


def _generic_unknown_handled_elsewhere() -> bool:
    return generic_unknown_handled_elsewhere()


def _is_person_detection(class_name: str, label: str, employee_name: str = "") -> bool:
    """Person / face / recognized staff / named individual — not objects or weapons."""
    cls = (class_name or "").strip().lower()
    lbl = (label or "").strip().lower()
    emp = (employee_name or "").strip()

    if cls in _WEAPON_CLASSES:
        return False
    if cls in _NON_PERSON_CLASSES:
        return False
    if cls in ("person", "face"):
        return True
    if emp:
        return True
    if lbl in ("person", "face", "unknown"):
        return cls not in _NON_PERSON_CLASSES
    # Named labels (e.g. staff face) only when the detector class is person/face.
    if lbl and lbl not in _GENERIC_LABELS:
        return cls in ("person", "face") or bool(emp)
    return False


def _match_unknown_by_track(instance, camera, now) -> JourneyPerson | None:
    """Link to an existing unknown only when the same camera track id repeats."""
    track_id = getattr(instance, "local_track_id", None)
    if not track_id or not camera:
        return None

    from .models import CameraTrack, TrackStatus

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

    from cameras.models import DetectionEvent

    prev = (
        DetectionEvent.objects.filter(
            camera=camera,
            local_track_id=track_id,
            person_identity_id__isnull=False,
            created_at__gte=now - timedelta(minutes=15),
        )
        .exclude(pk=instance.pk)
        .order_by("-created_at")
        .first()
    )
    if prev and prev.person_identity_id:
        return JourneyPerson.objects.filter(
            pk=prev.person_identity_id,
            person_type=PersonType.UNKNOWN,
            status=PersonStatus.ACTIVE,
        ).first()
    return None


def _resolve_person_from_detection(instance) -> tuple[JourneyPerson | None, bool]:
    """Return (person, created). Each unknown person gets a separate journey unless track-linked."""
    staff_id, staff_name = resolve_staff_from_face_label(instance.employee_name or instance.label or "")
    if not staff_id and instance.personal_number:
        from users.models import Staff

        staff = Staff.objects.filter(personal_number=instance.personal_number).first()
        if staff:
            staff_id = staff.pk
            staff_name = staff.full_name or staff_name

    camera = instance.camera
    now = instance.created_at or timezone.now()

    if staff_id:
        person = JourneyPerson.objects.filter(staff_id=staff_id, status=PersonStatus.ACTIVE).first()
        if person is None:
            from users.models import Staff

            staff = Staff.objects.filter(pk=staff_id).first()
            if staff:
                person = register_staff_journey_person(staff)
                return person, True
        return person, False

    label = (instance.label or "").strip()
    if label and label.lower() not in _GENERIC_LABELS:
        person = JourneyPerson.objects.filter(
            display_name__iexact=label,
            status=PersonStatus.ACTIVE,
            latest_seen_at__gte=now - timedelta(minutes=30),
        ).first()
        if person:
            return person, False

    # Generic unknown — do NOT merge all unknowns on one camera; only reuse same track id.
    if label.lower() in _GENERIC_LABELS or not label:
        tracked = _match_unknown_by_track(instance, camera, now)
        if tracked:
            return tracked, False

        person, created = resolve_unknown_person(
            camera=camera,
            bbox=getattr(instance, "bbox", None) or [],
            now=now,
            track_id=getattr(instance, "local_track_id", None),
            source="detection_bridge",
        )
        return person, created

    person_type = PersonType.UNKNOWN
    display = staff_name or label
    person = create_journey_person(
        person_type=person_type,
        display_name=display[:200],
        latest_camera=camera,
        latest_zone=_camera_zone(camera),
        latest_seen_at=now,
        status=PersonStatus.ACTIVE,
    )
    return person, True


def record_journey_sighting(
    *,
    person: JourneyPerson,
    created: bool,
    camera,
    instance,
    detection_event_id: int | None = None,
    source: str = "detection_bridge",
) -> JourneyEvent:
    """Create timeline row + queue snapshot for one person sighting."""
    now = getattr(instance, "created_at", None) or timezone.now()
    staff_id, staff_name = resolve_staff_from_face_label(
        getattr(instance, "employee_name", "") or getattr(instance, "label", "") or ""
    )

    updates = ["latest_seen_at", "updated_at"]
    person.latest_seen_at = now
    if camera:
        person.latest_camera = camera
        person.latest_zone = _camera_zone(camera)
        updates.extend(["latest_camera", "latest_zone"])
    if staff_id and not person.staff_id:
        person.staff_id = staff_id
        person.person_type = PersonType.STAFF
        person.display_name = staff_name or person.display_name
        updates.extend(["staff_id", "person_type", "display_name"])
    person.save(update_fields=list(dict.fromkeys(updates)))

    if created:
        event_type = JourneyEventType.UNKNOWN_CREATED
        title = f"Unknown person — {person.code}"
    elif staff_id or person.person_type == PersonType.STAFF:
        event_type = JourneyEventType.STAFF_RECOGNIZED
        title = f"Recognized: {person.display_name}"
    else:
        event_type = JourneyEventType.CAMERA_DETECTION
        title = f"Seen at {camera.name if camera else 'camera'}"

    journey_event = JourneyEvent.objects.create(
        journey_person=person,
        event_type=event_type,
        title=title,
        description=f"{instance.class_name}: {instance.label}",
        camera=camera,
        zone=_camera_zone(camera),
        detection_event_id=detection_event_id,
        confidence=getattr(instance, "confidence", None),
        bbox=getattr(instance, "bbox", None) or [],
        snapshot_path="",
        metadata={
            "source": source,
            "label": getattr(instance, "label", ""),
            "employee_name": getattr(instance, "employee_name", ""),
            "personal_number": getattr(instance, "personal_number", ""),
        },
    )

    if detection_event_id:
        from cameras.models import DetectionEvent

        DetectionEvent.objects.filter(pk=detection_event_id).update(
            person_qr=person.code,
            person_identity_id=person.pk,
            track_event="detection",
        )

    track_id = getattr(instance, "local_track_id", None)
    if track_id and camera and person.person_type == PersonType.UNKNOWN:
        from .models import CameraTrack, TrackStatus

        track = (
            CameraTrack.objects.filter(
                journey_person=person,
                camera=camera,
                track_id=track_id,
                status=TrackStatus.ACTIVE,
            )
            .order_by("-started_at")
            .first()
        )
        if track is None:
            CameraTrack.objects.create(
                journey_person=person,
                camera=camera,
                track_id=track_id,
                status=TrackStatus.ACTIVE,
                started_at=now,
                last_bbox=getattr(instance, "bbox", None) or [],
                metadata={"source": source},
            )
        else:
            track.last_bbox = getattr(instance, "bbox", None) or []
            track.save(update_fields=["last_bbox"])

    from .snapshot_capture import schedule_journey_snapshot

    schedule_journey_snapshot(
        journey_event.pk,
        detection_event_id,
        camera.pk if camera else None,
    )
    return journey_event


@transaction.atomic
def bridge_detection_event(instance, *, force: bool = False) -> JourneyPerson | None:
    """Create/update journey person + timeline event from a DetectionEvent."""
    if not _is_person_detection(
        instance.class_name,
        instance.label,
        instance.employee_name or "",
    ):
        return None

    label_key = (instance.employee_name or instance.label or "").strip().lower()
    if label_key in _GENERIC_LABELS and _generic_unknown_handled_elsewhere():
        return None

    if not force:
        recent = JourneyEvent.objects.filter(
            detection_event_id=instance.pk,
        ).exists()
        if recent:
            return None

        since = (instance.created_at or timezone.now()) - timedelta(seconds=_BRIDGE_DEDUP_SECONDS)
        label_for_dedup = (instance.employee_name or instance.label or "").strip()
        if label_for_dedup.lower() not in _GENERIC_LABELS:
            if JourneyEvent.objects.filter(
                camera=instance.camera,
                event_type__in=[
                    JourneyEventType.CAMERA_DETECTION,
                    JourneyEventType.STAFF_RECOGNIZED,
                    JourneyEventType.UNKNOWN_CREATED,
                ],
                created_at__gte=since,
                journey_person__display_name__iexact=label_for_dedup,
            ).exists():
                return None

    person, created = _resolve_person_from_detection(instance)
    if person is None:
        return None

    record_journey_sighting(
        person=person,
        created=created,
        camera=instance.camera,
        instance=instance,
        detection_event_id=instance.pk,
    )
    return person


def backfill_from_detections(*, hours: int = 24, limit: int = 500) -> int:
    """Process recent person DetectionEvents into journey DB."""
    from cameras.models import DetectionEvent

    since = timezone.now() - timedelta(hours=max(1, hours))
    qs = (
        DetectionEvent.objects.filter(created_at__gte=since, class_name__iexact="person")
        .select_related("camera", "camera__nvr", "camera__nvr__site")
        .order_by("-created_at")
    )
    bridged = 0
    for event in qs[:limit]:
        try:
            if bridge_detection_event(event, force=True):
                bridged += 1
        except Exception:
            logger.exception("Bridge failed for detection %s", event.pk)
    return bridged
