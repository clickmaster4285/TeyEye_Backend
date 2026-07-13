from __future__ import annotations

from django.shortcuts import get_object_or_404
from django.utils import timezone
from rest_framework import permissions, status
from rest_framework.response import Response
from rest_framework.views import APIView

from detentions.models import DetentionMemo

from .models import (
    AssessmentNotification,
    DetentionAssessment,
    NoteSheet,
    NoteSheetNotification,
    RecoveryMemo,
    RecoveryNotification,
    SeizureReport,
)
from .notifications import (
    NOTE_SHEET_FORWARD_TO_LABEL,
    RECOVERY_FORWARD_TO_LABEL,
    mark_assessment_notifications_resolved,
    mark_note_sheet_notifications_resolved,
    mark_recovery_notifications_resolved,
    notify_assessment_submitted,
    notify_note_sheet_submitted,
    notify_recovery_submitted,
    user_can_approve_assessment,
    user_can_approve_note_sheet,
    user_can_approve_recovery,
)
from .serializers import (
    AssessmentApprovalSerializer,
    AssessmentWriteSerializer,
    LinkDetentionSerializer,
    NoteSheetApprovalSerializer,
    NoteSheetWriteSerializer,
    RecoveryApprovalSerializer,
    RecoveryMemoWriteSerializer,
    SeizureReportWriteSerializer,
    apply_assessment,
    apply_note_sheet,
    apply_recovery,
    apply_seizure_report,
    assessment_to_dict,
    body_from_request,
    build_recovery_assessment_sheet,
    maybe_create_deposit_for_recovery,
    note_sheet_to_dict,
    recovery_memo_to_dict,
    save_assessment_uploads,
    save_note_sheet_goods_images,
    save_note_sheet_uploads,
    seizure_report_to_dict,
)


def _username(request) -> str:
    user = getattr(request, "user", None)
    if user and getattr(user, "is_authenticated", False):
        return user.get_username() or ""
    return ""


def _notification_to_dict(n: NoteSheetNotification) -> dict:
    sheet = n.note_sheet
    return {
        "id": str(n.id),
        "title": n.title,
        "message": n.message,
        "isRead": n.is_read,
        "createdAt": n.created_at.isoformat() if n.created_at else "",
        "noteSheetId": str(n.note_sheet_id),
        "noteSheetNo": (sheet.note_sheet_no or sheet.reference_number or "") if sheet else "",
        "assessmentId": "",
        "recoveryMemoId": "",
        "type": "note_sheet_approval",
        "hrefKind": "note_sheet",
    }


def _assessment_notification_to_dict(n: AssessmentNotification) -> dict:
    assessment = n.assessment
    memo = assessment.detention_memo if assessment else None
    return {
        "id": str(n.id),
        "title": n.title,
        "message": n.message,
        "isRead": n.is_read,
        "createdAt": n.created_at.isoformat() if n.created_at else "",
        "noteSheetId": "",
        "noteSheetNo": "",
        "assessmentId": str(n.assessment_id),
        "recoveryMemoId": "",
        "caseNo": (memo.case_no if memo else "") or "",
        "type": "assessment_approval",
        "hrefKind": "assessment",
    }


def _recovery_notification_to_dict(n: RecoveryNotification) -> dict:
    recovery = n.recovery_memo
    memo = recovery.detention_memo if recovery else None
    return {
        "id": str(n.id),
        "title": n.title,
        "message": n.message,
        "isRead": n.is_read,
        "createdAt": n.created_at.isoformat() if n.created_at else "",
        "noteSheetId": "",
        "noteSheetNo": "",
        "assessmentId": "",
        "recoveryMemoId": str(n.recovery_memo_id),
        "caseNo": (memo.case_no if memo else "") or "",
        "type": "recovery_approval",
        "hrefKind": "recovery",
    }


class NoteSheetListAPIView(APIView):
    permission_classes = [permissions.IsAuthenticated]

    def get(self, request):
        status_filter = (request.query_params.get("status") or "").strip()
        qs = NoteSheet.objects.prefetch_related("items__images", "attachments").all()
        if status_filter:
            qs = qs.filter(status=status_filter)
        available = request.query_params.get("available") == "1"
        if available:
            qs = qs.filter(status=NoteSheet.STATUS_APPROVED, detention_memo__isnull=True)
        return Response([note_sheet_to_dict(o, request) for o in qs])


