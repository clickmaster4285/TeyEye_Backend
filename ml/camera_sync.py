"""Push active camera RTSP URLs to the ML service (one RTSP session per camera key)."""

from __future__ import annotations

import logging

from django.db import close_old_connections

logger = logging.getLogger(__name__)


def collect_active_camera_entries() -> list[dict[str, str]]:
    from cameras.models import Camera

    close_old_connections()
    rows = (
        Camera.objects.filter(
            is_active=True,
            nvr__is_active=True,
            nvr__site__is_active=True,
        )
        .select_related("nvr", "nvr__site")
        .order_by("id")
    )
    entries: list[dict[str, str]] = []
    for camera in rows:
        rtsp_url = (camera.effective_stream_url() or "").strip()
        if not rtsp_url:
            continue
        entries.append(
            {
                "key": camera.stream_key,
                "rtsp_url": rtsp_url,
                "purpose": camera.purpose,
            }
        )
    return entries


def sync_cameras_to_ml(*, retries: int = 3) -> dict | None:
    from .client import MLServiceError, ml_register_cameras_bulk, ml_service_enabled

    if not ml_service_enabled():
        logger.debug("[camera-sync] ML service not configured — skip")
        return None

    entries = collect_active_camera_entries()
    if not entries:
        logger.info("[camera-sync] No active cameras to register")
        return {"registered": 0, "total": 0}

    last_exc: Exception | None = None
    for attempt in range(1, max(1, retries) + 1):
        try:
            result = ml_register_cameras_bulk(entries)
            logger.info(
                "[camera-sync] Registered %s/%s camera stream(s) on ML service",
                result.get("registered", 0),
                result.get("total", len(entries)),
            )
            return result
        except MLServiceError as exc:
            last_exc = exc
            logger.warning(
                "[camera-sync] Attempt %s/%s failed: %s",
                attempt,
                retries,
                exc,
            )
    if last_exc is not None:
        logger.error("[camera-sync] Could not sync cameras to ML: %s", last_exc)
    return None
