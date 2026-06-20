"""Capture a short MP4 clip when a detection event is saved."""

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
_global_clip_semaphore = threading.Semaphore(1)


def _clip_enabled() -> bool:
    return bool(getattr(settings, "DETECTION_CLIP_ENABLED", True))


def _clip_duration_sec() -> int:
    raw = getattr(settings, "DETECTION_CLIP_SECONDS", 7)
    try:
        duration = int(raw)
    except (TypeError, ValueError):
        duration = 7
    return min(10, max(5, duration))


def _clip_fps() -> int:
    raw = getattr(settings, "CAMERA_STREAM_FPS", 25)
    try:
        return max(8, min(30, int(raw)))
    except (TypeError, ValueError):
        return 25


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
    label = _display_class(event)
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


def _reencode_h264(source_path: str, out_path: str) -> bool:
    cmd = [
        ffmpeg_path(),
        "-nostdin",
        "-hide_banner",
        "-loglevel",
        "error",
        "-y",
        "-i",
        source_path,
        "-c:v",
        "libx264",
        "-preset",
        "fast",
        "-crf",
        "23",
        "-an",
        "-movflags",
        "+faststart",
        out_path,
    ]
    try:
        proc = subprocess.run(cmd, capture_output=True, timeout=120)
    except (FileNotFoundError, subprocess.TimeoutExpired):
        return False
    return proc.returncode == 0 and os.path.isfile(out_path) and os.path.getsize(out_path) > 0


def _record_clip_from_mjpeg(mjpeg_url: str, event: DetectionEvent, out_path: str, duration: int) -> bool:
    """Record from ML annotated MJPEG (reuses the open RTSP session)."""
    try:
        import cv2
        import numpy as np
    except ImportError:
        logger.warning("OpenCV not available for MJPEG clip capture")
        return False

    fps = _clip_fps()
    min_frames = max(4, duration)
    writer = None
    frames = 0
    temp_cv = f"{out_path}.cv.mp4"
    record_start: float | None = None
    warmup_deadline = time.monotonic() + 15

    try:
        with requests.get(mjpeg_url, stream=True, timeout=(10, 10)) as resp:
            if resp.status_code != 200:
                return False
            buffer = b""
            for chunk in resp.iter_content(chunk_size=8192):
                now = time.monotonic()
                if record_start is None and now > warmup_deadline:
                    break
                if record_start is not None and now - record_start >= duration:
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
                    if frame is None:
                        continue
                    if record_start is None:
                        record_start = time.monotonic()
                    if writer is None:
                        h, w = frame.shape[:2]
                        writer = cv2.VideoWriter(
                            temp_cv,
                            cv2.VideoWriter_fourcc(*"mp4v"),
                            fps,
                            (w, h),
                        )
                        if not writer.isOpened():
                            return False
                    writer.write(_draw_detection_on_frame(frame, event))
                    frames += 1
                    if record_start is not None and time.monotonic() - record_start >= duration:
                        break
                if record_start is not None and time.monotonic() - record_start >= duration:
                    break
    except requests.RequestException as exc:
        logger.warning("MJPEG clip capture failed: %s", exc)
        return False
    finally:
        if writer is not None:
            writer.release()

    if frames < min_frames or not os.path.isfile(temp_cv) or os.path.getsize(temp_cv) <= 0:
        try:
            os.remove(temp_cv)
        except OSError:
            pass
        return False

    ok = _reencode_h264(temp_cv, out_path)
    try:
        os.remove(temp_cv)
    except OSError:
        pass
    return ok


def _record_raw_clip_rtsp(stream_url: str, raw_path: str, duration: int) -> bool:
    cmd = [
        ffmpeg_path(),
        "-nostdin",
        "-hide_banner",
        "-loglevel",
        "error",
        *_rtsp_input_extra(),
        "-i",
        stream_url,
        "-t",
        str(duration),
        "-map",
        "0:v:0?",
        "-an",
        "-c:v",
        "libx264",
        "-preset",
        "ultrafast",
        "-crf",
        "23",
        "-y",
        raw_path,
    ]
    try:
        proc = subprocess.run(cmd, capture_output=True, timeout=duration * 3 + 30)
    except (FileNotFoundError, subprocess.TimeoutExpired) as exc:
        logger.warning("Raw RTSP clip ffmpeg failed: %s", exc)
        return False
    return proc.returncode == 0 and os.path.isfile(raw_path) and os.path.getsize(raw_path) > 0