class NoteSheetCreateAPIView(APIView):
    permission_classes = [permissions.IsAuthenticated]

    def post(self, request):
        try:
            body = body_from_request(request)
            ser = NoteSheetWriteSerializer(data=body)
            ser.is_valid(raise_exception=True)
            obj = NoteSheet()
            apply_note_sheet(obj, ser.validated_data, username=_username(request))
            save_note_sheet_uploads(request, obj)
            save_note_sheet_goods_images(request, obj, ser.validated_data.get("items"))
            obj = NoteSheet.objects.prefetch_related("items__images", "attachments").get(pk=obj.pk)
            return Response(note_sheet_to_dict(obj, request), status=status.HTTP_201_CREATED)
        except Exception as exc:
            # Surface actionable error for note-sheet create failures (validation already raises).
            from rest_framework.exceptions import ValidationError as DRFValidationError

            if isinstance(exc, DRFValidationError):
                raise
            return Response(
                {"detail": f"{type(exc).__name__}: {exc}"},
                status=status.HTTP_500_INTERNAL_SERVER_ERROR,
            )


class NoteSheetReadAPIView(APIView):
    permission_classes = [permissions.IsAuthenticated]

    def get(self, request, pk):
        obj = get_object_or_404(
            NoteSheet.objects.prefetch_related("items__images", "attachments"),
            pk=pk,
        )
        if obj.status == NoteSheet.STATUS_SUBMITTED and not obj.viewed_at:
            obj.viewed_at = timezone.now()
            obj.save(update_fields=["viewed_at", "updated_at"])
        return Response(note_sheet_to_dict(obj, request))


class NoteSheetUpdateAPIView(APIView):
    permission_classes = [permissions.IsAuthenticated]

    def put(self, request, pk):
        try:
            obj = get_object_or_404(NoteSheet, pk=pk)
            body = body_from_request(request)
            ser = NoteSheetWriteSerializer(data=body, partial=True)
            ser.is_valid(raise_exception=True)
            apply_note_sheet(obj, ser.validated_data, username=_username(request))
            save_note_sheet_uploads(request, obj)
            save_note_sheet_goods_images(request, obj, ser.validated_data.get("items"))
            obj = NoteSheet.objects.prefetch_related("items__images", "attachments").get(pk=obj.pk)
            return Response(note_sheet_to_dict(obj, request))
        except Exception as exc:
            from rest_framework.exceptions import ValidationError as DRFValidationError
            from django.http import Http404

            if isinstance(exc, (DRFValidationError, Http404)):
                raise
            return Response(
                {"detail": f"{type(exc).__name__}: {exc}"},
                status=status.HTTP_500_INTERNAL_SERVER_ERROR,
            )


class NoteSheetDeleteAPIView(APIView):
    permission_classes = [permissions.IsAuthenticated]

    def delete(self, request, pk):
        obj = get_object_or_404(NoteSheet, pk=pk)
        if obj.detention_memo_id:
            return Response(
                {"detail": "Cannot delete note sheet linked to a detention memo."},
                status=status.HTTP_400_BAD_REQUEST,
            )
        obj.delete()
        return Response(status=status.HTTP_204_NO_CONTENT)


