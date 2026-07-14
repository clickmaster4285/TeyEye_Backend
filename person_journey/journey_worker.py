"""Sync cameras to ML journey pipeline and start ML journey processing."""

from __future__ import annotations

import logging
import os
import threading
import time

from django.conf import settings

logger = logging.getLogger(__name__)

_stop = threading.Event()
_thread: threading.Thread | None = None


def _interval() -> int:
    return max(10, int(getattr(settings, "PERSON_JOURNEY_SYNC_INTERVAL_SEC", 60)))


def sync_cameras_to_journey_ml() -> dict:
    from cameras.models import Camera
    from ml.client import ml_service_enabled

    if not ml_service_enabled():
        return {"synced": 0, "reason": "ml_disabled"}

    cameras = Camera.objects.filter(is_active=True, nvr__isnull=False).select_related("nvr", "nvr__site")
    entries = []
    for cam in cameras:
        try:
            entries.append(
                {
                    "key": cam.stream_key,
                    "rtsp_url": cam.effective_stream_url(),
                    "camera_id": cam.pk,
                    "zone": cam.zone or "",
                    "name": cam.name,
                }
            )
        except Exception as exc:
            logger.warning("Journey sync skip camera %s: %s", cam.pk, exc)

    if not entries:
        return {"synced": 0}

    import requests

    base = getattr(settings, "ML_SERVICE_URL", "").rstrip("/")
    backend_url = getattr(settings, "PERSON_JOURNEY_BACKEND_URL", "http://127.0.0.1:8000")
    ingest_token = getattr(settings, "PERSON_JOURNEY_INGEST_TOKEN", "")
    try:
        res = requests.post(
            f"{base}/journey/register/bulk",
            json={
                "cameras": entries,
                "backend_ingest_url": f"{backend_url.rstrip('/')}/api/person-journey/ingest/",
                "ingest_token": ingest_token,
            },
            timeout=30,
        )
        res.raise_for_status()
        return res.json()
    except Exception as exc:
        logger.warning("Journey ML camera sync failed (restart ml_services api_server.py): %s", exc)
        return {"synced": 0, "error": str(exc), "hint": "Restart ML server to enable /journey/register/bulk"}


def _worker_loop():
    from django.db import close_old_connections

    while not _stop.is_set():
        close_old_connections()
        try:
            sync_cameras_to_journey_ml()
        except Exception:
            logger.exception("Journey sync worker iteration failed")
        _stop.wait(_interval())


def start_journey_worker_thread():
    global _thread
    if _thread and _thread.is_alive():
        return
    _stop.clear()
    _thread = threading.Thread(target=_worker_loop, daemon=True, name="person-journey-sync")
    _thread.start()
    logger.info("Person journey camera sync worker started (interval=%ss)", _interval())
    try:
        result = sync_cameras_to_journey_ml()
        logger.info("Person journey initial ML sync: %s", result)
    except Exception:
        logger.exception("Person journey initial ML sync failed")