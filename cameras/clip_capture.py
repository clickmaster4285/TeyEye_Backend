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
from django.core.files.base import ContentFile
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


def _ml_raw_mjpeg_url(camera) -> str | None:
    try:
        from ml.client import ml_live_mjpeg_raw_url, ml_service_enabled
    except ImportError:
        return None
    if not ml_service_enabled():
        return None
    return ml_live_mjpeg_raw_url(camera.stream_key, rtsp_url=camera.effective_stream_url())


def _ml_attendance_mjpeg_url(camera, *, target_width: int) -> str | None:
    """HD frames from ML main-stream session (avoids NVR substream on 2nd RTSP connection)."""
    try:
        from ml.client import ml_live_mjpeg_attendance_url, ml_service_enabled
    except ImportError:
        return None
    if not ml_service_enabled():
        return None
    return ml_live_mjpeg_attendance_url(
        camera.stream_key,
        rtsp_url=camera.effective_stream_url(),
        width=target_width,
    )


def _rtsp_input_extra() -> list[str]:
    return [
        "-rtsp_transport",
        "tcp",
        "-fflags",
        "+discardcorrupt",
        "-err_detect",
        "ignore_err",
    ]


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

    x1 = int(max(0, min(x1, frame_w - 1)))
    y1 = int(max(0, min(y1, frame_h - 1)))
    x2 = int(max(x1 + 1, min(x2, frame_w)))
    y2 = int(max(y1 + 1, min(y2, frame_h)))
    return [x1, y1, x2, y2]


def _map_bbox_to_capture_frame(
    bbox: list,
    src_w: int,
    src_h: int,
    dst_w: int,
    dst_h: int,
) -> list[int] | None:
    """Map detection bbox from inference resolution to captured clip frame size."""
    if not isinstance(bbox, (list, tuple)) or len(bbox) < 4:
        return None
    if src_w <= 0 or src_h <= 0 or dst_w <= 0 or dst_h <= 0:
        return _fit_bbox_to_frame(bbox, dst_w, dst_h)
    try:
        x1, y1, x2, y2 = (float(v) for v in bbox[:4])
    except (TypeError, ValueError):
        return None
    sx = dst_w / float(src_w)
    sy = dst_h / float(src_h)
    return _fit_bbox_to_frame([x1 * sx, y1 * sy, x2 * sx, y2 * sy], dst_w, dst_h)


def _labels_match_staff(det: dict, label: str, employee_name: str) -> bool:
    det_label = str(det.get("label") or "").strip().lower()
    if not det_label or det_label in _GENERIC_EMPLOYEE_LABELS:
        return False
    targets = {label.strip().lower(), employee_name.strip().lower()}
    targets.discard("")
    return det_label in targets


_GENERIC_EMPLOYEE_LABELS = frozenset({"unknown", "person", "face", ""})


def _staff_bbox_from_ml(
    camera,
    label: str,
    employee_name: str,
    frame_w: int,
    frame_h: int,
    fallback_bbox: list,
    *,
    fallback_confidence: float = 0.0,
    infer_frame_w: int = 0,
    infer_frame_h: int = 0,
) -> tuple[list[int] | None, float]:
    """Resolve staff bbox from live ML detections, mapped to the captured frame size."""
    try:
        from ml.client import ml_live_detections, ml_service_enabled
    except ImportError:
        fitted = _fit_bbox_to_frame(fallback_bbox, frame_w, frame_h)
        return fitted, fallback_confidence

    if not ml_service_enabled():
        fitted = _fit_bbox_to_frame(fallback_bbox, frame_w, frame_h)
        return fitted, fallback_confidence

    try:
        payload = ml_live_detections(camera.stream_key, rtsp_url=camera.effective_stream_url())
    except Exception:
        fitted = _fit_bbox_to_frame(fallback_bbox, frame_w, frame_h)
        return fitted, fallback_confidence

    infer_w = int(payload.get("frame_width") or infer_frame_w or 0)
    infer_h = int(payload.get("frame_height") or infer_frame_h or 0)

    for det in payload.get("detections") or []:
        cls = str(det.get("class_name") or det.get("label") or "").strip().lower()
        if cls not in ("person", "face"):
            continue
        if not _labels_match_staff(det, label, employee_name):
            continue
        src_w = int(det.get("frame_width") or infer_w or frame_w)
        src_h = int(det.get("frame_height") or infer_h or frame_h)
        fitted = _map_bbox_to_capture_frame(det.get("bbox") or [], src_w, src_h, frame_w, frame_h)
        if fitted:
            try:
                conf = float(det.get("confidence", fallback_confidence))
            except (TypeError, ValueError):
                conf = fallback_confidence
            return fitted, conf

    src_w = infer_w or frame_w
    src_h = infer_h or frame_h
    fitted = _map_bbox_to_capture_frame(fallback_bbox, src_w, src_h, frame_w, frame_h)
    return fitted, fallback_confidence