class NoteSheetApprovalAPIView(APIView):
    permission_classes = [permissions.IsAuthenticated]

    def post(self, request, pk):
        obj = get_object_or_404(
            NoteSheet.objects.prefetch_related("items__images", "attachments"),
            pk=pk,
        )
        ser = NoteSheetApprovalSerializer(data=request.data)
        ser.is_valid(raise_exception=True)
        action = ser.validated_data["action"]
        remarks = (
            ser.validated_data.get("approvalRemarks")
            or ser.validated_data.get("rejectionReason")
            or ""
        )

        if action == "submit":
            if obj.status not in (NoteSheet.STATUS_DRAFT, NoteSheet.STATUS_REJECTED):
                return Response(
                    {"detail": "Only draft/rejected sheets can be submitted."},
                    status=400,
                )
            # Auto-route to Assistant Collector, Deputy Collector, Location Admin, Super Admin
            obj.forward_to = NOTE_SHEET_FORWARD_TO_LABEL
            obj.forward_to_user_id = None
            obj.status = NoteSheet.STATUS_SUBMITTED
            obj.submitted_at = timezone.now()
            obj.rejection_reason = ""
            obj.approval_remarks = ""
            obj.viewed_at = None
            obj.save(
                update_fields=[
                    "forward_to",
                    "forward_to_user_id",
                    "status",
                    "submitted_at",
                    "rejection_reason",
                    "approval_remarks",
                    "viewed_at",
                    "updated_at",
                ]
            )
            notify_note_sheet_submitted(
                obj,
                submitted_by_user_id=getattr(request.user, "id", None),
            )
        elif action == "view":
            if obj.status == NoteSheet.STATUS_SUBMITTED and not obj.viewed_at:
                obj.viewed_at = timezone.now()
                obj.save(update_fields=["viewed_at", "updated_at"])
        elif action == "approve":
            if obj.status != NoteSheet.STATUS_SUBMITTED:
                return Response(
                    {"detail": "Only submitted sheets can be approved."},
                    status=400,
                )
            if not user_can_approve_note_sheet(request.user, obj):
                return Response(
                    {
                        "detail": (
                            "Only Assistant Collector, Deputy Collector, "
                            "Location Admin, or Super Admin can approve this note sheet."
                        )
                    },
                    status=403,
                )
            obj.status = NoteSheet.STATUS_APPROVED
            obj.approved_by = (
                (getattr(request.user, "full_name", None) or "").strip()
                or ser.validated_data.get("approvedBy")
                or _username(request)
            )
            obj.approved_at = timezone.now()
            obj.approval_remarks = remarks
            obj.rejection_reason = ""
            obj.save(
                update_fields=[
                    "status",
                    "approved_by",
                    "approved_at",
                    "approval_remarks",
                    "rejection_reason",
                    "updated_at",
                ]
            )
            mark_note_sheet_notifications_resolved(obj)
        elif action == "reject":
            if obj.status != NoteSheet.STATUS_SUBMITTED:
                return Response(
                    {"detail": "Only submitted sheets can be rejected."},
                    status=400,
                )
            if not user_can_approve_note_sheet(request.user, obj):
                return Response(
                    {
                        "detail": (
                            "Only Assistant Collector, Deputy Collector, "
                            "Location Admin, or Super Admin can reject this note sheet."
                        )
                    },
                    status=403,
                )
            obj.status = NoteSheet.STATUS_REJECTED
            obj.approved_by = (
                (getattr(request.user, "full_name", None) or "").strip()
                or ser.validated_data.get("approvedBy")
                or _username(request)
            )
            obj.approved_at = timezone.now()
            obj.rejection_reason = remarks
            obj.approval_remarks = remarks
            obj.save(
                update_fields=[
                    "status",
                    "approved_by",
                    "approved_at",
                    "rejection_reason",
                    "approval_remarks",
                    "updated_at",
                ]
            )
            mark_note_sheet_notifications_resolved(obj)
        return Response(note_sheet_to_dict(obj, request))


class NoteSheetLinkDetentionAPIView(APIView):
    """Link an approved note sheet to a newly created detention memo (one-time)."""

    permission_classes = [permissions.IsAuthenticated]

    def post(self, request, pk):
        obj = get_object_or_404(
            NoteSheet.objects.prefetch_related("items__images", "attachments"),
            pk=pk,
        )
        if obj.status != NoteSheet.STATUS_APPROVED:
            return Response(
                {"detail": "Note sheet must be approved before creating a detention memo."},
                status=400,
            )
        if obj.detention_memo_id:
            return Response({"detail": "Note sheet already linked to a detention memo."}, status=400)
        ser = LinkDetentionSerializer(data=request.data)
        ser.is_valid(raise_exception=True)
        memo = get_object_or_404(DetentionMemo, pk=ser.validated_data["detentionMemoId"])
        if NoteSheet.objects.filter(detention_memo=memo).exists():
            return Response(
                {"detail": "Detention memo already linked to another note sheet."},
                status=400,
            )
        obj.detention_memo = memo
        obj.save(update_fields=["detention_memo", "updated_at"])
        return Response(note_sheet_to_dict(obj, request))


class AssessmentListAPIView(APIView):
    permission_classes = [permissions.IsAuthenticated]

    def get(self, request):
        memo_id = (request.query_params.get("detentionMemoId") or "").strip()
        status_filter = (request.query_params.get("status") or "").strip()
        qs = DetentionAssessment.objects.select_related("detention_memo").prefetch_related(
            "attachments"
        )
        if memo_id:
            qs = qs.filter(detention_memo_id=memo_id)
        if status_filter:
            qs = qs.filter(status=status_filter)
        return Response([assessment_to_dict(o, request) for o in qs])


