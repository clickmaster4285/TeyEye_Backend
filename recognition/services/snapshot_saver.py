from __future__ import annotations

import logging
from pathlib import Path

import cv2
import numpy as np
from django.conf import settings
from django.core.files.base import ContentFile
from django.utils import timezone

from recognition.models import DetectionSnapshot

logger = logging.getLogger(__name__)


def _annotate_frame(
    frame: np.ndarray,
    camera_id: int,
    camera_name: str,
    staff_label: str,
    confidence: float,
    bbox=None,
) -> np.ndarray:
    img = frame.copy()
    h, w = img.shape[:2]

    max_w = 960
    if w > max_w:
        scale = max_w / w
        img = cv2.resize(img, (max_w, int(h * scale)))
        if bbox is not None:
            bbox = [int(v * scale) for v in bbox]

    if bbox is not None and len(bbox) == 4:
        x1, y1, x2, y2 = [int(v) for v in bbox]
        cv2.rectangle(img, (x1, y1), (x2, y2), (0, 200, 80), 2)

    stamp = timezone.localtime().strftime("%Y-%m-%d %H:%M:%S")
    lines = [
        f"Camera #{camera_id}  {camera_name}",
        f"{staff_label}  {confidence * 100:.0f}%",
        stamp,
    ]

    y = 28
    for line in lines:
        cv2.putText(img, line, (12, y), cv2.FONT_HERSHEY_SIMPLEX, 0.65, (0, 0, 0), 4, cv2.LINE_AA)
        cv2.putText(img, line, (12, y), cv2.FONT_HERSHEY_SIMPLEX, 0.65, (255, 255, 255), 2, cv2.LINE_AA)
        y += 28

    return img


def save_detection_snapshot(
    *,
    staff,
    camera_id: int,
    camera_name: str,
    frame: np.ndarray,
    confidence: float,
    attendance_action: str = "",
    attendance_record=None,
    bbox=None,
) -> DetectionSnapshot | None:
    """Save an annotated JPEG when staff is recognized on CCTV."""
    try:
        from cameras.models import Camera

        label = staff.employee_id or staff.full_name or f"staff-{staff.pk}"
        annotated = _annotate_frame(
            frame,
            camera_id=camera_id,
            camera_name=camera_name,
            staff_label=str(label),
            confidence=confidence,
            bbox=bbox,
        )
        ok, buf = cv2.imencode(".jpg", annotated, [int(cv2.IMWRITE_JPEG_QUALITY), 85])
        if not ok:
            return None

        camera = Camera.objects.filter(id=camera_id).first()
        stamp = timezone.localtime().strftime("%H%M%S")
        filename = f"staff{staff.pk}_cam{camera_id}_{stamp}.jpg"

        snapshot = DetectionSnapshot(
            staff=staff,
            camera=camera,
            camera_name=camera_name or f"Camera {camera_id}",
            confidence=round(confidence, 4),
            attendance_action=attendance_action or "",
        )
        snapshot.image.save(filename, ContentFile(buf.tobytes()), save=True)

        if (
            attendance_record is not None
            and attendance_action in ("check_in", "check_out")
        ):
            proof_name = (
                f"staff{staff.pk}_{attendance_action}_"
                f"{timezone.localtime().strftime('%Y%m%d_%H%M%S_%f')}.jpg"
            )
            attendance_record.image.save(
                proof_name,
                ContentFile(buf.tobytes()),
                save=True,
            )

        return snapshot
    except Exception:
        logger.exception("Failed to save detection snapshot")
        return None


def snapshot_to_dict(snapshot: DetectionSnapshot) -> dict:
    image_url = ""
    if snapshot.image:
        try:
            rel = Path(snapshot.image.name).as_posix()
            image_url = f"{settings.MEDIA_URL}{rel}"
        except Exception:
            image_url = snapshot.image.url

    staff = snapshot.staff
    return {
        "id": snapshot.id,
        "staff_id": snapshot.staff_id,
        "employee_id": staff.employee_id if staff else None,
        "employee_name": staff.full_name if staff else "",
        "camera_id": snapshot.camera_id,
        "camera_name": snapshot.camera_name,
        "camera_label": f"Camera #{snapshot.camera_id or '?'} · {snapshot.camera_name}",
        "image_url": image_url,
        "confidence": snapshot.confidence,
        "attendance_action": snapshot.attendance_action,
        "detected_at": snapshot.detected_at.isoformat(),
    }
