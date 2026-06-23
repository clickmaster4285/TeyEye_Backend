"""Mark HR attendance when registered staff are recognized (camera or kiosk)."""

from __future__ import annotations

import logging
import time
from typing import Literal

from django.conf import settings
from django.db.models import Q
from django.utils import timezone

from users.models import Attendance, Staff, User

logger = logging.getLogger(__name__)

AttendanceAction = Literal[
    "check_in",
    "check_out",
    "already_complete",
    "skipped_cooldown",
    "skipped_no_staff",
    "skipped_not_enrolled",
]

_GENERIC_LABELS = frozenset({"unknown", "person", "face", ""})

_recent_camera_marks: dict[str, float] = {}


def _camera_mark_cooldown() -> int:
    return max(30, int(getattr(settings, "ATTENDANCE_CAMERA_MARK_COOLDOWN_SECONDS", 120)))


def _min_checkout_seconds() -> int:
    hours = float(getattr(settings, "ATTENDANCE_MIN_CHECKOUT_HOURS", 4))
    return max(0, int(hours * 3600))


def _cooldown_key(*, user: User | None = None, staff: Staff | None = None) -> str | None:
    if user is not None:
        return f"user:{user.pk}"
    if staff is not None:
        return f"staff:{staff.pk}"
    return None


def _is_recognized_identity(identity: str) -> bool:
    lbl = (identity or "").strip()
    return bool(lbl) and lbl.lower() not in _GENERIC_LABELS


def resolve_staff_for_face_identity(identity: str) -> Staff | None:
    """Map ML identity label to a Staff row (full name, face label, or linked username)."""
    lbl = (identity or "").strip()
    if not _is_recognized_identity(lbl):
        return None

    return (
        Staff.objects.filter(
            Q(face_identity_label__iexact=lbl)
            | Q(full_name__iexact=lbl)
            | Q(user__username__iexact=lbl)
        )
        .select_related("user")
        .first()
    )


def resolve_user_for_face_identity(identity: str) -> User | None:
    """Map ML identity label to an active User when staff has a linked login."""
    staff = resolve_staff_for_face_identity(identity)
    if staff and staff.user_id:
        linked = staff.user
        if linked and not linked.is_deleted:
            return linked

    lbl = (identity or "").strip()
    if not _is_recognized_identity(lbl):
        return None

    user = User.objects.filter(username__iexact=lbl, is_deleted=False).first()
    return user


def staff_is_enrolled_for_attendance(staff: Staff | None) -> bool:
    if staff is None:
        return False
    from ml.face_sync import staff_has_face_embedding
    from users.staff_photos import staff_photo_paths

    if staff_has_face_embedding(staff):
        return True
    return bool(staff_photo_paths(staff))


def _touch_camera_cooldown(key: str) -> None:
    _recent_camera_marks[key] = time.monotonic()


def _camera_cooldown_active(key: str) -> bool:
    last = _recent_camera_marks.get(key, 0.0)
    return time.monotonic() - last < _camera_mark_cooldown()


def mark_attendance_for_staff(
    staff: Staff,
    *,
    source: str = "manual",
    allow_checkout: bool = True,
) -> tuple[AttendanceAction, Attendance | None]:
    """Check-in/out for enrolled staff (uses linked user row when present)."""
    if staff.user_id and staff.user and not staff.user.is_deleted:
        return mark_attendance_for_user(staff.user, source=source, allow_checkout=allow_checkout)

    now = timezone.now()
    today = timezone.localdate()
    key = _cooldown_key(staff=staff)

    if source == "camera" and key and _camera_cooldown_active(key):
        return "skipped_cooldown", None

    attendance, _ = Attendance.objects.get_or_create(staff=staff, date=today)

    if not attendance.check_in:
        attendance.check_in = now
        attendance.save(update_fields=["check_in"])
        if source == "camera" and key:
            _touch_camera_cooldown(key)
        logger.info("Attendance check-in: %s (%s)", staff.full_name, source)
        return "check_in", attendance

    if not allow_checkout or attendance.check_out:
        if source == "camera" and key:
            _touch_camera_cooldown(key)
        return "already_complete", attendance

    seconds_since = (now - attendance.check_in).total_seconds()
    min_checkout = _min_checkout_seconds()
    if source == "camera" and min_checkout > 0 and seconds_since < min_checkout:
        return "skipped_cooldown", attendance

    attendance.check_out = now
    attendance.save(update_fields=["check_out"])
    if source == "camera" and key:
        _touch_camera_cooldown(key)
    logger.info("Attendance check-out: %s (%s)", staff.full_name, source)
    return "check_out", attendance


