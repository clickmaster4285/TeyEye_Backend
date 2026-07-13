"""Resolve journey event snapshot URLs from stored path or linked DetectionEvent clip."""

from __future__ import annotations

from cameras.models import DetectionEvent

from .models import JourneyEvent


def detection_clip_url(detection_event_id: int | None) -> str:
    if not detection_event_id:
        return ""
    det = DetectionEvent.objects.filter(pk=detection_event_id).only("clip").first()
    if det is None or not det.clip:
        return ""
    return det.clip.url or ""


def journey_event_snapshot_url(event: JourneyEvent) -> str:
    """Only return images tied to this specific journey/detection event."""
    path = (event.snapshot_path or "").strip()
    if path:
        return path
    return detection_clip_url(event.detection_event_id)


def journey_person_latest_snapshot_url(person) -> str:
    for event in (
        JourneyEvent.objects.filter(journey_person=person)
        .exclude(snapshot_path="")
        .order_by("-created_at")
        .only("snapshot_path", "detection_event_id")[:20]
    ):
        url = journey_event_snapshot_url(event)
        if url:
            return url
    event = (
        JourneyEvent.objects.filter(journey_person=person, detection_event_id__isnull=False)
        .order_by("-created_at")
        .only("snapshot_path", "detection_event_id")
        .first()
    )
    if event is None:
        return ""
    return journey_event_snapshot_url(event)


def build_detection_clip_map(events: list[JourneyEvent]) -> dict[int, str]:
    ids = [e.detection_event_id for e in events if e.detection_event_id]
    if not ids:
        return {}
    out: dict[int, str] = {}
    for row in DetectionEvent.objects.filter(pk__in=ids).only("clip"):
        if row.clip:
            out[row.pk] = row.clip.url or ""
    return out


def serializer_context_for_events(events: list[JourneyEvent], person=None) -> dict:
    del person
    return {"detection_clip_map": build_detection_clip_map(events)}


def backfill_snapshot_paths_for_person(person) -> int:
    """Copy clip URL only when journey event has no snapshot and clip matches that detection."""
    rows = JourneyEvent.objects.filter(
        journey_person=person,
        detection_event_id__isnull=False,
        snapshot_path="",
    ).only("pk", "detection_event_id")
    if not rows:
        return 0

    clip_map = build_detection_clip_map(
        [JourneyEvent(detection_event_id=r.detection_event_id) for r in rows if r.detection_event_id]
    )
    updated = 0
    for row in rows:
        url = clip_map.get(row.detection_event_id or 0, "")
        if url:
            JourneyEvent.objects.filter(pk=row.pk).update(snapshot_path=url)
            updated += 1
    return updated


def person_camera_captures(person, *, since=None) -> list[dict]:
    """Latest sighting image per camera — only event-specific snapshots."""
    event_qs = JourneyEvent.objects.filter(journey_person=person, camera__isnull=False)
    if since is not None:
        event_qs = event_qs.filter(created_at__gte=since)

    camera_ids = sorted({cid for cid in event_qs.values_list("camera_id", flat=True) if cid})
    if not camera_ids:
        return []

    scoped_events = JourneyEvent.objects.filter(journey_person=person, camera__isnull=False)
    if since is not None:
        scoped_events = scoped_events.filter(created_at__gte=since)

    clip_map = build_detection_clip_map(
        list(scoped_events.filter(detection_event_id__isnull=False).only("detection_event_id"))
    )

    results: list[dict] = []
    for camera_id in camera_ids:
        events = scoped_events.filter(camera_id=camera_id).select_related("camera").order_by(
            "-created_at"
        )
        snapshot_url = ""
        chosen = None
        for ev in events:
            url = journey_event_snapshot_url(ev)
            if not url and ev.detection_event_id:
                url = clip_map.get(ev.detection_event_id, "")
            if url:
                snapshot_url = url
                chosen = ev
                break
        if chosen is None:
            chosen = events.first()
        if chosen is None:
            continue

        results.append(
            {
                "camera_id": camera_id,
                "camera_name": chosen.camera.name if chosen.camera else "",
                "camera_code": chosen.camera.code if chosen.camera else "",
                "zone": chosen.zone or (chosen.camera.zone if chosen.camera else ""),
                "snapshot_url": snapshot_url,
                "event_id": chosen.pk,
                "detection_event_id": chosen.detection_event_id,
                "event_type": chosen.event_type,
                "title": chosen.title,
                "confidence": chosen.confidence,
                "captured_at": chosen.created_at,
            }
        )

    results.sort(key=lambda row: row.get("camera_name") or "")
    return results