def _burn_overlay_with_opencv(raw_path: str, out_path: str, event: DetectionEvent) -> bool:
    try:
        import cv2
    except ImportError:
        logger.warning("OpenCV not available for clip overlay")
        return False

    cap = cv2.VideoCapture(raw_path)
    if not cap.isOpened():
        return False

    fps = cap.get(cv2.CAP_PROP_FPS) or _clip_fps()
    width = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH))
    height = int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT))
    if width <= 0 or height <= 0:
        cap.release()
        return False

    temp_cv = f"{out_path}.cv.mp4"
    writer = cv2.VideoWriter(
        temp_cv,
        cv2.VideoWriter_fourcc(*"mp4v"),
        fps,
        (width, height),
    )
    if not writer.isOpened():
        cap.release()
        return False

    frames = 0
    while True:
        ok, frame = cap.read()
        if not ok:
            break
        writer.write(_draw_detection_on_frame(frame, event))
        frames += 1

    writer.release()
    cap.release()

    if frames == 0 or not os.path.isfile(temp_cv) or os.path.getsize(temp_cv) <= 0:
        try:
            os.remove(temp_cv)
        except OSError:
            pass
        return False

    ok = _reencode_h264(temp_cv, out_path)
    try:
        os.remove(temp_cv)
    except OSError:
        pass
    return ok


def _capture_rtsp_clip(
    stream_url: str,
    event: DetectionEvent,
    raw_path: str,
    temp_path: str,
    duration: int,
    event_id: int,
) -> bool:
    if not stream_url:
        return False
    if not _record_raw_clip_rtsp(stream_url, raw_path, duration):
        return False
    final_path = temp_path
    if not _burn_overlay_with_opencv(raw_path, temp_path, event):
        logger.warning("Overlay failed for event %s — saving raw clip", event_id)
        final_path = raw_path
    return os.path.isfile(final_path) and os.path.getsize(final_path) > 0, final_path


def _warm_ml_stream(camera) -> None:
    try:
        from ml.client import ml_live_detections, ml_service_enabled
    except ImportError:
        return
    if not ml_service_enabled():
        return
    for _ in range(3):
        try:
            ml_live_detections(camera.stream_key, rtsp_url=camera.effective_stream_url())
            return
        except Exception:
            time.sleep(0.5)


def capture_detection_clip_sync(camera_id: int, event_id: int) -> None:
    """Record a short clip with this event's class label drawn on every frame."""
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

    duration = _clip_duration_sec()
    _update_clip_status(event_id, ClipStatus.RECORDING)

    temp_dir = os.path.join(settings.MEDIA_ROOT, "detection_clips", "_tmp")
    os.makedirs(temp_dir, exist_ok=True)
    stamp = int(time.time())
    temp_path = os.path.join(temp_dir, f"event_{event_id}_{stamp}.mp4")
    raw_path = os.path.join(temp_dir, f"event_{event_id}_{stamp}_raw.mp4")

    try:
        saved = False
        stream_url = camera.effective_stream_url()
        if stream_url:
            saved, temp_path = _capture_rtsp_clip(
                stream_url, event, raw_path, temp_path, duration, event_id
            )

        if not saved:
            mjpeg_url = _ml_mjpeg_url(camera)
            if mjpeg_url:
                _warm_ml_stream(camera)
                saved = _record_clip_from_mjpeg(mjpeg_url, event, temp_path, duration)

        if not saved and not stream_url:
            logger.debug("Clip capture skipped for event %s: no stream URL", event_id)
            _update_clip_status(event_id, ClipStatus.SKIPPED)
            return

        if not saved:
            _update_clip_status(event_id, ClipStatus.FAILED)
            return

        filename = f"event_{event_id}.mp4"
        with open(temp_path, "rb") as fh:
            event.clip.save(filename, File(fh), save=True)
        _update_clip_status(event_id, ClipStatus.READY)
        logger.info(
            "Saved detection clip for event %s (%s) class=%s",
            event_id,
            event.clip.name,
            _display_class(event),
        )
    except Exception:
        logger.exception("Failed to save clip for detection event %s", event_id)
        _update_clip_status(event_id, ClipStatus.FAILED)
    finally:
        for path in {raw_path, temp_path, f"{temp_path}.cv.mp4"}:
            try:
                if path and os.path.isfile(path):
                    os.remove(path)
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

        with _global_clip_semaphore:
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
                name=f"det-clip-q-{camera_id}",
            )
            thread.start()


def requeue_pending_clips() -> int:
    """Enqueue pending clips left from a previous run."""
    from .models import ClipStatus, DetectionEvent

    close_old_connections()
    rows = list(
        DetectionEvent.objects.filter(clip_status=ClipStatus.PENDING, clip="")
        .order_by("created_at")
        .values_list("camera_id", "id")
    )
    for camera_id, event_id in rows:
        _enqueue_clip(camera_id, event_id)
    if rows:
        logger.info("[clip-capture] Re-queued %s pending clip(s)", len(rows))
    return len(rows)


def schedule_detection_clip(camera_id: int, event_id: int) -> None:
    """Queue clip capture; every detection is recorded in order per camera."""
    from .models import ClipStatus

    if not _clip_enabled():
        _update_clip_status(event_id, ClipStatus.SKIPPED)
        return

    _enqueue_clip(camera_id, event_id)
