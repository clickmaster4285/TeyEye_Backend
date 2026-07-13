"""Person matching engine — face + appearance + travel-time scoring."""

from __future__ import annotations

import math
from dataclasses import dataclass
from datetime import timedelta
from typing import Any

from django.conf import settings
from django.db.models import Q
from django.utils import timezone

from .models import JourneyPerson, PersonStatus, PersonType


def _env_float(key: str, default: float) -> float:
    try:
        return float(getattr(settings, key, default))
    except (TypeError, ValueError):
        return default


def _env_int(key: str, default: int) -> int:
    try:
        return int(getattr(settings, key, default))
    except (TypeError, ValueError):
        return default


FACE_MATCH_THRESHOLD = _env_float("JOURNEY_FACE_MATCH_THRESHOLD", 0.72)
REID_MATCH_THRESHOLD = _env_float("JOURNEY_REID_MATCH_THRESHOLD", 0.68)
COMBINED_MATCH_THRESHOLD = _env_float("JOURNEY_COMBINED_MATCH_THRESHOLD", 0.75)
MAX_TRAVEL_SECONDS = _env_int("JOURNEY_MAX_TRAVEL_SECONDS", 120)
RECENT_WINDOW_SECONDS = _env_int("JOURNEY_RECENT_WINDOW_SECONDS", 600)


def cosine_similarity(a: list[float] | None, b: list[float] | None) -> float:
    if not a or not b:
        return 0.0
    n = min(len(a), len(b))
    if n == 0:
        return 0.0
    dot = sum(float(a[i]) * float(b[i]) for i in range(n))
    na = math.sqrt(sum(float(a[i]) ** 2 for i in range(n)))
    nb = math.sqrt(sum(float(b[i]) ** 2 for i in range(n)))
    if na <= 0 or nb <= 0:
        return 0.0
    return max(0.0, min(1.0, dot / (na * nb)))


def _travel_time_valid(
    *,
    from_camera_id: int | None,
    to_camera_id: int | None,
    seconds_elapsed: float,
) -> bool:
    if from_camera_id is None or to_camera_id is None:
        return True
    if from_camera_id == to_camera_id:
        return True
    return 0 <= seconds_elapsed <= MAX_TRAVEL_SECONDS


def _connected_cameras(from_camera_id: int | None, to_camera_id: int | None) -> bool:
    if from_camera_id is None or to_camera_id is None:
        return True
    if from_camera_id == to_camera_id:
        return True
    try:
        from cameras.models import Camera

        c1 = Camera.objects.filter(pk=from_camera_id).values("location", "zone").first()
        c2 = Camera.objects.filter(pk=to_camera_id).values("location", "zone").first()
        if not c1 or not c2:
            return True
        if c1["location"] and c1["location"] == c2["location"]:
            return True
        if c1["zone"] and c2["zone"] and c1["zone"] == c2["zone"]:
            return True
    except Exception:
        return True
    return True


@dataclass
class MatchCandidate:
    person: JourneyPerson
    face_score: float
    reid_score: float
    travel_score: float
    combined_score: float


def score_candidate(
    person: JourneyPerson,
    *,
    face_embedding: list[float] | None,
    reid_embedding: list[float] | None,
    camera_id: int | None,
    now,
) -> MatchCandidate | None:
    face_score = cosine_similarity(face_embedding, person.face_embedding or [])
    reid_score = cosine_similarity(reid_embedding, person.reid_embedding or [])

    travel_score = 0.0
    if person.latest_seen_at and person.latest_camera_id:
        elapsed = (now - person.latest_seen_at).total_seconds()
        if _travel_time_valid(
            from_camera_id=person.latest_camera_id,
            to_camera_id=camera_id,
            seconds_elapsed=elapsed,
        ) and _connected_cameras(person.latest_camera_id, camera_id):
            travel_score = max(0.0, 1.0 - (elapsed / max(1, MAX_TRAVEL_SECONDS)))
        else:
            travel_score = 0.0

    has_face = bool(face_embedding and person.face_embedding)
    has_reid = bool(reid_embedding and person.reid_embedding)

    if has_face and has_reid:
        combined = face_score * 0.5 + reid_score * 0.3 + travel_score * 0.2
    elif has_face:
        combined = face_score * 0.7 + travel_score * 0.3
    elif has_reid:
        combined = reid_score * 0.7 + travel_score * 0.3
    else:
        combined = travel_score

    return MatchCandidate(
        person=person,
        face_score=face_score,
        reid_score=reid_score,
        travel_score=travel_score,
        combined_score=combined,
    )


def find_best_match(
    *,
    face_embedding: list[float] | None,
    reid_embedding: list[float] | None,
    camera_id: int | None,
    person_type_hint: str | None = None,
    staff_id: int | None = None,
    visitor_id: int | None = None,
) -> MatchCandidate | None:
    now = timezone.now()
    since = now - timedelta(seconds=RECENT_WINDOW_SECONDS)

    qs = JourneyPerson.objects.filter(
        status=PersonStatus.ACTIVE,
        latest_seen_at__gte=since,
    ).select_related("staff", "visitor", "latest_camera")

    if staff_id:
        qs = qs.filter(Q(staff_id=staff_id) | Q(person_type=PersonType.STAFF))
    elif visitor_id:
        qs = qs.filter(Q(visitor_id=visitor_id) | Q(person_type=PersonType.VISITOR))
    elif person_type_hint:
        qs = qs.filter(person_type=person_type_hint)

    candidates: list[MatchCandidate] = []
    for person in qs[:200]:
        scored = score_candidate(
            person,
            face_embedding=face_embedding,
            reid_embedding=reid_embedding,
            camera_id=camera_id,
            now=now,
        )
        if scored is None:
            continue
        if scored.combined_score >= COMBINED_MATCH_THRESHOLD:
            candidates.append(scored)
        elif face_embedding and scored.face_score >= FACE_MATCH_THRESHOLD:
            candidates.append(scored)
        elif reid_embedding and scored.reid_score >= REID_MATCH_THRESHOLD:
            candidates.append(scored)

    if not candidates:
        return None
    best = max(candidates, key=lambda c: c.combined_score)
    # Without face/ReID, travel-time alone must not merge distinct unknown persons.
    if not face_embedding and not reid_embedding:
        if best.face_score < 0.01 and best.reid_score < 0.01:
            return None
    return best


def resolve_staff_from_face_label(label: str) -> tuple[int | None, str]:
    from users.models import Staff
    from django.db.models import Q

    lbl = (label or "").strip()
    if not lbl or lbl.lower() in {"unknown", "person", "face", ""}:
        return None, ""

    staff = (
        Staff.objects.filter(
            Q(face_identity_label__iexact=lbl)
            | Q(full_name__iexact=lbl)
            | Q(user__username__iexact=lbl)
        )
        .select_related("user")
        .first()
    )
    if staff is None:
        return None, lbl
    return staff.pk, (staff.full_name or lbl).strip()
