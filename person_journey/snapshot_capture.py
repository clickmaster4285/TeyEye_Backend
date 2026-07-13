"""Capture and attach person journey snapshots (full HD frame with person highlighted)."""

from __future__ import annotations

import logging
import threading
from collections import deque

from django.conf import settings
from django.core.files.base import ContentFile
from django.core.files.storage import default_storage
from django.db import close_old_connections, transaction
from django.utils import timezone

logger = logging.getLogger(__name__)

_crop_queue: deque[int] = deque()
_crop_guard = threading.Lock()
_crop_workers = 0
_MAX_CROP_WORKERS = 3


def _ensure_db_connection() -> None:
    close_old_connections()
    from django.db import connection

    connection.ensure_connection()


def _journey_jpeg_quality() -> int:
    return max(90, min(100, int(getattr(settings, "JOURNEY_SNAPSHOT_JPEG_QUALITY", 98))))


def _journey_full_frame() -> bool:
    return bool(getattr(settings, "JOURNEY_SNAPSHOT_FULL_FRAME", True))


def link_detection_clip_to_journey(detection_event_id: int, clip_url: str) -> int:
    """Legacy hook — only fill journey rows that still have no dedicated snapshot."""
    url = (clip_url or "").strip()
    if not detection_event_id or not url:
        return 0
    from .models import JourneyEvent

    return JourneyEvent.objects.filter(
        detection_event_id=detection_event_id,
        snapshot_path="",
    ).update(snapshot_path=url)


def _resolve_crop_box(bbox, frame_w: int, frame_h: int, camera, detection) -> list[int] | None:
    """Map detection bbox to captured frame coordinates."""
    from cameras.clip_capture import _fit_bbox_to_frame, _map_bbox_to_capture_frame

    if not bbox or len(bbox) < 4:
        return None

    try:
        x2 = float(bbox[2])
        y2 = float(bbox[3])
    except (TypeError, ValueError):
        return None

    infer_w = infer_h = 0
    if detection is not None:
        meta = getattr(detection, "metadata", None) or {}
        if isinstance(meta, dict):
            infer_w = int(meta.get("frame_width") or 0)
            infer_h = int(meta.get("frame_height") or 0)

    if infer_w <= 0 or infer_h <= 0:
        try:
            from ml.client import ml_live_detections, ml_service_enabled

            if camera and ml_service_enabled():
                payload = ml_live_detections(
                    camera.stream_key,
                    rtsp_url=camera.effective_stream_url(),
                )
                infer_w = int(payload.get("frame_width") or 0)
                infer_h = int(payload.get("frame_height") or 0)
        except Exception:
            pass

    if x2 > frame_w or y2 > frame_h:
        if infer_w <= 0 or infer_h <= 0:
            infer_w = max(int(x2 * 1.05), frame_w)
            infer_h = max(int(y2 * 1.05), frame_h)
        return _map_bbox_to_capture_frame(bbox, infer_w, infer_h, frame_w, frame_h)

    return _fit_bbox_to_frame(bbox, frame_w, frame_h)


def _person_label(journey_event) -> str:
    person = journey_event.journey_person
    meta = journey_event.metadata or {}
    if isinstance(meta, dict):
        face_label = str(meta.get("face_label") or meta.get("label") or "").strip()
        if face_label and face_label.lower() not in {"unknown", "person", "face", ""}:
            return face_label[:80]
    if person:
        return (person.display_name or person.code or "Person")[:80]
    return "Person"


def _extract_person_crop(frame, crop_box: list[int] | None):
    """Tight person crop used only for ReID embedding (not saved as snapshot)."""
    if crop_box is None:
        return None
    h, w = frame.shape[:2]
    x1, y1, x2, y2 = crop_box
    pad = int(0.08 * max(x2 - x1, y2 - y1, 1))
    x1 = max(0, x1 - pad)
    y1 = max(0, y1 - pad)
    x2 = min(w, x2 + pad)
    y2 = min(h, y2 + pad)
    if x2 <= x1 or y2 <= y1:
        return None
    return frame[y1:y2, x1:x2].copy()