class AssessmentCreateAPIView(APIView):
    permission_classes = [permissions.IsAuthenticated]

    def post(self, request):
        try:
            body = body_from_request(request)
            ser = AssessmentWriteSerializer(data=body)
            ser.is_valid(raise_exception=True)
            data = ser.validated_data
            memo_id = data.get("detentionMemoId")
            if not memo_id:
                return Response({"detail": "detentionMemoId is required."}, status=400)
            memo = get_object_or_404(DetentionMemo, pk=memo_id)
            if DetentionAssessment.objects.filter(detention_memo=memo).exists():
                return Response(
                    {"detail": "Assessment already exists for this detention memo."},
                    status=400,
                )
            obj = DetentionAssessment(
                detention_memo=memo,
                status=DetentionAssessment.STATUS_DRAFT,
            )
            apply_assessment(obj, data, username=_username(request))
            save_assessment_uploads(request, obj)
            obj = DetentionAssessment.objects.select_related("detention_memo").prefetch_related(
                "attachments"
            ).get(pk=obj.pk)
            return Response(assessment_to_dict(obj, request), status=status.HTTP_201_CREATED)
        except Exception as exc:
            from rest_framework.exceptions import ValidationError as DRFValidationError
            from django.http import Http404

            if isinstance(exc, (DRFValidationError, Http404)):
                raise
            return Response(
                {"detail": f"{type(exc).__name__}: {exc}"},
                status=status.HTTP_500_INTERNAL_SERVER_ERROR,
            )


class AssessmentReadAPIView(APIView):
    permission_classes = [permissions.IsAuthenticated]

    def get(self, request, pk):
        obj = get_object_or_404(
            DetentionAssessment.objects.select_related("detention_memo").prefetch_related(
                "attachments"
            ),
            pk=pk,
        )
        if obj.status == DetentionAssessment.STATUS_SUBMITTED and not obj.viewed_at:
            obj.viewed_at = timezone.now()
            obj.save(update_fields=["viewed_at", "updated_at"])
        return Response(assessment_to_dict(obj, request))


class AssessmentUpdateAPIView(APIView):
    permission_classes = [permissions.IsAuthenticated]

    def put(self, request, pk):
        obj = get_object_or_404(DetentionAssessment, pk=pk)
        if obj.status not in (
            DetentionAssessment.STATUS_DRAFT,
            DetentionAssessment.STATUS_REJECTED,
        ):
            return Response(
                {"detail": "Only draft or rejected assessments can be edited."},
                status=400,
            )
        body = body_from_request(request)
        ser = AssessmentWriteSerializer(data=body, partial=True)
        ser.is_valid(raise_exception=True)
        apply_assessment(obj, ser.validated_data, username=_username(request))
        save_assessment_uploads(request, obj)
        obj = DetentionAssessment.objects.select_related("detention_memo").prefetch_related(
            "attachments"
        ).get(pk=obj.pk)
        return Response(assessment_to_dict(obj, request))


class AssessmentDeleteAPIView(APIView):
    permission_classes = [permissions.IsAuthenticated]

    def delete(self, request, pk):
        obj = get_object_or_404(DetentionAssessment, pk=pk)
        if obj.status == DetentionAssessment.STATUS_APPROVED:
            return Response(
                {"detail": "Cannot delete an approved assessment."},
                status=400,
            )
        obj.delete()
        return Response(status=status.HTTP_204_NO_CONTENT)


