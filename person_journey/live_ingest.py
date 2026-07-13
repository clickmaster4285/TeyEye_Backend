"""Ingest every person detection from ML live feed (bypasses label dedup in cameras app)."""

from __future__ import annotations

import logging
from datetime import timedelta
from types import SimpleNamespace

from django.db import transaction
from django.utils import timezone

from cameras.detection_utils import resolve_staff_identity

from .bridge_detection import (
    _GENERIC_LABELS,
    _is_person_detection,
    _resolve_person_from_detection,
    record_journey_sighting,
)
from .matching import resolve_staff_from_face_label
from .models import JourneyEvent, JourneyPerson, PersonStatus, PersonType
from .unknown_resolution import live_ingest_unknowns_enabled, resolve_unknown_person

logger = logging.getLogger(__name__)

_MIN_CONFIDENCE = 0.30
_EVENT_DEDUP_SECONDS = 4


def _filter_person_detections(detections: list[dict]) -> list[dict]:
    kept: list[dict] = []
    for det in detections or []:
        label = str(det.get("label") or det.get("class_name") or "").strip()
        class_name = str(det.get("class_name") or label or "object").strip()
        try:
            confidence = float(det.get("confidence", 0))
        except (TypeError, ValueError):
            continue
        if confidence < _MIN_CONFIDENCE:
            continue
        employee_name, personal_number = resolve_staff_identity(label, class_name)
        if not _is_person_detection(class_name, label, employee_name):
            continue
        kept.append(
            {
                **det,
                "label": label,
                "class_name": class_name,
                "confidence": confidence,
                "bbox": det.get("bbox") or [],
                "employee_name": employee_name,
                "personal_number": personal_number,
            }
        )
    return kept


def _recent_event_exists(person: JourneyPerson, camera, now) -> bool:
    return JourneyEvent.objects.filter(
        journey_person=person,
        camera=camera,
        created_at__gte=now - timedelta(seconds=_EVENT_DEDUP_SECONDS),
    ).exists()


@transaction.atomic
def ingest_camera_detections(camera, detections: list[dict]) -> int:
    """Record one journey sighting per person visible in the ML detection batch."""
    people = _filter_person_detections(detections)
    if not people:
        return 0

    unknowns_enabled = live_ingest_unknowns_enabled()
    now = timezone.now()
    recorded = 0
    frame_slots: list[tuple[list, JourneyPerson]] = []

    for det in people:
        label = det["label"]
        class_name = det["class_name"]
        bbox = det["bbox"]
        confidence = det["confidence"]
        employee_name = det.get("employee_name") or ""
        personal_number = det.get("personal_number") or ""
        is_generic_unknown = (label or "").lower() in _GENERIC_LABELS

        if is_generic_unknown and not unknowns_enabled:
            continue

        proxy = SimpleNamespace(
            pk=None,
            camera=camera,
            label=label,
            class_name=class_name,
            employee_name=employee_name,
            personal_number=personal_number,
            created_at=now,
            local_track_id=det.get("track_id"),
            bbox=bbox,
            confidence=confidence,
            metadata={
                "frame_width": det.get("frame_width"),
                "frame_height": det.get("frame_height"),
            },
        )

        staff_id, staff_name = resolve_staff_from_face_label(employee_name or label)
        if not staff_id and personal_number:
            from users.models import Staff

            staff = Staff.objects.filter(personal_number=personal_number).first()
            if staff:
                staff_id = staff.pk
                staff_name = staff.full_name or staff_name

        if staff_id:
            person, created = _resolve_person_from_detection(proxy)
        elif is_generic_unknown:
            person, created = resolve_unknown_person(
                camera=camera,
                bbox=bbox,
                now=now,
                frame_slots=frame_slots,
                track_id=det.get("track_id"),
                face_embedding=det.get("face_embedding") or None,
                reid_embedding=det.get("reid_embedding") or None,
                source="live_ingest",
            )
            if person:
                frame_slots.append((bbox, person))
        else:
            person, created = _resolve_person_from_detection(proxy)

        if person is None:
            continue
        if _recent_event_exists(person, camera, now):
            person.latest_seen_at = now
            person.latest_camera = camera
            person.save(update_fields=["latest_seen_at", "latest_camera", "updated_at"])
            continue

        record_journey_sighting(
            person=person,
            created=created,
            camera=camera,
            instance=proxy,
            detection_event_id=None,
            source="live_ingest",
        )
        recorded += 1

    if recorded:
        logger.info("Live ingest camera %s: recorded %s/%s persons", camera.pk, recorded, len(people))
    return recorded
