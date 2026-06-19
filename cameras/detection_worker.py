"""Background worker: poll ML live detections and persist readings."""

from __future__ import annotations

import logging
import os
import sys
import threading
import time
from pathlib import Path

from django.conf import settings
from django.db import close_old_connections

logger = logging.getLogger(__name__)

_stop_event = threading.Event()
_worker_thread: threading.Thread | None = None
_lock_handle = None


def _lock_path() -> Path:
    base = Path(getattr(settings, "BASE_DIR", Path.cwd()))
    return base / ".detection_worker.lock"


def _acquire_worker_lock():
    lock_path = _lock_path()
    lock_path.parent.mkdir(parents=True, exist_ok=True)
    fh = None
    try:
        fh = open(lock_path, "a+", encoding="utf-8")
        if sys.platform == "win32":
            import msvcrt

            try:
                msvcrt.locking(fh.fileno(), msvcrt.LK_NBLCK, 1)
            except OSError:
                fh.close()
                return None
        else:
            import fcntl

            try:
                fcntl.flock(fh.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
            except BlockingIOError:
                fh.close()
                return None
        fh.seek(0)
        fh.truncate()
        fh.write(f"{os.getpid()}\n")
        fh.flush()
        return fh
    except OSError as exc:
        logger.debug("[detection-worker] Could not acquire lock: %s", exc)
        if fh is not None:
            try:
                fh.close()
            except OSError:
                pass
        return None


def _worker_enabled() -> bool:
    return bool(getattr(settings, "DETECTION_WORKER_ENABLED", True))


def _poll_interval() -> float:
    return max(1.0, float(getattr(settings, "DETECTION_WORKER_INTERVAL_SEC", 2)))


def _camera_refresh_interval() -> int:
    return max(15, int(getattr(settings, "DETECTION_WORKER_CAMERA_REFRESH_SEC", 60)))


def _wait_for_ml(timeout_sec: float = 180.0) -> bool:
    from ml.client import ml_health, ml_service_enabled

    if not ml_service_enabled():
        return False
    deadline = time.monotonic() + timeout_sec
    while time.monotonic() < deadline and not _stop_event.is_set():
        try:
            ml_health()
            return True
        except Exception:
            time.sleep(2.0)
    return False


def _active_camera_ids() -> list[int]:
    from .models import Camera

    return list(
        Camera.objects.filter(
            is_active=True,
            nvr__is_active=True,
            nvr__site__is_active=True,
        )
        .order_by("id")
        .values_list("id", flat=True)
    )


def _poll_camera(camera_id: int) -> int:
    from ml.client import MLServiceError, ml_live_detections, ml_service_enabled

    from .detection_utils import save_detection_batch
    from .models import Camera

    if not ml_service_enabled():
        return 0

    try:
        camera = Camera.objects.select_related("nvr", "nvr__site").get(pk=camera_id)
    except Camera.DoesNotExist:
        return 0

    try:
        result = ml_live_detections(camera.stream_key, rtsp_url=camera.effective_stream_url())
    except MLServiceError as exc:
        logger.debug("ML poll skipped for camera %s: %s", camera_id, exc)
        return 0

    detections = result.get("detections") or []
    if not detections:
        return 0
    return save_detection_batch(camera, detections)


def run_worker_forever() -> None:
    """Poll cameras round-robin and save detections until stopped."""
    if not _worker_enabled():
        logger.info("[detection-worker] Disabled via DETECTION_WORKER_ENABLED")
        return

    if not _wait_for_ml():
        logger.warning("[detection-worker] ML service not ready — retrying in loop")

    camera_ids: list[int] = []
    index = 0
    last_refresh = 0.0
    interval = _poll_interval()
    refresh_sec = _camera_refresh_interval()

    logger.info(
        "[detection-worker] Started (pid=%s, interval=%.1fs, refresh=%ss)",
        os.getpid(),
        interval,
        refresh_sec,
    )

    while not _stop_event.is_set():
        close_old_connections()
        now = time.monotonic()
        if not camera_ids or now - last_refresh >= refresh_sec:
            camera_ids = _active_camera_ids()
            last_refresh = now
            if camera_ids:
                logger.info("[detection-worker] Tracking %s active camera(s)", len(camera_ids))
            else:
                logger.debug("[detection-worker] No active cameras configured")

        if camera_ids:
            cam_id = camera_ids[index % len(camera_ids)]
            index += 1
            try:
                saved = _poll_camera(cam_id)
                if saved:
                    logger.info("[detection-worker] Saved %s detection(s) for camera %s", saved, cam_id)
            except Exception:
                logger.exception("[detection-worker] Unexpected error polling camera %s", cam_id)

        _stop_event.wait(interval)

    logger.info("[detection-worker] Stopped")


def stop_background_worker() -> None:
    global _lock_handle
    _stop_event.set()
    if _worker_thread is not None and _worker_thread.is_alive():
        _worker_thread.join(timeout=10.0)
    if _lock_handle is not None:
        try:
            _lock_handle.close()
        except OSError:
            pass
        _lock_handle = None


def should_autostart_in_process() -> bool:
    if not _worker_enabled():
        return False
    if not getattr(settings, "DETECTION_WORKER_AUTO_START", True):
        return False
    if os.environ.get("TEKEYE_DETECTION_WORKER") == "1":
        return False
    if "run_detection_worker" in sys.argv:
        return False
    if "runserver" in sys.argv and os.environ.get("RUN_MAIN") != "true":
        return False
    return True


def maybe_start_background_worker() -> None:
    """Start daemon thread when Django boots (dev / single-process)."""
    global _worker_thread, _lock_handle

    if not should_autostart_in_process():
        return
    if _worker_thread is not None and _worker_thread.is_alive():
        return

    lock = _acquire_worker_lock()
    if lock is None:
        logger.debug("[detection-worker] Another process already holds the worker lock")
        return

    _lock_handle = lock
    _stop_event.clear()
    _worker_thread = threading.Thread(
        target=run_worker_forever,
        daemon=True,
        name="detection-worker",
    )
    _worker_thread.start()
    logger.info("[detection-worker] Background thread started")
