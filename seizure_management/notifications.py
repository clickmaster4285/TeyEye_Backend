"""Note sheet, assessment & recovery memo approval roles and in-app notifications."""

from __future__ import annotations

from django.contrib.auth import get_user_model

from .models import (
    AssessmentNotification,
    DetentionAssessment,
    NoteSheet,
    NoteSheetNotification,
    RecoveryMemo,
    RecoveryNotification,
)

User = get_user_model()

# Officials who receive approval requests / can approve or reject.
NOTE_SHEET_APPROVER_ROLES = frozenset(
    {
        "ADMIN",  # Super Admin
        "LOCATION_ADMIN",
        "DEPUTY_COLLECTOR",
        "ASSISTANT_COLLECTOR",
    }
)

# Same approver set for assessments and recovery memos (note sheet flow unchanged).
ASSESSMENT_APPROVER_ROLES = NOTE_SHEET_APPROVER_ROLES
RECOVERY_APPROVER_ROLES = NOTE_SHEET_APPROVER_ROLES

NOTE_SHEET_FORWARD_TO_LABEL = (
    "Assistant Collector, Deputy Collector, Location Admin, Super Admin"
)

ASSESSMENT_FORWARD_TO_LABEL = NOTE_SHEET_FORWARD_TO_LABEL
RECOVERY_FORWARD_TO_LABEL = NOTE_SHEET_FORWARD_TO_LABEL

LOCATION_SCOPED_APPROVER_ROLES = frozenset(
    {
        "LOCATION_ADMIN",
        "DEPUTY_COLLECTOR",
        "ASSISTANT_COLLECTOR",
    }
)


def _normalize_role(role: str | None) -> str:
    return (role or "").strip().upper()


def note_sheet_submitter_location(obj: NoteSheet) -> str:
    """Location code of the officer who prepared/created the note sheet."""
    username = (obj.created_by or "").strip()
    if username:
        loc = (
            User.objects.filter(username__iexact=username, is_deleted=False)
            .values_list("location", flat=True)
            .first()
        )
        if loc:
            return (loc or "").strip().upper()
    # Fallback: match office label to a location choice
    office = (obj.office or "").strip().upper()
    if office:
        for code, label in User.LOCATION_CHOICES:
            if code.upper() == office or label.upper() == office:
                return code.upper()
            if office in label.upper() or label.upper() in office:
                return code.upper()
    return ""


def assessment_submitter_location(obj: DetentionAssessment) -> str:
    username = (obj.created_by or "").strip()
    if not username:
        return ""
    loc = (
        User.objects.filter(username__iexact=username, is_deleted=False)
        .values_list("location", flat=True)
        .first()
    )
    return (loc or "").strip().upper() if loc else ""


def recovery_submitter_location(obj: RecoveryMemo) -> str:
    username = (obj.created_by or obj.recovery_officer or "").strip()
    if not username:
        return ""
    loc = (
        User.objects.filter(username__iexact=username, is_deleted=False)
        .values_list("location", flat=True)
        .first()
    )
    return (loc or "").strip().upper() if loc else ""


def user_can_approve_note_sheet(user, obj: NoteSheet | None = None) -> bool:
    """True if user is Super Admin / Location Admin / Deputy or Assistant Collector."""
    if not user or not getattr(user, "is_authenticated", False):
        return False
    role = _normalize_role(getattr(user, "role", None))
    if role not in NOTE_SHEET_APPROVER_ROLES:
        return False
    if role == "ADMIN":
        return True
    if obj is None:
        return True
    submitter_loc = note_sheet_submitter_location(obj)
    user_loc = (getattr(user, "location", None) or "").strip().upper()
    if not submitter_loc:
        # Unknown location — still allow location-scoped officials
        return True
    return user_loc == submitter_loc


def user_can_approve_assessment(user, obj: DetentionAssessment | None = None) -> bool:
    if not user or not getattr(user, "is_authenticated", False):
        return False
    role = _normalize_role(getattr(user, "role", None))
    if role not in ASSESSMENT_APPROVER_ROLES:
        return False
    if role == "ADMIN":
        return True
    if obj is None:
        return True
    submitter_loc = assessment_submitter_location(obj)
    user_loc = (getattr(user, "location", None) or "").strip().upper()
    if not submitter_loc:
        return True
    return user_loc == submitter_loc


def user_can_approve_recovery(user, obj: RecoveryMemo | None = None) -> bool:
    if not user or not getattr(user, "is_authenticated", False):
        return False
    role = _normalize_role(getattr(user, "role", None))
    if role not in RECOVERY_APPROVER_ROLES:
        return False
    if role == "ADMIN":
        return True
    if obj is None:
        return True
    submitter_loc = recovery_submitter_location(obj)
    user_loc = (getattr(user, "location", None) or "").strip().upper()
    if not submitter_loc:
        return True
    return user_loc == submitter_loc


