"""Enroll staff profile photos into DB embeddings and push them to the ML service."""

from __future__ import annotations

import logging
from pathlib import Path
from typing import Any

from django.core.files.base import ContentFile

from users.models import Staff, StaffFaceEmbedding

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
    if not staff.profile_image:
        return ""
    return str(staff.profile_image.name or "").strip()


def staff_needs_face_enrollment(staff: Staff) -> bool:
    """True when staff has a photo but no up-to-date active embedding."""
    image_key = staff_profile_image_key(staff)
    if not image_key:
        return False
    latest = (
        StaffFaceEmbedding.objects.filter(staff=staff, is_active=True, is_primary=True)
        .order_by("-updated_at")
        .first()
    )
    if latest is None:
        return True
    return (latest.source_profile_image or "") != image_key


def collect_db_face_embeddings() -> list[dict[str, Any]]:
    return [
        {"identity": row.identity_label, "embedding": row.embedding}
        for row in StaffFaceEmbedding.objects.filter(is_active=True).only(
            "identity_label", "embedding"
        )
    ]


def push_face_embeddings_to_ml() -> dict[str, Any] | None:
    if not ml_service_enabled():
        return None
    return ml_reload_faces(embeddings=collect_db_face_embeddings())


def refresh_staff_identity_labels(staff: Staff) -> int:
    identity = staff_identity_label(staff)
    if not identity:
        return 0
    return StaffFaceEmbedding.objects.filter(staff=staff, is_active=True).update(
        identity_label=identity
    )


def enroll_staff_face(staff: Staff, *, push_ml: bool = True, force: bool = False) -> StaffFaceEmbedding | None:
    """Extract SFace embedding from staff.profile_image and store in StaffFaceEmbedding."""
    image_key = staff_profile_image_key(staff)
    if not image_key:
        return None
    if not force and not staff_needs_face_enrollment(staff):
        return (
            StaffFaceEmbedding.objects.filter(staff=staff, is_active=True, is_primary=True)
            .order_by("-updated_at")
            .first()
        )
    if not ml_service_enabled():
        logger.warning("ML_SERVICE_URL not set — cannot enroll face for staff %s", staff.pk)
        return None

    try:
        with staff.profile_image.open("rb") as fh:
            image_bytes = fh.read()
    except (ValueError, OSError) as exc:
        logger.warning("Could not read profile image for staff %s: %s", staff.pk, exc)
        return None

    filename = Path(staff.profile_image.name).name or "face.jpg"
    try:
        result = ml_extract_face_embedding(image_bytes, filename=filename)
    except MLServiceError as exc:
        logger.error(
            "Face embedding failed for staff %s (%s): %s",
            staff.pk,
            staff.full_name,
            exc,
        )
        return None

    embedding = result.get("embedding") or []
    if not embedding:
        logger.warning("Empty embedding for staff %s (%s)", staff.pk, staff.full_name)
        return None

    identity = staff_identity_label(staff)
    StaffFaceEmbedding.objects.filter(staff=staff, is_primary=True).update(
        is_primary=False,
        is_active=False,
    )

    ext = Path(filename).suffix or ".jpg"
    safe_identity = "".join(c if c.isalnum() or c in "._-" else "_" for c in identity)
    face_filename = f"staff_{staff.id}_{safe_identity}{ext}"

    emb = StaffFaceEmbedding(
        staff=staff,
        embedding=embedding,
        embedding_dim=len(embedding),
        embedding_model=result.get("model") or StaffFaceEmbedding.EMBEDDING_MODEL_SFACE,
        identity_label=identity,
        is_primary=True,
        is_active=True,
        source_profile_image=image_key,
    )
    emb.image.save(face_filename, ContentFile(image_bytes), save=False)
    emb.save()

    logger.info(
        "Enrolled face for staff %s (%s) as %r dim=%s",
        staff.pk,
        staff.full_name,
        identity,
        len(embedding),
    )

    if push_ml:
        try:
            push_face_embeddings_to_ml()
        except MLServiceError as exc:
            logger.warning("Could not push face embeddings to ML: %s", exc)

    return emb


def enroll_missing_staff_faces(*, push_ml: bool = True) -> tuple[int, int]:
    """Enroll staff with photos that lack a current embedding. Returns (enrolled, skipped)."""
    enrolled = 0
    skipped = 0
    for staff in Staff.objects.select_related("user").iterator():
        if not staff_needs_face_enrollment(staff):
            skipped += 1
            continue
        if enroll_staff_face(staff, push_ml=False):
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
    """Enroll every staff member with a profile photo. Returns (enrolled, skipped)."""
    enrolled = 0
    skipped = 0
    for staff in Staff.objects.select_related("user").iterator():
        if not staff_profile_image_key(staff):
            skipped += 1
            continue
        if not force and not staff_needs_face_enrollment(staff):
            skipped += 1
            continue
        if enroll_staff_face(staff, push_ml=False, force=force):
            enrolled += 1
        else:
            skipped += 1

    if push_ml and enrolled:
        try:
            push_face_embeddings_to_ml()
        except MLServiceError as exc:
            logger.warning("Could not push face embeddings to ML: %s", exc)

    return enrolled, skipped


def sync_staff_face_after_save(staff: Staff, *, image_changed: bool) -> StaffFaceEmbedding | None:
    """Called after staff create/update when profile_image may have changed."""
    if not staff_profile_image_key(staff):
        return None
    if not image_changed and not staff_needs_face_enrollment(staff):
        return None
    return enroll_staff_face(staff, push_ml=True)


def sync_staff_identity_after_user_link(staff: Staff) -> None:
    """Refresh identity labels and reload ML after linking/creating a user."""
    if staff_profile_image_key(staff):
        enroll_staff_face(staff, push_ml=False, force=staff_needs_face_enrollment(staff))
    elif StaffFaceEmbedding.objects.filter(staff=staff, is_active=True).exists():
        refresh_staff_identity_labels(staff)
    try:
        push_face_embeddings_to_ml()
    except MLServiceError as exc:
        logger.warning("Could not push face embeddings to ML: %s", exc)