class AssessmentApprovalAPIView(APIView):
    permission_classes = [permissions.IsAuthenticated]

    def post(self, request, pk):
        obj = get_object_or_404(
            DetentionAssessment.objects.select_related("detention_memo").prefetch_related(
                "attachments"
            ),
            pk=pk,
        )
        ser = AssessmentApprovalSerializer(data=request.data)
        ser.is_valid(raise_exception=True)
        action = ser.validated_data["action"]
        remarks = (
            ser.validated_data.get("approvalRemarks")
            or ser.validated_data.get("rejectionReason")
            or ""
        )

        if action == "submit":
            if obj.status not in (
                DetentionAssessment.STATUS_DRAFT,
                DetentionAssessment.STATUS_REJECTED,
            ):
                return Response(
                    {"detail": "Only draft/rejected assessments can be submitted."},
                    status=400,
                )
            if not (obj.examining_officer or "").strip():
                return Response(
                    {"detail": "Examining officer is required before submit."},
                    status=400,
                )
            if obj.document_relevance == DetentionAssessment.RELEVANCE_PENDING:
                return Response(
                    {"detail": "Set document relevance (Relevant / Not Relevant) before submit."},
                    status=400,
                )
            obj.status = DetentionAssessment.STATUS_SUBMITTED
            obj.submitted_at = timezone.now()
            obj.rejection_reason = ""
            obj.approval_remarks = ""
            obj.viewed_at = None
            obj.updated_by = _username(request) or obj.updated_by
            obj.save(
                update_fields=[
                    "status",
                    "submitted_at",
                    "rejection_reason",
                    "approval_remarks",
                    "viewed_at",
                    "updated_by",
                    "updated_at",
                ]
            )
            notify_assessment_submitted(
                obj,
                submitted_by_user_id=getattr(request.user, "id", None),
            )
        elif action == "view":
            if obj.status == DetentionAssessment.STATUS_SUBMITTED and not obj.viewed_at:
                obj.viewed_at = timezone.now()
                obj.save(update_fields=["viewed_at", "updated_at"])
        elif action == "approve":
            if obj.status != DetentionAssessment.STATUS_SUBMITTED:
                return Response(
                    {"detail": "Only submitted assessments can be approved."},
                    status=400,
                )
            if not user_can_approve_assessment(request.user, obj):
                return Response(
                    {
                        "detail": (
                            "Only Assistant Collector, Deputy Collector, "
                            "Location Admin, or Super Admin can approve this assessment."
                        )
                    },
                    status=403,
                )
            obj.status = DetentionAssessment.STATUS_APPROVED
            obj.approved_by = (
                (getattr(request.user, "full_name", None) or "").strip()
                or ser.validated_data.get("approvedBy")
                or _username(request)
            )
            obj.approved_at = timezone.now()
            obj.approval_remarks = remarks
            obj.rejection_reason = ""
            obj.save(
                update_fields=[
                    "status",
                    "approved_by",
                    "approved_at",
                    "approval_remarks",
                    "rejection_reason",
                    "updated_at",
                ]
            )
            mark_assessment_notifications_resolved(obj)
        elif action == "reject":
            if obj.status != DetentionAssessment.STATUS_SUBMITTED:
                return Response(
                    {"detail": "Only submitted assessments can be rejected."},
                    status=400,
                )
            if not user_can_approve_assessment(request.user, obj):
                return Response(
                    {
                        "detail": (
                            "Only Assistant Collector, Deputy Collector, "
                            "Location Admin, or Super Admin can reject this assessment."
                        )
                    },
                    status=403,
                )
            obj.status = DetentionAssessment.STATUS_REJECTED
            obj.approved_by = (
                (getattr(request.user, "full_name", None) or "").strip()
                or ser.validated_data.get("approvedBy")
                or _username(request)
            )
            obj.approved_at = timezone.now()
            obj.rejection_reason = remarks
            obj.approval_remarks = remarks
            obj.save(
                update_fields=[
                    "status",
                    "approved_by",
                    "approved_at",
                    "rejection_reason",
                    "approval_remarks",
                    "updated_at",
                ]
            )
            mark_assessment_notifications_resolved(obj)

        obj = DetentionAssessment.objects.select_related("detention_memo").prefetch_related(
            "attachments"
        ).get(pk=obj.pk)
        return Response(assessment_to_dict(obj, request))


class RecoveryMemoListAPIView(APIView):
    permission_classes = [permissions.IsAuthenticated]

    def get(self, request):
        memo_id = (request.query_params.get("detentionMemoId") or "").strip()
        qs = RecoveryMemo.objects.select_related("detention_memo", "assessment", "deposit_account").all()
        if memo_id:
            qs = qs.filter(detention_memo_id=memo_id)
        return Response([recovery_memo_to_dict(o) for o in qs])


class RecoveryMemoCreateAPIView(APIView):
    permission_classes = [permissions.IsAuthenticated]

    def post(self, request):
        ser = RecoveryMemoWriteSerializer(data=request.data)
        ser.is_valid(raise_exception=True)
        data = ser.validated_data
        memo = get_object_or_404(DetentionMemo, pk=data["detentionMemoId"])
        obj = RecoveryMemo(detention_memo=memo)
        if data.get("assessmentId"):
            obj.assessment = get_object_or_404(DetentionAssessment, pk=data["assessmentId"])
        apply_recovery(obj, data, username=_username(request))
        if data.get("createDeposit"):
            maybe_create_deposit_for_recovery(obj)
            obj.refresh_from_db()
        return Response(recovery_memo_to_dict(obj), status=status.HTTP_201_CREATED)


class RecoveryMemoReadAPIView(APIView):
    permission_classes = [permissions.IsAuthenticated]

    def get(self, request, pk):
        obj = get_object_or_404(
            RecoveryMemo.objects.select_related("detention_memo", "assessment", "deposit_account"),
            pk=pk,
        )
        return Response(recovery_memo_to_dict(obj))