def _draw_attendance_staff_on_frame(
    frame,
    *,
    bbox: list[int] | None,
    display_name: str,
    confidence: float,
):
    """Draw only the attendance staff box + label (no top-left banner)."""
    import cv2

    output = frame.copy()
    if not bbox:
        return output

    h, w = output.shape[:2]
    x1, y1, x2, y2 = bbox
    color = (0, 220, 0)
    font = cv2.FONT_HERSHEY_SIMPLEX
    font_scale = max(0.45, h / 720 * 0.45)
    thickness = max(1, int(font_scale * 1.5))
    box_thickness = max(2, int(font_scale * 1.2))

    cv2.rectangle(output, (x1, y1), (x2, y2), color, box_thickness)
    label = f"{display_name} {confidence:.2f}".strip()
    (text_w, text_h), baseline = cv2.getTextSize(label, font, font_scale, thickness)
    text_x = int(x1)
    text_y = max(text_h + 4, int(y1) - 4)
    cv2.rectangle(
        output,
        (text_x, text_y - text_h - 3),
        (text_x + text_w + 4, text_y + baseline + 2),
        (0, 0, 0),
        -1,
    )
    cv2.putText(
        output,
        label,
        (text_x + 2, text_y),
        font,
        font_scale,
        color,
        thickness,
        cv2.LINE_AA,
    )
    return output


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

    try:
        import cv2
    except ImportError:
        _update_clip_status(event_id, ClipStatus.FAILED)
        return

    frame = None
    stream_url = camera.effective_stream_url()
    if stream_url:
        frame = _read_rtsp_snapshot(stream_url)

    if frame is None:
        raw_mjpeg_url = _ml_raw_mjpeg_url(camera)
        if raw_mjpeg_url:
            _warm_ml_stream(camera)
            frame = _read_mjpeg_snapshot(raw_mjpeg_url)

    if frame is None:
        if not stream_url and not _ml_raw_mjpeg_url(camera):
            _update_clip_status(event_id, ClipStatus.SKIPPED)
        else:
            _update_clip_status(event_id, ClipStatus.FAILED)
        return

    annotated = _draw_detection_on_frame(frame, event)
    ok, encoded = cv2.imencode(".jpg", annotated, [int(cv2.IMWRITE_JPEG_QUALITY), 88])
    if not ok or encoded is None:
        logger.warning("JPEG encode failed for detection event %s", event_id)
        _update_clip_status(event_id, ClipStatus.FAILED)
        return

    try:
        event.refresh_from_db(fields=["clip", "clip_status"])
        if event.clip:
            _update_clip_status(event_id, ClipStatus.READY)
            return

        filename = f"event_{event_id}.jpg"
        event.clip.save(filename, ContentFile(encoded.tobytes()), save=True)
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


def _ml_annotated_mjpeg_url(camera) -> str | None:
    try:
        from ml.client import ml_live_mjpeg_url, ml_service_enabled
    except ImportError:
        return None
    if not ml_service_enabled():
        return None
    return ml_live_mjpeg_url(camera.stream_key, rtsp_url=camera.effective_stream_url())


def _attendance_video_seconds() -> float:
    return max(1.0, float(getattr(settings, "ATTENDANCE_VIDEO_SECONDS", 5)))


def _attendance_video_fps() -> int:
    return max(4, min(25, int(getattr(settings, "ATTENDANCE_VIDEO_FPS", 10))))


def _attendance_video_width() -> int:
    return max(640, min(3840, int(getattr(settings, "ATTENDANCE_VIDEO_WIDTH", 1280))))


