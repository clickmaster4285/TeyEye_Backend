"""Persist ML detection readings with light deduplication."""

from __future__ import annotations

import os
from datetime import timedelta
from typing import Any

from django.conf import settings
from django.db.models import Q
from django.utils import timezone

from .clip_capture import schedule_detection_clip
from .models import Camera, CameraPurpose, ClipStatus, DetectionEvent

DEFAULT_MIN_CONFIDENCE = 0.25
_GENERIC_EMPLOYEE_LABELS = frozenset({"unknown", "person", "face", ""})
_ANPR_CLASS_NAMES = frozenset(
    {
        "car",
        "truck",
        "bus",
        "motorcycle",
        "bicycle",
        "vehicle",
        "license plate",
        "number plate",
    }
)


def _coco_max_class_id() -> int:
    try:
        return int(os.getenv("ML_COCO_MAX_CLASS_ID", "79"))
    except (TypeError, ValueError):
        return 79


def is_coco_detection(det: dict[str, Any]) -> bool:
    """True for generic COCO model hits (e.g. chair, person) — not custom specialist classes."""
    tag = str(det.get("model_tag") or det.get("model") or "").strip().lower()
    if tag in ("custom", "smoke"):
        return False
    if tag == "coco":
        return True
    try:
        cls_id = int(det.get("class_id", -1))
    except (TypeError, ValueError):
        cls_id = -1
    return 0 <= cls_id <= _coco_max_class_id()


def filter_detections_for_camera(camera: Camera, detections: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Keep only detections relevant to this camera's AI purpose."""
    purpose = camera.purpose
    kept: list[dict[str, Any]] = []

    for det in detections or []:
        if det.get("alert"):
            kept.append(det)
            continue

        cls = str(det.get("class_name") or det.get("label") or "").strip().lower()

        if purpose == CameraPurpose.OBJECT_DETECTION:
            if not is_coco_detection(det):
                kept.append(det)
            continue

        if purpose in (CameraPurpose.FACE_RECOGNITION, CameraPurpose.ATTENDANCE):
            if cls in ("person", "face"):
                kept.append(det)
            continue

        if purpose == CameraPurpose.ANPR:
            if cls in _ANPR_CLASS_NAMES:
                kept.append(det)
            continue

        kept.append(det)

    return kept


def resolve_employee_name(label: str, class_name: str) -> str:
    """Map ML face-recognition label to employee_name for person/face detections."""
    employee_name, _ = resolve_staff_identity(label, class_name)
    return employee_name


def resolve_staff_identity(label: str, class_name: str) -> tuple[str, str]:
    """Return (employee_name, personal_number) for recognized person/face detections."""
    lbl = (label or "").strip()
    cls = (class_name or "").strip().lower()
    if cls not in ("person", "face") or lbl.lower() in _GENERIC_EMPLOYEE_LABELS:
        return "", ""

    from users.models import Staff, StaffFaceEmbedding

    staff = None
    embedding = (
        StaffFaceEmbedding.objects.filter(identity_label__iexact=lbl, is_active=True)
        .select_related("staff")
        .first()
    )
    if embedding is not None:
        staff = embedding.staff

    if staff is None:
        staff = (
            Staff.objects.filter(Q(user__username__iexact=lbl) | Q(full_name__iexact=lbl))
            .select_related("user")
            .first()
        )

    if staff is None:
        return lbl[:150], ""

    employee_name = (staff.full_name or lbl).strip()[:150]
    personal_number = (staff.personal_number or "").strip()[:50]
    return employee_name, personal_number


def _dedup_seconds() -> int:
    raw = getattr(settings, "DETECTION_DEDUP_SECONDS", 5)
    try:
        return max(0, int(raw))
    except (TypeError, ValueError):
        return 5


def save_detection_batch(
    camera: Camera,
    detections: list[dict[str, Any]],
    *,
    min_confidence: float = DEFAULT_MIN_CONFIDENCE,
    dedup_seconds: int | None = None,
) -> int:
    """Save detections from a live ML poll. Returns number of new rows created."""
    detections = filter_detections_for_camera(camera, detections)
    if not detections:
        return 0

    dedup_window = _dedup_seconds() if dedup_seconds is None else max(0, dedup_seconds)
    since = timezone.now() - timedelta(seconds=max(1, dedup_window)) if dedup_window > 0 else None
    saved = 0

    for det in detections:
        label = str(det.get("label") or det.get("class_name") or "").strip()
        class_name = str(det.get("class_name") or label or "object").strip()
        if not label:
            continue
        try:
            confidence = float(det.get("confidence", 0))
        except (TypeError, ValueError):
            continue
        if confidence < min_confidence:
            continue

        if since is not None and DetectionEvent.objects.filter(
            camera=camera,
            label=label,
            class_name=class_name,
            created_at__gte=since,
        ).exists():
            continue

        clip_enabled = bool(getattr(settings, "DETECTION_CLIP_ENABLED", True))
        employee_name, personal_number = resolve_staff_identity(label, class_name)
        event = DetectionEvent.objects.create(
            camera=camera,
            class_name=class_name[:80],
            label=label[:120],
            employee_name=employee_name,
            personal_number=personal_number,
            confidence=confidence,
            bbox=det.get("bbox") or [],
            is_alert=bool(det.get("alert")),
            clip_status=ClipStatus.PENDING if clip_enabled else ClipStatus.SKIPPED,
        )
        schedule_detection_clip(camera.pk, event.pk)
        saved += 1

    return saved
