"""Enroll all staff photos into face_embeddings on Staff and push vectors to ML."""

from __future__ import annotations

import logging
from pathlib import Path
from typing import Any

from django.core.files.storage import default_storage

from users.models import Staff
from users.staff_photos import staff_photo_paths

from .client import (
    MLServiceError,
    ml_extract_face_embedding,
    ml_reload_faces,
    ml_service_enabled,
)

logger = logging.getLogger(__name__)


def staff_identity_label(staff: Staff) -> str:
    name = (staff.full_name or "").strip()
    if name:
        return name
    user = getattr(staff, "user", None)
    if user and user.username:
        return user.username.strip()
    return ""


def staff_profile_image_key(staff: Staff) -> str:
    paths = staff_photo_paths(staff)
    return paths[0] if paths else ""


def _stored_embedding_map(staff: Staff) -> dict[str, dict[str, Any]]:
    out: dict[str, dict[str, Any]] = {}
    raw = getattr(staff, "face_embeddings", None)
    if not isinstance(raw, list):
        return out
    for item in raw:
        if not isinstance(item, dict):
            continue
        key = str(item.get("image_key") or "").strip()
        emb = item.get("embedding")
        if key and isinstance(emb, list) and emb:
            out[key] = item
    return out


def staff_has_face_embedding(staff: Staff) -> bool:
    if _stored_embedding_map(staff):
        return True
    emb = staff.face_embedding
    return isinstance(emb, list) and len(emb) > 0


def staff_needs_face_enrollment(staff: Staff) -> bool:
    """True when any staff photo lacks a stored embedding."""
    paths = staff_photo_paths(staff)
    if not paths:
        return False
    stored = _stored_embedding_map(staff)
    if not stored and staff_has_face_embedding(staff):
        legacy_key = (staff.face_embedding_profile_key or "").strip()
        if legacy_key in paths:
            return len(paths) > 1
        return True
    return any(path not in stored for path in paths)


def _read_photo_bytes(path: str) -> bytes | None:
    try:
        with default_storage.open(path, "rb") as fh:
            return fh.read()
    except (ValueError, OSError) as exc:
        logger.warning("Could not read staff photo %s: %s", path, exc)
        return None


def _extract_embedding_for_path(path: str) -> dict[str, Any] | None:
    image_bytes = _read_photo_bytes(path)
    if not image_bytes:
        return None
    filename = Path(path).name or "face.jpg"
    try:
        result = ml_extract_face_embedding(image_bytes, filename=filename)
    except MLServiceError as exc:
        logger.error("Face embedding failed for %s: %s", path, exc)
        return None
    embedding = result.get("embedding") or []
    if not embedding:
        return None
    return {
        "image_key": path,
        "embedding": embedding,
        "dim": len(embedding),
        "model": result.get("model") or Staff.FACE_EMBEDDING_MODEL_SFACE,
    }


def _sync_primary_embedding_fields(staff: Staff, entries: list[dict[str, Any]], paths: list[str]) -> None:
    first = entries[0] if entries else None
    Staff.objects.filter(pk=staff.pk).update(
        face_embeddings=entries,
        face_embedding=(first or {}).get("embedding"),
        face_embedding_dim=int((first or {}).get("dim") or 0),
        face_embedding_model=str((first or {}).get("model") or ""),
        face_identity_label=staff_identity_label(staff),
        face_embedding_profile_key=",".join(paths),
    )


def collect_db_face_embeddings() -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for staff in Staff.objects.iterator():
        identity = (staff.face_identity_label or staff_identity_label(staff)).strip()
        if not identity:
            continue

        entries = getattr(staff, "face_embeddings", None)
        if isinstance(entries, list) and entries:
            for item in entries:
                if not isinstance(item, dict):
                    continue
                emb = item.get("embedding")
                if isinstance(emb, list) and emb:
                    rows.append({"identity": identity, "embedding": emb})
            continue

        emb = staff.face_embedding
        if isinstance(emb, list) and emb:
            rows.append({"identity": identity, "embedding": emb})
    return rows


def push_face_embeddings_to_ml() -> dict[str, Any] | None:
    if not ml_service_enabled():
        return None
    return ml_reload_faces(embeddings=collect_db_face_embeddings())