class RecoveryMemoUpdateAPIView(APIView):
    permission_classes = [permissions.IsAuthenticated]

    def put(self, request, pk):
        obj = get_object_or_404(
            RecoveryMemo.objects.select_related("detention_memo", "assessment", "deposit_account"),
            pk=pk,
        )
        payload = dict(request.data)
        payload.setdefault("detentionMemoId", str(obj.detention_memo_id))
        ser = RecoveryMemoWriteSerializer(data=payload)
        ser.is_valid(raise_exception=True)
        apply_recovery(obj, ser.validated_data, username=_username(request))
        if ser.validated_data.get("createDeposit"):
            maybe_create_deposit_for_recovery(obj)
        obj.refresh_from_db()
        return Response(recovery_memo_to_dict(obj))


class RecoveryMemoDeleteAPIView(APIView):
    permission_classes = [permissions.IsAuthenticated]

    def delete(self, request, pk):
        obj = get_object_or_404(RecoveryMemo, pk=pk)
        obj.delete()
        return Response(status=status.HTTP_204_NO_CONTENT)


class RecoveryMemoApprovalAPIView(APIView):
    permission_classes = [permissions.IsAuthenticated]

    def post(self, request, pk):
        obj = get_object_or_404(
            RecoveryMemo.objects.select_related("detention_memo", "assessment", "deposit_account"),
            pk=pk,
        )
        ser = RecoveryApprovalSerializer(data=request.data)
        ser.is_valid(raise_exception=True)
        action = ser.validated_data["action"]
        remarks = (
            ser.validated_data.get("approvalRemarks")
            or ser.validated_data.get("rejectionReason")
            or ""
        ).strip()
        actor = (ser.validated_data.get("approvedBy") or _username(request) or "").strip()

        if action == "view":
            if obj.approval_status == RecoveryMemo.STATUS_PENDING and not obj.viewed_at:
                obj.viewed_at = timezone.now()
                obj.save(update_fields=["viewed_at", "updated_at"])
            return Response(recovery_memo_to_dict(obj))

        if action == "submit":
            if obj.approval_status not in (RecoveryMemo.STATUS_DRAFT, RecoveryMemo.STATUS_REJECTED):
                return Response(
                    {"detail": "Only draft/rejected recovery memos can be submitted."},
                    status=400,
                )
            if not (obj.recovery_officer or "").strip():
                return Response(
                    {"detail": "Recovery officer is required before submit."},
                    status=400,
                )
            obj.approval_status = RecoveryMemo.STATUS_PENDING
            obj.submitted_at = timezone.now()
            obj.rejection_reason = ""
            obj.approval_remarks = ""
            obj.save(
                update_fields=[
                    "approval_status",
                    "submitted_at",
                    "rejection_reason",
                    "approval_remarks",
                    "updated_at",
                ]
            )
            notify_recovery_submitted(
                obj,
                submitted_by_user_id=getattr(request.user, "id", None),
            )

        elif action == "approve":
            if obj.approval_status != RecoveryMemo.STATUS_PENDING:
                return Response(
                    {"detail": "Only pending recovery memos can be approved."},
                    status=400,
                )
            if not user_can_approve_recovery(request.user, obj):
                return Response(
                    {
                        "detail": (
                            f"Only {RECOVERY_FORWARD_TO_LABEL} can approve this recovery memo."
                        )
                    },
                    status=403,
                )
            obj.approval_status = RecoveryMemo.STATUS_APPROVED
            obj.approved_by = actor
            obj.approved_at = timezone.now()
            obj.approval_remarks = remarks
            obj.rejection_reason = ""
            obj.save(
                update_fields=[
                    "approval_status",
                    "approved_by",
                    "approved_at",
                    "approval_remarks",
                    "rejection_reason",
                    "updated_at",
                ]
            )
            mark_recovery_notifications_resolved(obj)

        elif action == "reject":
            if obj.approval_status != RecoveryMemo.STATUS_PENDING:
                return Response(
                    {"detail": "Only pending recovery memos can be rejected."},
                    status=400,
                )
            if not user_can_approve_recovery(request.user, obj):
                return Response(
                    {
                        "detail": (
                            f"Only {RECOVERY_FORWARD_TO_LABEL} can reject this recovery memo."
                        )
                    },
                    status=403,
                )
            if not remarks:
                return Response({"detail": "Rejection reason is required."}, status=400)
            obj.approval_status = RecoveryMemo.STATUS_REJECTED
            obj.approved_by = actor
            obj.approved_at = timezone.now()
            obj.rejection_reason = remarks
            obj.approval_remarks = remarks
            obj.save(
                update_fields=[
                    "approval_status",
                    "approved_by",
                    "approved_at",
                    "rejection_reason",
                    "approval_remarks",
                    "updated_at",
                ]
            )
            mark_recovery_notifications_resolved(obj)

        obj = RecoveryMemo.objects.select_related(
            "detention_memo", "assessment", "deposit_account"
        ).get(pk=obj.pk)
        return Response(recovery_memo_to_dict(obj))


