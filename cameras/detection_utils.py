"""Persist ML detection readings with light deduplication."""

from __future__ import annotations

from datetime import timedelta
from typing import Any

from django.conf import settings
from django.utils import timezone

from .clip_capture import schedule_detection_clip
from .models import Camera, ClipStatus, DetectionEvent

DEFAULT_MIN_CONFIDENCE = 0.25


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
        event = DetectionEvent.objects.create(
            camera=camera,
            class_name=class_name[:80],
            label=label[:120],
            confidence=confidence,
            bbox=det.get("bbox") or [],
            is_alert=bool(det.get("alert")),
            clip_status=ClipStatus.PENDING if clip_enabled else ClipStatus.SKIPPED,
        )
        schedule_detection_clip(camera.pk, event.pk)
        saved += 1

    return saved