def refresh_staff_identity_label(staff: Staff) -> bool:
    identity = staff_identity_label(staff)
    if not identity or not staff_has_face_embedding(staff):
        return False
    if (staff.face_identity_label or "").strip() == identity:
        return False
    Staff.objects.filter(pk=staff.pk).update(face_identity_label=identity)
    return True


def enroll_staff_faces(staff: Staff, *, push_ml: bool = True, force: bool = False) -> Staff | None:
    """Extract SFace embeddings for every photo in staff.staff_photos."""
    paths = staff_photo_paths(staff)
    if not paths:
        return None
    if not force and not staff_needs_face_enrollment(staff):
        return staff
    if not ml_service_enabled():
        logger.warning("ML_SERVICE_URL not set — cannot enroll faces for staff %s", staff.pk)
        return None

    stored = _stored_embedding_map(staff)
    entries: list[dict[str, Any]] = []
    for path in paths:
        if not force and path in stored:
            entries.append(stored[path])
            continue
        extracted = _extract_embedding_for_path(path)
        if extracted:
            entries.append(extracted)
        elif path in stored and force:
            entries.append(stored[path])

    if not entries:
        logger.warning("No face embeddings produced for staff %s (%s)", staff.pk, staff.full_name)
        return None

    _sync_primary_embedding_fields(staff, entries, paths)

    logger.info(
        "Enrolled %s face(s) for staff %s (%s) as %r",
        len(entries),
        staff.pk,
        staff.full_name,
        staff_identity_label(staff),
    )

    if push_ml:
        try:
            push_face_embeddings_to_ml()
        except MLServiceError as exc:
            logger.warning("Could not push face embeddings to ML: %s", exc)

    return Staff.objects.filter(pk=staff.pk).first()


def enroll_staff_face(staff: Staff, *, push_ml: bool = True, force: bool = False) -> Staff | None:
    """Backward-compatible alias — enrolls all staff photos."""
    return enroll_staff_faces(staff, push_ml=push_ml, force=force)


def enroll_missing_staff_faces(*, push_ml: bool = True) -> tuple[int, int]:
    enrolled = 0
    skipped = 0
    for staff in Staff.objects.select_related("user").iterator():
        if not staff_needs_face_enrollment(staff):
            skipped += 1
            continue
        if enroll_staff_faces(staff, push_ml=False):
            enrolled += 1
        else:
            skipped += 1

    if push_ml and enrolled:
        try:
            push_face_embeddings_to_ml()
        except MLServiceError as exc:
            logger.warning("Could not push face embeddings to ML: %s", exc)

    return enrolled, skipped


def enroll_all_staff_faces(*, push_ml: bool = True, force: bool = False) -> tuple[int, int]:
    enrolled = 0
    skipped = 0
    for staff in Staff.objects.select_related("user").iterator():
        if not staff_photo_paths(staff):
            skipped += 1
            continue
        if not force and not staff_needs_face_enrollment(staff):
            skipped += 1
            continue
        if enroll_staff_faces(staff, push_ml=False, force=force):
            enrolled += 1
        else:
            skipped += 1

    if push_ml and enrolled:
        try:
            push_face_embeddings_to_ml()
        except MLServiceError as exc:
            logger.warning("Could not push face embeddings to ML: %s", exc)

    return enrolled, skipped


def sync_staff_faces_after_save(staff: Staff, *, force: bool = False) -> Staff | None:
    """Called after staff create/update when photos may have changed."""
    if not staff_photo_paths(staff):
        return None
    if not force and not staff_needs_face_enrollment(staff):
        return None
    return enroll_staff_faces(staff, push_ml=True, force=force)


def sync_staff_face_after_save(staff: Staff, *, image_changed: bool) -> Staff | None:
    """Backward-compatible hook used by signals."""
    if not image_changed and not staff_needs_face_enrollment(staff):
        return None
    return sync_staff_faces_after_save(staff, force=image_changed)


def sync_staff_identity_after_user_link(staff: Staff) -> None:
    if staff_photo_paths(staff):
        enroll_staff_faces(staff, push_ml=False, force=staff_needs_face_enrollment(staff))
    elif staff_has_face_embedding(staff):
        if refresh_staff_identity_label(staff):
            try:
                push_face_embeddings_to_ml()
            except MLServiceError as exc:
                logger.warning("Could not push face embeddings to ML: %s", exc)
            return
    try:
        push_face_embeddings_to_ml()
    except MLServiceError as exc:
        logger.warning("Could not push face embeddings to ML: %s", exc)