class SeizureReportListAPIView(APIView):
    permission_classes = [permissions.IsAuthenticated]

    def get(self, request):
        qs = SeizureReport.objects.select_related("detention_memo", "assessment", "recovery_memo").all()
        return Response([seizure_report_to_dict(o) for o in qs])


class SeizureReportCreateAPIView(APIView):
    permission_classes = [permissions.IsAuthenticated]

    def post(self, request):
        ser = SeizureReportWriteSerializer(data=request.data)
        ser.is_valid(raise_exception=True)
        data = ser.validated_data
        memo = get_object_or_404(DetentionMemo, pk=data["detentionMemoId"])
        assessment = None
        recovery = None
        if data.get("assessmentId"):
            assessment = get_object_or_404(DetentionAssessment, pk=data["assessmentId"])
        else:
            assessment = DetentionAssessment.objects.filter(detention_memo=memo).order_by("-created_at").first()
        if data.get("recoveryMemoId"):
            recovery = get_object_or_404(RecoveryMemo, pk=data["recoveryMemoId"])
        else:
            recovery = (
                RecoveryMemo.objects.filter(detention_memo=memo, approval_status=RecoveryMemo.STATUS_APPROVED)
                .order_by("-created_at")
                .first()
            )
        if data.get("status") == SeizureReport.STATUS_SUBMITTED:
            if not assessment or assessment.status != DetentionAssessment.STATUS_APPROVED:
                return Response({"detail": "Approved assessment is required to submit."}, status=400)
            if not recovery or recovery.approval_status != RecoveryMemo.STATUS_APPROVED:
                return Response({"detail": "Approved recovery memo is required to submit."}, status=400)

        obj = SeizureReport(
            detention_memo=memo,
            assessment=assessment,
            recovery_memo=recovery,
        )
        notes = data.get("recoveryAssessmentNotes") or build_recovery_assessment_sheet(memo, assessment, recovery)
        data = {**data, "recoveryAssessmentNotes": notes}
        apply_seizure_report(obj, data)
        return Response(seizure_report_to_dict(obj), status=status.HTTP_201_CREATED)


class SeizureReportReadAPIView(APIView):
    permission_classes = [permissions.IsAuthenticated]

    def get(self, request, pk):
        obj = get_object_or_404(
            SeizureReport.objects.select_related("detention_memo", "assessment", "recovery_memo"),
            pk=pk,
        )
        return Response(seizure_report_to_dict(obj))


class SeizureReportUpdateAPIView(APIView):
    permission_classes = [permissions.IsAuthenticated]

    def put(self, request, pk):
        obj = get_object_or_404(
            SeizureReport.objects.select_related("detention_memo", "assessment", "recovery_memo"),
            pk=pk,
        )
        payload = dict(request.data)
        payload.setdefault("detentionMemoId", str(obj.detention_memo_id))
        ser = SeizureReportWriteSerializer(data=payload)
        ser.is_valid(raise_exception=True)
        data = ser.validated_data
        if data.get("status") == SeizureReport.STATUS_SUBMITTED:
            assessment = obj.assessment
            recovery = obj.recovery_memo
            if data.get("assessmentId"):
                assessment = get_object_or_404(DetentionAssessment, pk=data["assessmentId"])
            if data.get("recoveryMemoId"):
                recovery = get_object_or_404(RecoveryMemo, pk=data["recoveryMemoId"])
            if not assessment or assessment.status != DetentionAssessment.STATUS_APPROVED:
                return Response({"detail": "Approved assessment is required to submit."}, status=400)
            if not recovery or recovery.approval_status != RecoveryMemo.STATUS_APPROVED:
                return Response({"detail": "Approved recovery memo is required to submit."}, status=400)
        apply_seizure_report(obj, data)
        obj.refresh_from_db()
        return Response(seizure_report_to_dict(obj))


class SeizureReportDeleteAPIView(APIView):
    permission_classes = [permissions.IsAuthenticated]

    def delete(self, request, pk):
        obj = get_object_or_404(SeizureReport, pk=pk)
        obj.delete()
        return Response(status=status.HTTP_204_NO_CONTENT)