def recipients_for_note_sheet_approval(obj: NoteSheet, exclude_user_id: int | None = None):
    """Active users who should be notified about a submitted note sheet."""
    submitter_loc = note_sheet_submitter_location(obj)
    qs = User.objects.filter(
        is_deleted=False,
        is_active=True,
        role__in=list(NOTE_SHEET_APPROVER_ROLES),
    )
    if exclude_user_id:
        qs = qs.exclude(pk=exclude_user_id)

    recipients = []
    for u in qs:
        role = _normalize_role(u.role)
        if role == "ADMIN":
            recipients.append(u)
            continue
        if role in LOCATION_SCOPED_APPROVER_ROLES:
            if not submitter_loc or (u.location or "").strip().upper() == submitter_loc:
                recipients.append(u)
    return recipients


def recipients_for_assessment_approval(obj: DetentionAssessment, exclude_user_id: int | None = None):
    submitter_loc = assessment_submitter_location(obj)
    qs = User.objects.filter(
        is_deleted=False,
        is_active=True,
        role__in=list(ASSESSMENT_APPROVER_ROLES),
    )
    if exclude_user_id:
        qs = qs.exclude(pk=exclude_user_id)

    recipients = []
    for u in qs:
        role = _normalize_role(u.role)
        if role == "ADMIN":
            recipients.append(u)
            continue
        if role in LOCATION_SCOPED_APPROVER_ROLES:
            if not submitter_loc or (u.location or "").strip().upper() == submitter_loc:
                recipients.append(u)
    return recipients


def recipients_for_recovery_approval(obj: RecoveryMemo, exclude_user_id: int | None = None):
    submitter_loc = recovery_submitter_location(obj)
    qs = User.objects.filter(
        is_deleted=False,
        is_active=True,
        role__in=list(RECOVERY_APPROVER_ROLES),
    )
    if exclude_user_id:
        qs = qs.exclude(pk=exclude_user_id)

    recipients = []
    for u in qs:
        role = _normalize_role(u.role)
        if role == "ADMIN":
            recipients.append(u)
            continue
        if role in LOCATION_SCOPED_APPROVER_ROLES:
            if not submitter_loc or (u.location or "").strip().upper() == submitter_loc:
                recipients.append(u)
    return recipients


def notify_note_sheet_submitted(obj: NoteSheet, submitted_by_user_id: int | None = None) -> int:
    """Create unread notifications for all approver officials. Returns count created."""
    sheet_no = obj.note_sheet_no or obj.reference_number or str(obj.pk)
    prepared = (obj.prepared_by or obj.created_by or "an officer").strip()
    title = f"Note sheet pending approval: {sheet_no}"
    message = (
        f"{prepared} submitted note sheet {sheet_no} for approval. "
        f"Subject: {(obj.subject or '—').strip()}"
    )

    # Avoid duplicate unread notifications for the same sheet + recipient
    NoteSheetNotification.objects.filter(
        note_sheet=obj,
        is_read=False,
    ).delete()

    created = 0
    for user in recipients_for_note_sheet_approval(obj, exclude_user_id=submitted_by_user_id):
        NoteSheetNotification.objects.create(
            recipient_user_id=user.id,
            note_sheet=obj,
            title=title,
            message=message,
        )
        created += 1
    return created


def mark_note_sheet_notifications_resolved(obj: NoteSheet) -> None:
    """Mark related notifications as read after approve/reject."""
    NoteSheetNotification.objects.filter(note_sheet=obj, is_read=False).update(is_read=True)


def notify_assessment_submitted(obj: DetentionAssessment, submitted_by_user_id: int | None = None) -> int:
    memo = obj.detention_memo
    case_no = (memo.case_no if memo else "") or str(obj.pk)
    officer = (obj.examining_officer or obj.created_by or "an officer").strip()
    title = f"Assessment pending approval: {case_no}"
    message = (
        f"{officer} submitted detention assessment for case {case_no} for approval. "
        f"Documents: {obj.document_relevance}."
    )

    AssessmentNotification.objects.filter(assessment=obj, is_read=False).delete()

    created = 0
    for user in recipients_for_assessment_approval(obj, exclude_user_id=submitted_by_user_id):
        AssessmentNotification.objects.create(
            recipient_user_id=user.id,
            assessment=obj,
            title=title,
            message=message,
        )
        created += 1
    return created


def mark_assessment_notifications_resolved(obj: DetentionAssessment) -> None:
    AssessmentNotification.objects.filter(assessment=obj, is_read=False).update(is_read=True)


def notify_recovery_submitted(obj: RecoveryMemo, submitted_by_user_id: int | None = None) -> int:
    memo = obj.detention_memo
    case_no = (memo.case_no if memo else "") or str(obj.pk)
    officer = (obj.recovery_officer or obj.created_by or "an officer").strip()
    title = f"Recovery memo pending approval: {case_no}"
    message = (
        f"{officer} submitted recovery memo for case {case_no} for approval. "
        f"Category: {obj.category}."
    )

    RecoveryNotification.objects.filter(recovery_memo=obj, is_read=False).delete()

    created = 0
    for user in recipients_for_recovery_approval(obj, exclude_user_id=submitted_by_user_id):
        RecoveryNotification.objects.create(
            recipient_user_id=user.id,
            recovery_memo=obj,
            title=title,
            message=message,
        )
        created += 1
    return created


def mark_recovery_notifications_resolved(obj: RecoveryMemo) -> None:
    RecoveryNotification.objects.filter(recovery_memo=obj, is_read=False).update(is_read=True)