def _attendance_jpeg_quality() -> int:
    return max(80, min(100, int(getattr(settings, "ATTENDANCE_VIDEO_JPEG_QUALITY", 95))))


def _attendance_video_crf() -> int:
    return max(15, min(28, int(getattr(settings, "ATTENDANCE_VIDEO_CRF", 18))))


def _upscale_frames_to_hd(frames: list, target_width: int) -> list:
    """Upscale frames to HD width when the capture source was lower resolution."""
    try:
        import cv2
    except ImportError:
        return frames
    if not frames:
        return frames
    h, w = frames[0].shape[:2]
    if w >= target_width:
        return frames
    scale = target_width / float(w)
    new_w = target_width
    new_h = max(1, int(h * scale))
    return [cv2.resize(f, (new_w, new_h), interpolation=cv2.INTER_LANCZOS4) for f in frames]


def _read_rtsp_clip(
    stream_url: str,
    *,
    duration_sec: float,
    max_fps: int,
    target_width: int,
    on_frame=None,
) -> list:
    """Capture HD frames directly from RTSP via ffmpeg (best quality for attendance clips)."""
    try:
        import cv2
        import glob
        import shutil
    except ImportError:
        return []

    temp_dir = os.path.join(
        settings.MEDIA_ROOT,
        "attendance",
        "videos",
        "_tmp",
        f"rtsp_{int(time.time() * 1000)}",
    )
    os.makedirs(temp_dir, exist_ok=True)
    pattern = os.path.join(temp_dir, "frame_%04d.jpg")

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
        f"{duration_sec:.2f}",
        "-vf",
        f"scale={target_width}:-2:flags=lanczos",
        "-r",
        str(max(4, max_fps)),
        "-q:v",
        "2",
        pattern,
    ]
    frames: list = []
    try:
        proc = subprocess.run(cmd, capture_output=True, timeout=int(duration_sec) + 60)
        if proc.returncode != 0:
            logger.warning("RTSP clip ffmpeg failed: %s", (proc.stderr or b"")[:300])
            return []
        for path in sorted(glob.glob(os.path.join(temp_dir, "frame_*.jpg"))):
            frame = cv2.imread(path)
            if frame is None:
                continue
            if on_frame is not None:
                frame = on_frame(frame)
            frames.append(frame)
    except (FileNotFoundError, subprocess.TimeoutExpired) as exc:
        logger.warning("RTSP clip capture failed: %s", exc)
    finally:
        shutil.rmtree(temp_dir, ignore_errors=True)
    return frames


def _read_mjpeg_clip(
    mjpeg_url: str,
    *,
    duration_sec: float,
    max_fps: int = 10,
    on_frame=None,
) -> list:
    """Collect frames from MJPEG for the full wall-clock duration."""
    try:
        import cv2
        import numpy as np
    except ImportError:
        return []

    frames: list = []
    end_time = time.monotonic() + duration_sec
    min_interval = 1.0 / max(1, max_fps)
    last_saved = 0.0

    try:
        with requests.get(
            mjpeg_url,
            stream=True,
            timeout=(5, max(30, int(duration_sec) + 15)),
        ) as resp:
            if resp.status_code != 200:
                return []
            buffer = b""
            for chunk in resp.iter_content(chunk_size=8192):
                if time.monotonic() >= end_time:
                    break
                if not chunk:
                    time.sleep(0.01)
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
                    now = time.monotonic()
                    if now - last_saved < min_interval:
                        continue
                    last_saved = now
                    if on_frame is not None:
                        frame = on_frame(frame)
                    frames.append(frame)
    except requests.RequestException as exc:
        logger.warning("MJPEG clip capture failed: %s", exc)
    return frames