class SeizureManagementOverviewAPIView(APIView):
    permission_classes = [permissions.IsAuthenticated]

    def get(self, request):
        return Response(
            {
                "noteSheets": NoteSheet.objects.count(),
                "noteSheetsPending": NoteSheet.objects.filter(status=NoteSheet.STATUS_SUBMITTED).count(),
                "noteSheetsApprovedAvailable": NoteSheet.objects.filter(
                    status=NoteSheet.STATUS_APPROVED, detention_memo__isnull=True
                ).count(),
                "assessments": DetentionAssessment.objects.count(),
                "assessmentsPending": DetentionAssessment.objects.filter(
                    status=DetentionAssessment.STATUS_SUBMITTED
                ).count(),
                "recoveryMemos": RecoveryMemo.objects.count(),
                "recoveryPendingApproval": RecoveryMemo.objects.filter(
                    approval_status=RecoveryMemo.STATUS_PENDING
                ).count(),
                "seizureReports": SeizureReport.objects.count(),
                "seizureReportsSubmitted": SeizureReport.objects.filter(
                    status=SeizureReport.STATUS_SUBMITTED
                ).count(),
            }
        )


class NoteSheetNotificationListAPIView(APIView):
    """List in-app notifications for the logged-in official (note sheets + assessments + recovery)."""

    permission_classes = [permissions.IsAuthenticated]

    def get(self, request):
        unread_only = (request.query_params.get("unread") or "").strip() in ("1", "true", "yes")
        uid = request.user.id

        ns_qs = NoteSheetNotification.objects.filter(recipient_user_id=uid).select_related("note_sheet")
        as_qs = AssessmentNotification.objects.filter(recipient_user_id=uid).select_related(
            "assessment__detention_memo"
        )
        rc_qs = RecoveryNotification.objects.filter(recipient_user_id=uid).select_related(
            "recovery_memo__detention_memo"
        )
        if unread_only:
            ns_qs = ns_qs.filter(is_read=False)
            as_qs = as_qs.filter(is_read=False)
            rc_qs = rc_qs.filter(is_read=False)

        combined = (
            [_notification_to_dict(n) for n in ns_qs[:50]]
            + [_assessment_notification_to_dict(n) for n in as_qs[:50]]
            + [_recovery_notification_to_dict(n) for n in rc_qs[:50]]
        )
        combined.sort(key=lambda x: x.get("createdAt") or "", reverse=True)
        combined = combined[:50]

        unread_count = (
            NoteSheetNotification.objects.filter(recipient_user_id=uid, is_read=False).count()
            + AssessmentNotification.objects.filter(recipient_user_id=uid, is_read=False).count()
            + RecoveryNotification.objects.filter(recipient_user_id=uid, is_read=False).count()
        )
        return Response(
            {
                "unreadCount": unread_count,
                "results": combined,
            }
        )


class NoteSheetNotificationMarkReadAPIView(APIView):
    permission_classes = [permissions.IsAuthenticated]

    def post(self, request, pk=None):
        mark_all = False
        if isinstance(getattr(request, "data", None), dict):
            mark_all = request.data.get("all") in (True, "1", "true", "yes")
        if not mark_all:
            mark_all = request.query_params.get("all") in ("1", "true", "yes")
        if mark_all:
            NoteSheetNotification.objects.filter(
                recipient_user_id=request.user.id,
                is_read=False,
            ).update(is_read=True)
            AssessmentNotification.objects.filter(
                recipient_user_id=request.user.id,
                is_read=False,
            ).update(is_read=True)
            RecoveryNotification.objects.filter(
                recipient_user_id=request.user.id,
                is_read=False,
            ).update(is_read=True)
            return Response({"detail": "All notifications marked as read."})
        if pk:
            ns = NoteSheetNotification.objects.filter(
                pk=pk, recipient_user_id=request.user.id
            ).first()
            if ns:
                if not ns.is_read:
                    ns.is_read = True
                    ns.save(update_fields=["is_read"])
                return Response(_notification_to_dict(ns))
            an = AssessmentNotification.objects.filter(
                pk=pk, recipient_user_id=request.user.id
            ).first()
            if an:
                if not an.is_read:
                    an.is_read = True
                    an.save(update_fields=["is_read"])
                return Response(_assessment_notification_to_dict(an))
            rn = get_object_or_404(
                RecoveryNotification,
                pk=pk,
                recipient_user_id=request.user.id,
            )
            if not rn.is_read:
                rn.is_read = True
                rn.save(update_fields=["is_read"])
            return Response(_recovery_notification_to_dict(rn))
        return Response({"detail": "Provide notification id or {\"all\": true}."}, status=400)
