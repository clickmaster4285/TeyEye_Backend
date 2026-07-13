"""Poll ML live detections and record every visible person into Person Journey."""

from __future__ import annotations

import logging
import os
import threading
import time

from django.conf import settings
from django.db import close_old_connections

logger = logging.getLogger(__name__)

_stop = threading.Event()
_thread: threading.Thread | None = None


def _enabled() -> bool:
    return bool(getattr(settings, "PERSON_JOURNEY_LIVE_INGEST_ENABLED", True))


def _interval() -> float:
    return max(1.0, float(getattr(settings, "PERSON_JOURNEY_LIVE_INGEST_INTERVAL_SEC", 2)))


def _camera_refresh() -> int:
    return max(15, int(getattr(settings, "PERSON_JOURNEY_LIVE_CAMERA_REFRESH_SEC", 60)))


def _active_camera_ids() -> list[int]:
    from cameras.models import Camera

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

    from .live_ingest import ingest_camera_detections

    if not ml_service_enabled():
        return 0

    from cameras.models import Camera

    try:
        camera = Camera.objects.select_related("nvr", "nvr__site").get(pk=camera_id)
    except Camera.DoesNotExist:
        return 0

    try:
        result = ml_live_detections(camera.stream_key, rtsp_url=camera.effective_stream_url())
    except MLServiceError as exc:
        logger.debug("Journey live poll skipped camera %s: %s", camera_id, exc)
        return 0

    detections = result.get("detections") or []
    if not detections:
        return 0
    return ingest_camera_detections(camera, detections)


def _worker_loop() -> None:
    camera_ids: list[int] = []
    index = 0
    last_refresh = 0.0
    refresh_sec = _camera_refresh()
    interval = _interval()

    logger.info(
        "Person journey live ingest started (interval=%.1fs, cameras refresh=%ss)",
        interval,
        refresh_sec,
    )

    while not _stop.is_set():
        close_old_connections()
        now = time.monotonic()
        if not camera_ids or now - last_refresh >= refresh_sec:
            camera_ids = _active_camera_ids()
            last_refresh = now
            if camera_ids:
                logger.info("Journey live ingest tracking %s camera(s)", len(camera_ids))

        if camera_ids:
            cam_id = camera_ids[index % len(camera_ids)]
            index += 1
            try:
                count = _poll_camera(cam_id)
                if count:
                    logger.debug("Journey live ingest camera %s: %s persons", cam_id, count)
            except Exception:
                logger.exception("Journey live ingest failed for camera %s", cam_id)

        _stop.wait(interval)


def start_live_ingest_worker() -> None:
    global _thread
    if not _enabled():
        logger.info("Person journey live ingest disabled")
        return
    if _thread and _thread.is_alive():
        return
    _stop.clear()
    _thread = threading.Thread(target=_worker_loop, daemon=True, name="person-journey-live-ingest")
    _thread.start()