def capture_journey_crop_sync(journey_event_id: int) -> str:
    """Capture a full HD camera frame with the person boxed and labeled."""
    _ensure_db_connection()
    try:
        import cv2
    except ImportError:
        logger.warning("OpenCV not available for journey snapshot capture")
        return ""

    try:
        from cameras.clip_capture import draw_journey_snapshot_on_frame, read_journey_hd_frame
        from cameras.models import DetectionEvent

        from .models import JourneyEvent

        journey_event = (
            JourneyEvent.objects.select_related("camera", "camera__nvr", "journey_person")
            .filter(pk=journey_event_id)
            .first()
        )
        if journey_event is None or journey_event.camera_id is None:
            return ""

        existing = (journey_event.snapshot_path or "").strip()
        if existing and "journey_snapshots/" in existing:
            return existing

        detection = None
        if journey_event.detection_event_id:
            detection = DetectionEvent.objects.filter(pk=journey_event.detection_event_id).first()

        camera = journey_event.camera
        frame = read_journey_hd_frame(camera)
        if frame is None:
            return ""

        h, w = frame.shape[:2]
        bbox = journey_event.bbox or (detection.bbox if detection else []) or []
        crop_box = _resolve_crop_box(bbox, w, h, camera, detection)
        person_label = _person_label(journey_event)
        confidence = journey_event.confidence
        camera_name = (camera.name or camera.zone or "").strip() if camera else ""

        if _journey_full_frame():
            output = draw_journey_snapshot_on_frame(
                frame,
                bbox=crop_box,
                person_label=person_label,
                camera_name=camera_name,
                confidence=confidence,
            )
        elif crop_box:
            output = _extract_person_crop(frame, crop_box) or frame
        else:
            output = frame

        jpeg_q = _journey_jpeg_quality()
        ok, encoded = cv2.imencode(".jpg", output, [int(cv2.IMWRITE_JPEG_QUALITY), jpeg_q])
        if not ok or encoded is None:
            return ""

        jpeg_bytes = encoded.tobytes()
        today = timezone.localdate()
        rel_path = f"journey_snapshots/{today:%Y/%m/%d}/je_{journey_event_id}.jpg"
        saved_path = default_storage.save(rel_path, ContentFile(jpeg_bytes))
        url = default_storage.url(saved_path)
        JourneyEvent.objects.filter(pk=journey_event_id).update(snapshot_path=url)

        if journey_event.journey_person_id:
            from .unknown_resolution import update_person_embeddings_from_crop

            person_crop = _extract_person_crop(frame, crop_box)
            if person_crop is not None:
                ok_crop, crop_encoded = cv2.imencode(
                    ".jpg", person_crop, [int(cv2.IMWRITE_JPEG_QUALITY), jpeg_q]
                )
                if ok_crop and crop_encoded is not None:
                    update_person_embeddings_from_crop(
                        journey_event.journey_person, crop_encoded.tobytes()
                    )
            else:
                update_person_embeddings_from_crop(journey_event.journey_person, jpeg_bytes)

        logger.info(
            "Saved journey snapshot for event %s (%s, %sx%s)",
            journey_event_id,
            saved_path,
            output.shape[1],
            output.shape[0],
        )
        return url
    except Exception:
        logger.exception("Journey snapshot capture failed for event %s", journey_event_id)
        return ""
    finally:
        close_old_connections()


def _process_crop_queue() -> None:
    global _crop_workers
    while True:
        with _crop_guard:
            if not _crop_queue:
                _crop_workers -= 1
                return
            journey_event_id = _crop_queue.popleft()
        capture_journey_crop_sync(journey_event_id)


def _enqueue_journey_crop(journey_event_id: int) -> None:
    global _crop_workers
    with _crop_guard:
        if journey_event_id in _crop_queue:
            return
        _crop_queue.append(journey_event_id)
        if _crop_workers < _MAX_CROP_WORKERS:
            _crop_workers += 1
            threading.Thread(
                target=_process_crop_queue,
                daemon=True,
                name="journey-snapshot-worker",
            ).start()


def capture_and_attach_snapshot_sync(
    journey_event_id: int,
    detection_event_id: int,
    camera_id: int,
) -> str:
    """Capture a full-frame journey snapshot for this event."""
    del detection_event_id, camera_id
    return capture_journey_crop_sync(journey_event_id)


def schedule_journey_snapshot(
    journey_event_id: int,
    detection_event_id: int | None,
    camera_id: int | None,
) -> None:
    """Queue a snapshot capture after the DB transaction commits."""
    if not camera_id:
        return

    def _on_commit() -> None:
        _enqueue_journey_crop(journey_event_id)
        if detection_event_id:
            try:
                from cameras.clip_capture import schedule_detection_clip

                schedule_detection_clip(camera_id, detection_event_id)
            except Exception:
                logger.debug("Detection clip queue skipped for det %s", detection_event_id)

    transaction.on_commit(_on_commit)


def capture_missing_for_person(
    person,
    *,
    since=None,
    limit: int = 20,
    timeout: float = 60.0,
) -> int:
    """Capture snapshots for journey events that still have no image."""
    from concurrent.futures import ThreadPoolExecutor, as_completed

    from .models import JourneyEvent

    qs = JourneyEvent.objects.filter(
        journey_person=person,
        camera__isnull=False,
        snapshot_path="",
    )
    if since is not None:
        qs = qs.filter(created_at__gte=since)
    jobs = list(qs.order_by("-created_at").values_list("id", flat=True)[:limit])
    if not jobs:
        return 0

    done = 0
    with ThreadPoolExecutor(max_workers=2) as pool:
        futures = [pool.submit(capture_journey_crop_sync, ev_id) for ev_id in jobs]
        try:
            for fut in as_completed(futures, timeout=timeout):
                try:
                    if fut.result():
                        done += 1
                except Exception:
                    logger.exception("Parallel journey snapshot failed")
        except TimeoutError:
            logger.warning("Journey snapshot batch timed out after %ss", timeout)
    return done


def capture_all_missing_events(*, limit: int = 100) -> int:
    """Capture snapshots for any journey events missing images."""
    from .models import JourneyEvent

    jobs = list(
        JourneyEvent.objects.filter(
            camera__isnull=False,
            snapshot_path="",
        )
        .order_by("-created_at")
        .values_list("id", flat=True)[:limit]
    )
    done = 0
    for ev_id in jobs:
        if capture_journey_crop_sync(ev_id):
            done += 1
    return done
