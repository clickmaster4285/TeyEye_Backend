"""Capture a snapshot image (with detection overlay) when a detection event is saved."""

from __future__ import annotations

import logging
import os
import subprocess
import threading
import time
from collections import deque
from typing import TYPE_CHECKING

import requests
from django.conf import settings
from django.core.files import File
from django.db import close_old_connections

from .stream_utils import ffmpeg_path

if TYPE_CHECKING:
    from .models import Camera, DetectionEvent

logger = logging.getLogger(__name__)

_camera_clip_locks: dict[int, threading.Lock] = {}
_locks_guard = threading.Lock()
_camera_queues: dict[int, deque[int]] = {}
_queue_guard = threading.Lock()
_active_queue_workers: set[int] = set()


def _clip_enabled() -> bool:
    return bool(getattr(settings, "DETECTION_CLIP_ENABLED", True))


def _update_clip_status(event_id: int, status: str) -> None:
    close_old_connections()
    from .models import DetectionEvent

    DetectionEvent.objects.filter(pk=event_id).update(clip_status=status)


def _camera_lock(camera_id: int) -> threading.Lock:
    with _locks_guard:
        lock = _camera_clip_locks.get(camera_id)
        if lock is None:
            lock = threading.Lock()
            _camera_clip_locks[camera_id] = lock
        return lock


def _ml_mjpeg_url(camera) -> str | None:
    try:
        from ml.client import ml_live_mjpeg_url, ml_service_enabled
    except ImportError:
        return None
    if not ml_service_enabled():
        return None
    return ml_live_mjpeg_url(camera.stream_key, rtsp_url=camera.effective_stream_url())


def _rtsp_input_extra() -> list[str]:
    return ["-rtsp_transport", "tcp"]


def _display_class(event: DetectionEvent) -> str:
    return (event.class_name or event.label or "object").strip()


def _snapshot_label(event: DetectionEvent) -> str:
    """Prefer recognized employee name on annotated snapshots."""
    employee = (getattr(event, "employee_name", None) or "").strip()
    if employee:
        return employee[:80]

    label = (event.label or "").strip()
    cls = (event.class_name or "").strip().lower()
    generic = {"", "unknown", "person", "face"}
    if cls in ("person", "face") and label.lower() not in generic:
        return label[:80]

    return _display_class(event)


def _fit_bbox_to_frame(bbox: list, frame_w: int, frame_h: int) -> list[int] | None:
    if not isinstance(bbox, (list, tuple)) or len(bbox) < 4:
        return None
    try:
        x1, y1, x2, y2 = (float(v) for v in bbox[:4])
    except (TypeError, ValueError):
        return None
    if x2 <= x1 or y2 <= y1:
        return None

    max_x = max(x1, x2)
    max_y = max(y1, y2)
    if max_x > frame_w or max_y > frame_h:
        scale = min(frame_w / max_x, frame_h / max_y)
        x1, y1, x2, y2 = x1 * scale, y1 * scale, x2 * scale, y2 * scale

    x1 = int(max(0, min(x1, frame_w - 1)))
    y1 = int(max(0, min(y1, frame_h - 1)))
    x2 = int(max(x1 + 1, min(x2, frame_w)))
    y2 = int(max(y1 + 1, min(y2, frame_h)))
    return [x1, y1, x2, y2]


def _draw_detection_on_frame(frame, event: DetectionEvent):
    import cv2

    output = frame.copy()
    h, w = output.shape[:2]
    label = _snapshot_label(event)
    font = cv2.FONT_HERSHEY_SIMPLEX
    font_scale = max(0.32, h / 1400)
    thickness = max(1, int(font_scale * 1.4))
    box_thickness = max(1, int(font_scale * 1.6))

    color = (0, 0, 255) if event.is_alert else (0, 220, 0)

    (banner_w, banner_h), baseline = cv2.getTextSize(label, font, font_scale, thickness)
    pad = 5
    cv2.rectangle(
        output,
        (8, 8),
        (14 + banner_w + pad, 14 + banner_h + baseline + pad),
        (0, 0, 0),
        -1,
    )
    cv2.putText(
        output,
        label,
        (12, 14 + banner_h),
        font,
        font_scale,
        (255, 255, 255),
        thickness,
        cv2.LINE_AA,
    )

    fitted = _fit_bbox_to_frame(event.bbox or [], w, h)
    if fitted:
        x1, y1, x2, y2 = fitted
        cv2.rectangle(output, (x1, y1), (x2, y2), color, box_thickness)
        box_font_scale = max(0.28, h / 1600)
        box_thickness_text = max(1, int(box_font_scale * 1.4))
        (text_w, text_h), text_base = cv2.getTextSize(label, font, box_font_scale, box_thickness_text)
        text_x = x1
        text_y = max(text_h + 6, y1 - 6)
        cv2.rectangle(
            output,
            (text_x, text_y - text_h - 4),
            (text_x + text_w + 6, text_y + text_base + 3),
            (0, 0, 0),
            -1,
        )
        cv2.putText(
            output,
            label,
            (text_x + 3, text_y),
            font,
            box_font_scale,
            color,
            box_thickness_text,
            cv2.LINE_AA,
        )

    return output