def _encode_frames_to_mp4(frames: list, dest_path: str, *, duration_sec: float, nominal_fps: int) -> bool:
    if not frames:
        return False
    try:
        import cv2
    except ImportError:
        return False

    import tempfile

    h, w = frames[0].shape[:2]
    os.makedirs(os.path.dirname(dest_path), exist_ok=True)
    output_fps = max(1.0, len(frames) / max(0.5, float(duration_sec)))
    jpeg_q = _attendance_jpeg_quality()
    crf = _attendance_video_crf()

    with tempfile.TemporaryDirectory(prefix="att_clip_") as tmp:
        for idx, frame in enumerate(frames):
            path = os.path.join(tmp, f"frame_{idx:04d}.jpg")
            if not cv2.imwrite(path, frame, [int(cv2.IMWRITE_JPEG_QUALITY), jpeg_q]):
                return False

        cmd = [
            ffmpeg_path(),
            "-y",
            "-nostdin",
            "-hide_banner",
            "-loglevel",
            "error",
            "-framerate",
            f"{output_fps:.3f}",
            "-i",
            os.path.join(tmp, "frame_%04d.jpg"),
            "-c:v",
            "libx264",
            "-crf",
            str(crf),
            "-preset",
            "medium",
            "-pix_fmt",
            "yuv420p",
            "-movflags",
            "+faststart",
            dest_path,
        ]
        try:
            proc = subprocess.run(cmd, capture_output=True, timeout=90)
        except (FileNotFoundError, subprocess.TimeoutExpired) as exc:
            logger.warning("ffmpeg MP4 encode failed: %s", exc)
            return False

        if proc.returncode == 0 and os.path.isfile(dest_path) and os.path.getsize(dest_path) > 0:
            return True

        # Fallback codec when libx264 is unavailable.
        cmd[cmd.index("libx264")] = "mpeg4"
        try:
            proc = subprocess.run(cmd, capture_output=True, timeout=90)
        except (FileNotFoundError, subprocess.TimeoutExpired):
            return False
        return proc.returncode == 0 and os.path.isfile(dest_path) and os.path.getsize(dest_path) > 0


def _attendance_overlay(label: str, employee_name: str, class_name: str, bbox: list):
    from types import SimpleNamespace

    display_name = (employee_name or label or "staff").strip()[:80]
    return SimpleNamespace(
        label=(label or "")[:120],
        class_name=(class_name or "person")[:80],
        employee_name=display_name,
        bbox=bbox or [],
        is_alert=False,
    )


def _attendance_snapshot_enabled() -> bool:
    return bool(getattr(settings, "ATTENDANCE_SNAPSHOT_ENABLED", True))


