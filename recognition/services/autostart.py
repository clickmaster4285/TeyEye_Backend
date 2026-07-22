"""Autostart InsightFace CCTV attendance workers when the server boots."""

from __future__ import annotations

import logging
import threading

from django.db import close_old_connections

logger = logging.getLogger(__name__)


def collect_attendance_cameras() -> list[dict]:
    """Active attendance-capable cameras with a resolvable RTSP URL."""
    from cameras.models import Camera, CameraPurpose

    purposes = [
        CameraPurpose.ATTENDANCE,
        CameraPurpose.FACE_RECOGNITION,
        CameraPurpose.SURVEILLANCE,
        CameraPurpose.ZONE_MONITORING,
    ]
    cameras = []
    for cam in (
        Camera.objects.filter(is_active=True, purpose__in=purposes)
        .select_related("nvr")
        .order_by("code", "id")
    ):
        try:
            url = cam.effective_stream_url()
        except Exception as exc:
            logger.warning("Autostart: skip camera %s: %s", cam.id, exc)
            continue
        if not url:
            continue
        cameras.append({
            "id": cam.id,
            "name": cam.name or cam.code or f"Camera {cam.id}",
            "rtsp_url": url,
        })
    return cameras


def _autostart_worker(delay_seconds: float):
    import time

    time.sleep(delay_seconds)
    try:
        close_old_connections()
        from recognition.services.cctv_worker import get_cctv_manager

        cameras = collect_attendance_cameras()
        if not cameras:
            logger.info("CCTV autostart: no active attendance cameras found")
            return
        manager = get_cctv_manager()
        statuses = manager.start_all(cameras)
        logger.info("CCTV autostart: started %d attendance workers", len(statuses))
    except Exception:
        logger.exception("CCTV autostart failed")
    finally:
        close_old_connections()


def schedule_autostart(delay_seconds: float = 3.0):
    """Start workers in a daemon thread shortly after boot (non-blocking)."""
    thread = threading.Thread(
        target=_autostart_worker,
        args=(delay_seconds,),
        name="cctv-attendance-autostart",
        daemon=True,
    )
    thread.start()