def _read_mjpeg_snapshot(mjpeg_url: str, *, timeout_sec: float = 12.0) -> object | None:
    """Read one JPEG frame from the ML MJPEG stream."""
    try:
        import cv2
        import numpy as np
    except ImportError:
        logger.warning("OpenCV not available for snapshot capture")
        return None

    deadline = time.monotonic() + timeout_sec
    try:
        with requests.get(mjpeg_url, stream=True, timeout=(5, timeout_sec)) as resp:
            if resp.status_code != 200:
                return None
            buffer = b""
            for chunk in resp.iter_content(chunk_size=8192):
                if time.monotonic() > deadline:
                    break
                if not chunk:
                    continue
                buffer += chunk
                while True:
                    start = buffer.find(b"\xff\xd8")
                    end = buffer.find(b"\xff\xd9")
                    if start == -1 or end == -1 or end < start:
                        break
                    jpg = buffer[start : end + 2]
                    buffer = buffer[end + 2 :]
                    arr = np.frombuffer(jpg, dtype=np.uint8)
                    frame = cv2.imdecode(arr, cv2.IMREAD_COLOR)
                    if frame is not None:
                        return frame
    except requests.RequestException as exc:
        logger.warning("MJPEG snapshot capture failed: %s", exc)
    return None


def _read_rtsp_snapshot(stream_url: str) -> object | None:
    """Grab one frame from RTSP via ffmpeg."""
    try:
        import cv2
    except ImportError:
        return None

    temp_dir = os.path.join(settings.MEDIA_ROOT, "detection_clips", "_tmp")
    os.makedirs(temp_dir, exist_ok=True)
    temp_path = os.path.join(temp_dir, f"snap_{int(time.time() * 1000)}.jpg")
    cmd = [
        ffmpeg_path(),
        "-nostdin",
        "-hide_banner",
        "-loglevel",
        "error",
        *_rtsp_input_extra(),
        "-i",
        stream_url,
        "-frames:v",
        "1",
        "-q:v",
        "2",
        "-y",
        temp_path,
    ]
    try:
        proc = subprocess.run(cmd, capture_output=True, timeout=25)
    except (FileNotFoundError, subprocess.TimeoutExpired) as exc:
        logger.warning("RTSP snapshot ffmpeg failed: %s", exc)
        return None

    frame = None
    try:
        if os.path.isfile(temp_path) and os.path.getsize(temp_path) > 0:
            frame = cv2.imread(temp_path)
    finally:
        try:
            if os.path.isfile(temp_path):
                os.remove(temp_path)
        except OSError:
            pass

    if proc.returncode != 0 or frame is None:
        return None
    return frame


def _warm_ml_stream(camera) -> None:
    try:
        from ml.client import ml_live_detections, ml_service_enabled
    except ImportError:
        return
    if not ml_service_enabled():
        return
    for _ in range(2):
        try:
            ml_live_detections(camera.stream_key, rtsp_url=camera.effective_stream_url())
            return
        except Exception:
            time.sleep(0.5)