def capture_attendance_snapshot_sync(
    camera_id: int,
    attendance_id: int,
    *,
    label: str,
    employee_name: str,
    class_name: str,
    bbox: list,
    confidence: float,
    action: str,
    infer_frame_w: int = 0,
    infer_frame_h: int = 0,
) -> None:
    """Record attendance clip with a label on the marked staff member only."""
    from users.models import Attendance

    if not _attendance_snapshot_enabled():
        return

    close_old_connections()

    try:
        from .models import Camera

        camera = Camera.objects.select_related("nvr").get(pk=camera_id)
        attendance = Attendance.objects.get(pk=attendance_id)
    except (Camera.DoesNotExist, Attendance.DoesNotExist):
        return

    try:
        import cv2
    except ImportError:
        logger.warning("OpenCV not available for attendance clip capture")
        return

    duration = _attendance_video_seconds()
    fps = _attendance_video_fps()
    hd_width = _attendance_video_width()
    jpeg_q = _attendance_jpeg_quality()
    display_name = (employee_name or label or "staff").strip()[:80]
    frames: list = []
    bbox_state: dict[str, object] = {
        "bbox": None,
        "conf": confidence,
        "at": 0.0,
        "infer_w": int(infer_frame_w or 0),
        "infer_h": int(infer_frame_h or 0),
    }

    def _current_staff_box(frame_w: int, frame_h: int) -> tuple[list[int] | None, float]:
        now = time.monotonic()
        if bbox_state["bbox"] is None or now - float(bbox_state["at"]) >= 0.1:
            fitted, conf = _staff_bbox_from_ml(
                camera,
                label,
                employee_name,
                frame_w,
                frame_h,
                bbox or [],
                fallback_confidence=confidence,
                infer_frame_w=int(bbox_state["infer_w"] or 0),
                infer_frame_h=int(bbox_state["infer_h"] or 0),
            )
            bbox_state["bbox"] = fitted
            bbox_state["conf"] = conf
            bbox_state["at"] = now
        return bbox_state["bbox"], float(bbox_state["conf"])  # type: ignore[return-value]

    def _annotate_frame(frame):
        h, w = frame.shape[:2]
        fitted, conf = _current_staff_box(w, h)
        return _draw_attendance_staff_on_frame(
            frame,
            bbox=fitted,
            display_name=display_name,
            confidence=conf,
        )

    _warm_ml_stream(camera)
    stream_url = camera.effective_stream_url()

    # 1) HD main-stream via ML + label only the marked staff member.
    attendance_url = _ml_attendance_mjpeg_url(camera, target_width=hd_width)
    if attendance_url:
        frames = _read_mjpeg_clip(
            attendance_url,
            duration_sec=duration,
            max_fps=fps,
            on_frame=_annotate_frame,
        )

    # 2) Raw MJPEG + single staff overlay.
    if not frames:
        raw_url = _ml_raw_mjpeg_url(camera)
        if raw_url:
            frames = _read_mjpeg_clip(
                raw_url,
                duration_sec=duration,
                max_fps=fps,
                on_frame=_annotate_frame,
            )
            frames = _upscale_frames_to_hd(frames, hd_width)

    # 3) Last resort: separate RTSP (may be substream on some NVRs).
    if not frames and stream_url:
        frames = _read_rtsp_clip(
            stream_url,
            duration_sec=duration,
            max_fps=fps,
            target_width=hd_width,
            on_frame=_annotate_frame,
        )

    if not frames and stream_url:
        single = _read_rtsp_snapshot(stream_url)
        if single is not None:
            frames = _upscale_frames_to_hd([_annotate_frame(single)], hd_width)

    if not frames:
        logger.warning("Could not capture attendance clip for record %s", attendance_id)
        return

    temp_dir = os.path.join(settings.MEDIA_ROOT, "attendance", "videos", "_tmp")
    os.makedirs(temp_dir, exist_ok=True)
    temp_mp4 = os.path.join(temp_dir, f"attendance_{attendance_id}_{int(time.time())}.mp4")

    try:
        attendance.refresh_from_db(fields=["image", "video"])

        if len(frames) > 1 and _encode_frames_to_mp4(
            frames, temp_mp4, duration_sec=duration, nominal_fps=fps
        ):
            filename = f"attendance_{attendance_id}_{action}.mp4"
            with open(temp_mp4, "rb") as fh:
                attendance.video.save(filename, ContentFile(fh.read()), save=False)

        poster = frames[0]
        ok, encoded = cv2.imencode(".jpg", poster, [int(cv2.IMWRITE_JPEG_QUALITY), jpeg_q])
        if ok and encoded is not None:
            attendance.image.save(
                f"attendance_{attendance_id}_{action}.jpg",
                ContentFile(encoded.tobytes()),
                save=False,
            )

        attendance.save(update_fields=["image", "video"])
        logger.info(
            "Saved attendance clip for record %s video=%s action=%s frames=%s duration=%.1fs",
            attendance_id,
            attendance.video.name if attendance.video else "none",
            action,
            len(frames),
            duration,
        )
    except Exception:
        logger.exception("Failed to save attendance clip for record %s", attendance_id)
    finally:
        try:
            if os.path.isfile(temp_mp4):
                os.remove(temp_mp4)
        except OSError:
            pass


def schedule_attendance_snapshot(
    camera_id: int,
    attendance_id: int,
    *,
    label: str,
    employee_name: str,
    class_name: str,
    bbox: list,
    confidence: float,
    action: str,
    infer_frame_w: int = 0,
    infer_frame_h: int = 0,
) -> None:
    """Capture attendance proof clip — only the marked staff member is labeled."""
    if not _attendance_snapshot_enabled():
        return

    payload = {
        "camera_id": camera_id,
        "attendance_id": attendance_id,
        "label": label,
        "employee_name": employee_name,
        "class_name": class_name,
        "bbox": bbox,
        "confidence": confidence,
        "action": action,
        "infer_frame_w": infer_frame_w,
        "infer_frame_h": infer_frame_h,
    }

    def _run() -> None:
        with _camera_lock(camera_id):
            capture_attendance_snapshot_sync(**payload)

    thread = threading.Thread(
        target=_run,
        daemon=True,
        name=f"attendance-snap-{attendance_id}",
    )
    thread.start()