def mark_attendance_for_user(
    user: User,
    *,
    source: str = "manual",
    allow_checkout: bool = True,
) -> tuple[AttendanceAction, Attendance | None]:
    """Check-in on first mark today; optional check-out with cooldown rules."""
    now = timezone.now()
    today = timezone.localdate()
    key = _cooldown_key(user=user)

    if source == "camera" and key and _camera_cooldown_active(key):
        return "skipped_cooldown", None

    attendance, _ = Attendance.objects.get_or_create(user=user, date=today)

    if not attendance.check_in:
        attendance.check_in = now
        attendance.save(update_fields=["check_in"])
        if source == "camera" and key:
            _touch_camera_cooldown(key)
        logger.info("Attendance check-in: %s (%s)", user.username, source)
        return "check_in", attendance

    if not allow_checkout or attendance.check_out:
        if source == "camera" and key:
            _touch_camera_cooldown(key)
        return "already_complete", attendance

    seconds_since = (now - attendance.check_in).total_seconds()
    min_checkout = _min_checkout_seconds()
    if source == "camera" and min_checkout > 0 and seconds_since < min_checkout:
        return "skipped_cooldown", attendance

    attendance.check_out = now
    attendance.save(update_fields=["check_out"])
    if source == "camera" and key:
        _touch_camera_cooldown(key)
    logger.info("Attendance check-out: %s (%s)", user.username, source)
    return "check_out", attendance


def _attendance_camera_purposes():
    from cameras.models import CameraPurpose

    purposes = {
        CameraPurpose.ATTENDANCE,
        CameraPurpose.FACE_RECOGNITION,
        CameraPurpose.SURVEILLANCE,
        CameraPurpose.ZONE_MONITORING,
    }
    if getattr(settings, "ATTENDANCE_MARK_ON_FACE_RECOGNITION_CAMERAS", True):
        purposes.add(CameraPurpose.FACE_RECOGNITION)
    return purposes


def _camera_allows_attendance(camera) -> bool:
    from cameras.models import CameraPurpose

    blocked = {
        CameraPurpose.ANPR,
        CameraPurpose.OBJECT_DETECTION,
        CameraPurpose.THERMAL,
    }
    if camera.purpose in blocked:
        return False
    if camera.purpose in _attendance_camera_purposes():
        return True
    return getattr(settings, "ATTENDANCE_MARK_ON_ALL_CAMERAS", False)


def try_mark_attendance_from_detection(
    camera,
    label: str,
    class_name: str,
    confidence: float,
) -> tuple[AttendanceAction | None, Attendance | None]:
    """Auto-mark attendance when a camera recognizes enrolled staff."""
    if not _camera_allows_attendance(camera):
        return None, None

    cls = (class_name or "").strip().lower()
    if cls not in ("person", "face"):
        return None, None

    if not _is_recognized_identity(label):
        return None, None

    staff = resolve_staff_for_face_identity(label)
    if not staff:
        logger.debug("Attendance skip: no staff for label %r on camera %s", label, camera.pk)
        return "skipped_no_staff", None

    if not staff_is_enrolled_for_attendance(staff):
        logger.debug("Attendance skip: staff %s not enrolled on camera %s", staff.pk, camera.pk)
        return "skipped_not_enrolled", None

    # Label is already a face-match result; YOLO box confidence is unrelated to identity.
    return mark_attendance_for_staff(staff, source="camera", allow_checkout=True)