def capture_detection_clip_sync(camera_id: int, event_id: int) -> None:
    """Capture one annotated snapshot for this detection event."""
    from .models import Camera, ClipStatus, DetectionEvent

    if not _clip_enabled():
        _update_clip_status(event_id, ClipStatus.SKIPPED)
        return

    close_old_connections()

    try:
        camera = Camera.objects.select_related("nvr").get(pk=camera_id)
        event = DetectionEvent.objects.get(pk=event_id)
    except (Camera.DoesNotExist, DetectionEvent.DoesNotExist):
        return

    if event.clip_status == ClipStatus.SKIPPED:
        return

    if event.clip:
        _update_clip_status(event_id, ClipStatus.READY)
        return

    _update_clip_status(event_id, ClipStatus.RECORDING)

    temp_dir = os.path.join(settings.MEDIA_ROOT, "detection_clips", "_tmp")
    os.makedirs(temp_dir, exist_ok=True)
    temp_path = os.path.join(temp_dir, f"event_{event_id}_{int(time.time())}.jpg")

    try:
        import cv2
    except ImportError:
        _update_clip_status(event_id, ClipStatus.FAILED)
        return

    frame = None
    mjpeg_url = _ml_mjpeg_url(camera)
    if mjpeg_url:
        _warm_ml_stream(camera)
        frame = _read_mjpeg_snapshot(mjpeg_url)

    stream_url = camera.effective_stream_url()
    if frame is None and stream_url:
        frame = _read_rtsp_snapshot(stream_url)

    if frame is None:
        if not stream_url and not mjpeg_url:
            _update_clip_status(event_id, ClipStatus.SKIPPED)
        else:
            _update_clip_status(event_id, ClipStatus.FAILED)
        return

    annotated = _draw_detection_on_frame(frame, event)
    if not cv2.imwrite(temp_path, annotated, [int(cv2.IMWRITE_JPEG_QUALITY), 88]):
        _update_clip_status(event_id, ClipStatus.FAILED)
        return

    try:
        filename = f"event_{event_id}.jpg"
        with open(temp_path, "rb") as fh:
            event.clip.save(filename, File(fh), save=True)
        _update_clip_status(event_id, ClipStatus.READY)
        logger.info(
            "Saved detection snapshot for event %s (%s) class=%s",
            event_id,
            event.clip.name,
            _snapshot_label(event),
        )
    except Exception:
        logger.exception("Failed to save snapshot for detection event %s", event_id)
        _update_clip_status(event_id, ClipStatus.FAILED)
    finally:
        try:
            if os.path.isfile(temp_path):
                os.remove(temp_path)
        except OSError:
            pass


def _process_camera_queue(camera_id: int) -> None:
    while True:
        with _queue_guard:
            queue = _camera_queues.get(camera_id)
            if not queue:
                _active_queue_workers.discard(camera_id)
                return
            event_id = queue.popleft()

        with _camera_lock(camera_id):
            capture_detection_clip_sync(camera_id, event_id)


def _enqueue_clip(camera_id: int, event_id: int) -> None:
    with _queue_guard:
        queue = _camera_queues.setdefault(camera_id, deque())
        if event_id in queue:
            return
        queue.append(event_id)
        if camera_id not in _active_queue_workers:
            _active_queue_workers.add(camera_id)
            thread = threading.Thread(
                target=_process_camera_queue,
                args=(camera_id,),
                daemon=True,
                name=f"det-snapshot-q-{camera_id}",
            )
            thread.start()


def requeue_pending_clips(*, limit: int = 200) -> int:
    """Enqueue pending snapshots left from a previous run."""
    from .models import ClipStatus, DetectionEvent

    close_old_connections()
    DetectionEvent.objects.filter(
        clip_status=ClipStatus.RECORDING,
        clip="",
    ).update(clip_status=ClipStatus.PENDING)

    rows = list(
        DetectionEvent.objects.filter(clip_status=ClipStatus.PENDING, clip="")
        .order_by("created_at")
        .values_list("camera_id", "id")[:limit]
    )
    for camera_id, event_id in rows:
        _enqueue_clip(camera_id, event_id)
    if rows:
        logger.info("[snapshot-capture] Re-queued %s pending snapshot(s)", len(rows))
    return len(rows)


def schedule_detection_clip(camera_id: int, event_id: int) -> None:
    """Queue snapshot capture for a detection event."""
    from .models import ClipStatus

    if not _clip_enabled():
        _update_clip_status(event_id, ClipStatus.SKIPPED)
        return

    _enqueue_clip(camera_id, event_id)
