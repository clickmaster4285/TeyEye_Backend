from __future__ import annotations

import json
import uuid
from typing import Any

from django.core.exceptions import ValidationError
from django.utils import timezone
from rest_framework import serializers

from detentions.models import DepositAccountEntry, DetentionMemo
from detentions.serializers import create_deposit_account_entry

from .models import (
    DetentionAssessment,
    DetentionAssessmentAttachment,
    NoteSheet,
    NoteSheetAttachment,
    NoteSheetItem,
    NoteSheetItemImage,
    RecoveryMemo,
    SeizureReport,
)


def _is_uuid(value: str) -> bool:
    try:
        uuid.UUID(str(value))
        return True
    except (ValueError, TypeError, AttributeError):
        return False


def _find_note_sheet_item(obj: NoteSheet, client_line_id: str) -> NoteSheetItem | None:
    if not client_line_id:
        return None
    existing = obj.items.filter(client_line_id=client_line_id).first()
    if existing is not None:
        return existing
    if not _is_uuid(client_line_id):
        return None
    try:
        return obj.items.filter(pk=client_line_id).first()
    except (ValueError, TypeError, ValidationError):
        return None


def _absolute_media_url(request, file_field) -> str:
    if not file_field or not getattr(file_field, "name", None):
        return ""
    relative = file_field.url
    if request:
        try:
            return request.build_absolute_uri(relative)
        except Exception:
            pass
    return relative


def _iso(dt) -> str:
    return dt.isoformat() if dt else ""


def _note_sheet_item_to_dict(item: NoteSheetItem, request=None) -> dict:
    images = []
    for img in item.images.all():
        url = _absolute_media_url(request, img.image)
        if url:
            images.append(url)
    description = item.product or ""
    return {
        "id": str(item.id),
        "clientLineId": item.client_line_id or str(item.id),
        "qrCodeNumber": item.qr_code_number or "",
        "product": description,
        "description": description,
        "pctCode": item.pct_code or "",
        "quantity": item.quantity or "",
        "unit": item.unit or "",
        "condition": item.condition or "",
        "estimatedValue": item.estimated_value or "",
        "assessableValuePkr": item.estimated_value or "",
        "perishable": bool(item.perishable),
        "identificationRef": item.identification_ref or "",
        "remarks": item.remarks or "",
        "itemNotes": item.remarks or "",
        "images": images,
        "sortOrder": item.sort_order,
    }


def _note_sheet_attachment_to_dict(att: NoteSheetAttachment, request=None) -> dict:
    return {
        "id": str(att.id),
        "fileType": att.file_type or "",
        "originalFilename": att.original_filename or "",
        "url": _absolute_media_url(request, att.file),
        "uploadedAt": _iso(att.uploaded_at),
    }


def _note_sheet_timeline(obj: NoteSheet) -> list[dict]:
    steps = [
        {
            "key": "created",
            "label": "Created",
            "at": _iso(obj.created_at),
            "done": bool(obj.created_at),
        },
        {
            "key": "submitted",
            "label": "Submitted",
            "at": _iso(obj.submitted_at),
            "done": bool(obj.submitted_at)
            or obj.status
            in (NoteSheet.STATUS_SUBMITTED, NoteSheet.STATUS_APPROVED, NoteSheet.STATUS_REJECTED),
        },
        {
            "key": "viewed",
            "label": "Viewed by Officer",
            "at": _iso(obj.viewed_at),
            "done": bool(obj.viewed_at),
        },
        {
            "key": "decision",
            "label": "Approved" if obj.status == NoteSheet.STATUS_APPROVED else (
                "Rejected" if obj.status == NoteSheet.STATUS_REJECTED else "Decision"
            ),
            "at": _iso(obj.approved_at),
            "done": obj.status in (NoteSheet.STATUS_APPROVED, NoteSheet.STATUS_REJECTED),
        },
        {
            "key": "detentionMemo",
            "label": "Detention Memo Created",
            "at": "",
            "done": bool(obj.detention_memo_id),
        },
    ]
    return steps


def note_sheet_to_dict(obj: NoteSheet, request=None) -> dict:
    items = list(obj.items.all())
    attachments = list(obj.attachments.all())
    evidence = obj.evidence_collected if isinstance(obj.evidence_collected, list) else []
    return {
        "id": str(obj.id),
        # Basic
        "noteSheetNo": obj.note_sheet_no or "",
        "referenceNumber": obj.reference_number or obj.note_sheet_no or "",
        "dateTime": obj.date_time or "",
        "office": obj.office or "",
        "caseNo": obj.case_no or "",
        "priority": obj.priority or NoteSheet.PRIORITY_NORMAL,
        "status": obj.status,
        "subject": obj.subject or "",
        # Officer
        "preparedBy": obj.prepared_by or "",
        "badgeId": obj.badge_id or "",
        "designation": obj.designation or "",
        "department": obj.department or "",
        "officerContact": obj.officer_contact or "",
        # Accused
        "accusedName": obj.accused_name or "",
        "accusedFatherName": obj.accused_father_name or "",
        "accusedCnic": obj.accused_cnic or "",
        "accusedMobile": obj.accused_mobile or "",
        "accusedAddress": obj.accused_address or "",
        "businessName": obj.business_name or "",
        "ntnStrn": obj.ntn_strn or "",
        # Goods
        "items": [_note_sheet_item_to_dict(i, request) for i in items],
        # Location
        "placeOfInspection": obj.place_of_inspection or "",
        "warehouseShop": obj.warehouse_shop or "",
        "gpsLocation": obj.gps_location or "",
        "inspectionDate": obj.inspection_date or "",
        # Narrative
        "groundsOfSuspicion": obj.grounds_of_suspicion or "",
        "evidenceCollected": evidence,
        "preliminaryFindings": obj.preliminary_findings or "",
        "recommendation": obj.recommendation or "",
        "content": obj.content or "",
        # Attachments
        "attachments": [_note_sheet_attachment_to_dict(a, request) for a in attachments],
        # Approval
        "preparedSignature": obj.prepared_signature or "",
        "preparedDate": obj.prepared_date or "",
        "forwardTo": obj.forward_to or "",
        "forwardToUserId": obj.forward_to_user_id or None,
        "approvedBy": obj.approved_by or "",
        "approvedAt": _iso(obj.approved_at),
        "approvalRemarks": obj.approval_remarks or "",
        "rejectionReason": obj.rejection_reason or "",
        "submittedAt": _iso(obj.submitted_at),
        "viewedAt": _iso(obj.viewed_at),
        # Links / audit
        "detentionMemoId": str(obj.detention_memo_id) if obj.detention_memo_id else "",
        "createdBy": obj.created_by or "",
        "updatedBy": obj.updated_by or "",
        "createdAt": _iso(obj.created_at),
        "updatedAt": _iso(obj.updated_at),
        "timeline": _note_sheet_timeline(obj),
    }


def assessment_to_dict(obj: DetentionAssessment, request=None) -> dict:
    memo = obj.detention_memo
    attachments = list(obj.attachments.all()) if hasattr(obj, "attachments") else []
    return {
        "id": str(obj.id),
        "detentionMemoId": str(obj.detention_memo_id),
        "caseNo": memo.case_no if memo else "",
        "referenceNumber": memo.reference_number if memo else "",
        "assessmentDate": obj.assessment_date or "",
        "examiningOfficer": obj.examining_officer or "",
        "goodsCondition": obj.goods_condition or "",
        "valuationNotes": obj.valuation_notes or "",
        "findings": obj.findings or "",
        "documentRelevance": obj.document_relevance,
        "status": obj.status,
        "approvedBy": obj.approved_by or "",
        "approvedAt": _iso(obj.approved_at),
        "approvalRemarks": obj.approval_remarks or "",
        "rejectionReason": obj.rejection_reason or "",
        "submittedAt": _iso(obj.submitted_at),
        "viewedAt": _iso(obj.viewed_at),
        "createdBy": obj.created_by or "",
        "updatedBy": obj.updated_by or "",
        "attachments": [
            {
                "id": str(a.id),
                "fileType": a.file_type,
                "originalFilename": a.original_filename or "",
                "url": _absolute_media_url(request, a.file),
                "uploadedAt": _iso(a.uploaded_at),
            }
            for a in attachments
        ],
        "createdAt": _iso(obj.created_at),
        "updatedAt": _iso(obj.updated_at),
        "timeline": _assessment_timeline(obj),
    }


def _assessment_timeline(obj: DetentionAssessment) -> list[dict]:
    events: list[dict] = []
    events.append(
        {
            "action": "created",
            "label": "Created",
            "at": _iso(obj.created_at),
            "by": obj.created_by or "",
        }
    )
    if obj.submitted_at:
        events.append(
            {
                "action": "submitted",
                "label": "Submitted for approval",
                "at": _iso(obj.submitted_at),
                "by": obj.updated_by or obj.created_by or "",
            }
        )
    if obj.status == DetentionAssessment.STATUS_APPROVED and obj.approved_at:
        events.append(
            {
                "action": "approved",
                "label": "Approved",
                "at": _iso(obj.approved_at),
                "by": obj.approved_by or "",
                "remarks": obj.approval_remarks or "",
            }
        )
    if obj.status == DetentionAssessment.STATUS_REJECTED and obj.approved_at:
        events.append(
            {
                "action": "rejected",
                "label": "Rejected",
                "at": _iso(obj.approved_at),
                "by": obj.approved_by or "",
                "remarks": obj.rejection_reason or "",
            }
        )
    return events


def recovery_memo_to_dict(obj: RecoveryMemo) -> dict:
    memo = obj.detention_memo
    return {
        "id": str(obj.id),
        "detentionMemoId": str(obj.detention_memo_id),
        "assessmentId": str(obj.assessment_id) if obj.assessment_id else "",
        "caseNo": memo.case_no if memo else "",
        "referenceNumber": memo.reference_number if memo else "",
        "category": obj.category,
        "recoveryDate": obj.recovery_date or "",
        "recoveryOfficer": obj.recovery_officer or "",
        "goodsDescription": obj.goods_description or "",
        "quantity": obj.quantity or "",
        "remarks": obj.remarks or "",
        "approvalStatus": obj.approval_status,
        "approvedBy": obj.approved_by or "",
        "approvedAt": _iso(obj.approved_at),
        "approvalRemarks": getattr(obj, "approval_remarks", None) or "",
        "rejectionReason": obj.rejection_reason or "",
        "submittedAt": _iso(getattr(obj, "submitted_at", None)),
        "depositAccountId": str(obj.deposit_account_id) if obj.deposit_account_id else "",
        "createdBy": getattr(obj, "created_by", None) or "",
        "updatedBy": getattr(obj, "updated_by", None) or "",
        "createdAt": _iso(obj.created_at),
        "updatedAt": _iso(obj.updated_at),
    }


def seizure_report_to_dict(obj: SeizureReport) -> dict:
    memo = obj.detention_memo
    return {
        "id": str(obj.id),
        "detentionMemoId": str(obj.detention_memo_id),
        "assessmentId": str(obj.assessment_id) if obj.assessment_id else "",
        "recoveryMemoId": str(obj.recovery_memo_id) if obj.recovery_memo_id else "",
        "caseNo": memo.case_no if memo else "",
        "referenceNumber": memo.reference_number if memo else "",
        "reportDate": obj.report_date or "",
        "preparedBy": obj.prepared_by or "",
        "summary": obj.summary or "",
        "recoveryAssessmentNotes": obj.recovery_assessment_notes or "",
        "status": obj.status,
        "submittedAt": _iso(obj.submitted_at),
        "createdAt": _iso(obj.created_at),
        "updatedAt": _iso(obj.updated_at),
    }


class NoteSheetItemWriteSerializer(serializers.Serializer):
    id = serializers.CharField(required=False, allow_blank=True)
    clientLineId = serializers.CharField(required=False, allow_blank=True)
    qrCodeNumber = serializers.CharField(required=False, allow_blank=True)
    product = serializers.CharField(required=False, allow_blank=True)
    description = serializers.CharField(required=False, allow_blank=True)
    pctCode = serializers.CharField(required=False, allow_blank=True)
    quantity = serializers.CharField(required=False, allow_blank=True)
    unit = serializers.CharField(required=False, allow_blank=True)
    condition = serializers.CharField(required=False, allow_blank=True)
    estimatedValue = serializers.CharField(required=False, allow_blank=True)
    assessableValuePkr = serializers.CharField(required=False, allow_blank=True)
    perishable = serializers.BooleanField(required=False, default=False)
    identificationRef = serializers.CharField(required=False, allow_blank=True)
    remarks = serializers.CharField(required=False, allow_blank=True)
    itemNotes = serializers.CharField(required=False, allow_blank=True)
    sortOrder = serializers.IntegerField(required=False, min_value=0)


class NoteSheetWriteSerializer(serializers.Serializer):
    noteSheetNo = serializers.CharField(required=False, allow_blank=True)
    referenceNumber = serializers.CharField(required=False, allow_blank=True)
    dateTime = serializers.CharField(required=False, allow_blank=True)
    office = serializers.CharField(required=False, allow_blank=True)
    caseNo = serializers.CharField(required=False, allow_blank=True)
    priority = serializers.ChoiceField(
        choices=[c[0] for c in NoteSheet.PRIORITY_CHOICES],
        required=False,
    )
    status = serializers.ChoiceField(
        choices=[c[0] for c in NoteSheet.STATUS_CHOICES],
        required=False,
    )
    subject = serializers.CharField(required=False, allow_blank=True)

    preparedBy = serializers.CharField(required=False, allow_blank=True)
    badgeId = serializers.CharField(required=False, allow_blank=True)
    designation = serializers.CharField(required=False, allow_blank=True)
    department = serializers.CharField(required=False, allow_blank=True)
    officerContact = serializers.CharField(required=False, allow_blank=True)

    accusedName = serializers.CharField(required=False, allow_blank=True)
    accusedFatherName = serializers.CharField(required=False, allow_blank=True)
    accusedCnic = serializers.CharField(required=False, allow_blank=True)
    accusedMobile = serializers.CharField(required=False, allow_blank=True)
    accusedAddress = serializers.CharField(required=False, allow_blank=True)
    businessName = serializers.CharField(required=False, allow_blank=True)
    ntnStrn = serializers.CharField(required=False, allow_blank=True)

    placeOfInspection = serializers.CharField(required=False, allow_blank=True)
    warehouseShop = serializers.CharField(required=False, allow_blank=True)
    gpsLocation = serializers.CharField(required=False, allow_blank=True)
    inspectionDate = serializers.CharField(required=False, allow_blank=True)

    groundsOfSuspicion = serializers.CharField(required=False, allow_blank=True)
    evidenceCollected = serializers.ListField(
        child=serializers.CharField(allow_blank=True),
        required=False,
    )
    preliminaryFindings = serializers.CharField(required=False, allow_blank=True)
    recommendation = serializers.ChoiceField(
        choices=[c[0] for c in NoteSheet.RECOMMENDATION_CHOICES],
        required=False,
        allow_blank=True,
    )
    content = serializers.CharField(required=False, allow_blank=True)

    preparedSignature = serializers.CharField(required=False, allow_blank=True)
    preparedDate = serializers.CharField(required=False, allow_blank=True)
    forwardTo = serializers.CharField(required=False, allow_blank=True)
    forwardToUserId = serializers.IntegerField(required=False, allow_null=True)
    approvalRemarks = serializers.CharField(required=False, allow_blank=True)

    items = NoteSheetItemWriteSerializer(many=True, required=False)


class NoteSheetApprovalSerializer(serializers.Serializer):
    action = serializers.ChoiceField(choices=["submit", "approve", "reject", "view"])
    approvedBy = serializers.CharField(required=False, allow_blank=True)
    rejectionReason = serializers.CharField(required=False, allow_blank=True)
    approvalRemarks = serializers.CharField(required=False, allow_blank=True)


class AssessmentWriteSerializer(serializers.Serializer):
    detentionMemoId = serializers.UUIDField(required=False)
    assessmentDate = serializers.CharField(required=False, allow_blank=True)
    examiningOfficer = serializers.CharField(required=False, allow_blank=True)
    goodsCondition = serializers.CharField(required=False, allow_blank=True)
    valuationNotes = serializers.CharField(required=False, allow_blank=True)
    findings = serializers.CharField(required=False, allow_blank=True)
    documentRelevance = serializers.ChoiceField(
        choices=[c[0] for c in DetentionAssessment.RELEVANCE_CHOICES],
        required=False,
    )
    status = serializers.ChoiceField(
        choices=[c[0] for c in DetentionAssessment.STATUS_CHOICES],
        required=False,
    )
    createdBy = serializers.CharField(required=False, allow_blank=True)
    updatedBy = serializers.CharField(required=False, allow_blank=True)


class AssessmentApprovalSerializer(serializers.Serializer):
    action = serializers.ChoiceField(choices=["submit", "approve", "reject", "view"])
    approvedBy = serializers.CharField(required=False, allow_blank=True)
    rejectionReason = serializers.CharField(required=False, allow_blank=True)
    approvalRemarks = serializers.CharField(required=False, allow_blank=True)


class RecoveryMemoWriteSerializer(serializers.Serializer):
    detentionMemoId = serializers.UUIDField()
    assessmentId = serializers.UUIDField(required=False, allow_null=True)
    category = serializers.ChoiceField(
        choices=[c[0] for c in RecoveryMemo.CATEGORY_CHOICES],
        required=False,
    )
    recoveryDate = serializers.CharField(required=False, allow_blank=True)
    recoveryOfficer = serializers.CharField(required=False, allow_blank=True)
    goodsDescription = serializers.CharField(required=False, allow_blank=True)
    quantity = serializers.CharField(required=False, allow_blank=True)
    remarks = serializers.CharField(required=False, allow_blank=True)
    approvalStatus = serializers.ChoiceField(
        choices=[c[0] for c in RecoveryMemo.STATUS_CHOICES],
        required=False,
    )
    createDeposit = serializers.BooleanField(required=False, default=False)


class RecoveryApprovalSerializer(serializers.Serializer):
    action = serializers.ChoiceField(choices=["submit", "approve", "reject", "view"])
    approvedBy = serializers.CharField(required=False, allow_blank=True)
    rejectionReason = serializers.CharField(required=False, allow_blank=True)
    approvalRemarks = serializers.CharField(required=False, allow_blank=True)


class SeizureReportWriteSerializer(serializers.Serializer):
    detentionMemoId = serializers.UUIDField()
    assessmentId = serializers.UUIDField(required=False, allow_null=True)
    recoveryMemoId = serializers.UUIDField(required=False, allow_null=True)
    caseNo = serializers.CharField(required=False, allow_blank=True)
    reportDate = serializers.CharField(required=False, allow_blank=True)
    preparedBy = serializers.CharField(required=False, allow_blank=True)
    summary = serializers.CharField(required=False, allow_blank=True)
    recoveryAssessmentNotes = serializers.CharField(required=False, allow_blank=True)
    status = serializers.ChoiceField(
        choices=[c[0] for c in SeizureReport.STATUS_CHOICES],
        required=False,
    )


class LinkDetentionSerializer(serializers.Serializer):
    detentionMemoId = serializers.UUIDField()


def body_from_request(request) -> dict[str, Any]:
    ct = (request.content_type or "").lower()
    if "multipart/form-data" in ct:
        raw = request.data.get("payload")
        if raw is None or raw == "":
            return {}
        if isinstance(raw, dict):
            return dict(raw)
        if isinstance(raw, str):
            try:
                return json.loads(raw)
            except json.JSONDecodeError:
                return {}
        return {}
    if isinstance(request.data, dict):
        return dict(request.data)
    try:
        return dict(request.data)
    except Exception:
        return {}


_FILE_TYPE_KEYS = {
    "photo": NoteSheetAttachment.TYPE_PHOTO,
    "video": NoteSheetAttachment.TYPE_VIDEO,
    "pdf": NoteSheetAttachment.TYPE_PDF,
    "invoice": NoteSheetAttachment.TYPE_INVOICE,
    "delivery_challan": NoteSheetAttachment.TYPE_CHALLAN,
    "import_document": NoteSheetAttachment.TYPE_IMPORT,
    "cnic": NoteSheetAttachment.TYPE_CNIC,
    "other": NoteSheetAttachment.TYPE_OTHER,
}


def save_note_sheet_uploads(request, obj: NoteSheet) -> list[NoteSheetAttachment]:
    created: list[NoteSheetAttachment] = []
    files = getattr(request, "FILES", None)
    if not files:
        return created

    for key, file_type in _FILE_TYPE_KEYS.items():
        for uploaded in files.getlist(key):
            created.append(
                NoteSheetAttachment.objects.create(
                    note_sheet=obj,
                    file=uploaded,
                    file_type=file_type,
                    original_filename=getattr(uploaded, "name", "") or "",
                )
            )

    for uploaded in files.getlist("attachments"):
        name = (getattr(uploaded, "name", "") or "").lower()
        if name.endswith((".jpg", ".jpeg", ".png", ".gif", ".webp", ".bmp")):
            file_type = NoteSheetAttachment.TYPE_PHOTO
        elif name.endswith((".mp4", ".mov", ".avi", ".mkv", ".webm")):
            file_type = NoteSheetAttachment.TYPE_VIDEO
        elif name.endswith(".pdf"):
            file_type = NoteSheetAttachment.TYPE_PDF
        else:
            file_type = NoteSheetAttachment.TYPE_OTHER
        created.append(
            NoteSheetAttachment.objects.create(
                note_sheet=obj,
                file=uploaded,
                file_type=file_type,
                original_filename=getattr(uploaded, "name", "") or "",
            )
        )
    return created


def apply_note_sheet(obj: NoteSheet, data: dict, username: str = "") -> NoteSheet:
    field_map = {
        "noteSheetNo": "note_sheet_no",
        "referenceNumber": "reference_number",
        "dateTime": "date_time",
        "office": "office",
        "caseNo": "case_no",
        "priority": "priority",
        "status": "status",
        "subject": "subject",
        "preparedBy": "prepared_by",
        "badgeId": "badge_id",
        "designation": "designation",
        "department": "department",
        "officerContact": "officer_contact",
        "accusedName": "accused_name",
        "accusedFatherName": "accused_father_name",
        "accusedCnic": "accused_cnic",
        "accusedMobile": "accused_mobile",
        "accusedAddress": "accused_address",
        "businessName": "business_name",
        "ntnStrn": "ntn_strn",
        "placeOfInspection": "place_of_inspection",
        "warehouseShop": "warehouse_shop",
        "gpsLocation": "gps_location",
        "inspectionDate": "inspection_date",
        "groundsOfSuspicion": "grounds_of_suspicion",
        "preliminaryFindings": "preliminary_findings",
        "recommendation": "recommendation",
        "content": "content",
        "preparedSignature": "prepared_signature",
        "preparedDate": "prepared_date",
        "forwardTo": "forward_to",
        "approvalRemarks": "approval_remarks",
    }
    for camel, attr in field_map.items():
        if camel not in data:
            continue
        value = data.get(camel)
        if camel in ("priority", "status", "recommendation") and not value:
            continue
        setattr(obj, attr, value if value is not None else "")

    if "forwardToUserId" in data:
        raw_id = data.get("forwardToUserId")
        try:
            obj.forward_to_user_id = int(raw_id) if raw_id not in (None, "") else None
        except (TypeError, ValueError):
            obj.forward_to_user_id = None

    if "evidenceCollected" in data:
        evidence = data.get("evidenceCollected")
        obj.evidence_collected = evidence if isinstance(evidence, list) else []

    is_new = obj._state.adding
    if is_new and username:
        obj.created_by = username
    if username:
        obj.updated_by = username

    if obj.note_sheet_no and not obj.reference_number:
        obj.reference_number = obj.note_sheet_no
    elif obj.reference_number and not obj.note_sheet_no:
        obj.note_sheet_no = obj.reference_number

    obj.save()
    before_no = obj.note_sheet_no
    before_ref = obj.reference_number
    obj.ensure_note_sheet_no()
    if obj.note_sheet_no != before_no or obj.reference_number != before_ref:
        obj.save(update_fields=["note_sheet_no", "reference_number", "updated_at"])

    if "items" in data:
        items = data.get("items") or []
        keep_ids: list = []
        for idx, row in enumerate(items):
            if not isinstance(row, dict):
                continue
            description = (row.get("description") or row.get("product") or "").strip()
            estimated = (row.get("assessableValuePkr") or row.get("estimatedValue") or "").strip()
            notes = (row.get("itemNotes") or row.get("remarks") or "").strip()
            client_line_id = (row.get("clientLineId") or row.get("id") or "").strip()
            existing = _find_note_sheet_item(obj, client_line_id)
            fields = {
                "client_line_id": client_line_id,
                "qr_code_number": row.get("qrCodeNumber") or "",
                "product": description,
                "pct_code": row.get("pctCode") or "",
                "quantity": row.get("quantity") or "",
                "unit": row.get("unit") or "",
                "condition": row.get("condition") or "",
                "estimated_value": estimated,
                "perishable": bool(row.get("perishable")),
                "identification_ref": row.get("identificationRef") or "",
                "remarks": notes,
                "sort_order": row.get("sortOrder") if row.get("sortOrder") is not None else idx,
            }
            if existing:
                for attr, value in fields.items():
                    setattr(existing, attr, value)
                existing.save()
                keep_ids.append(existing.id)
            else:
                created_item = NoteSheetItem.objects.create(note_sheet=obj, **fields)
                if not created_item.client_line_id:
                    created_item.client_line_id = str(created_item.id)
                    created_item.save(update_fields=["client_line_id"])
                keep_ids.append(created_item.id)
        obj.items.exclude(id__in=keep_ids).delete()
    return obj


def save_note_sheet_goods_images(request, obj: NoteSheet, items_payload: list | None) -> None:
    """Save goods images uploaded as goods_image_{clientLineId}_{n}."""
    if not items_payload:
        return
    files = getattr(request, "FILES", None)
    if not files:
        return

    try:
        from detentions.image_utils import compress_image
    except ImportError:
        compress_image = None

    for row in items_payload:
        if not isinstance(row, dict):
            continue
        client_line_id = (row.get("clientLineId") or row.get("id") or "").strip()
        if not client_line_id:
            continue
        goods_line = _find_note_sheet_item(obj, client_line_id)
        if not goods_line:
            continue

        remaining = 10 - goods_line.images.count()
        if remaining <= 0:
            continue

        prefix = f"goods_image_{client_line_id}_"
        for key in list(files.keys()):
            if not key.startswith(prefix) or remaining <= 0:
                continue
            uploaded = files[key]
            if compress_image:
                uploaded = compress_image(uploaded, max_width=1920, max_height=1080, quality=85)
            NoteSheetItemImage.objects.create(item=goods_line, image=uploaded)
            remaining -= 1


def apply_assessment(
    obj: DetentionAssessment,
    data: dict,
    username: str = "",
) -> DetentionAssessment:
    if "assessmentDate" in data:
        obj.assessment_date = data.get("assessmentDate") or ""
    if "examiningOfficer" in data:
        obj.examining_officer = data.get("examiningOfficer") or ""
    if "goodsCondition" in data:
        obj.goods_condition = data.get("goodsCondition") or ""
    if "valuationNotes" in data:
        obj.valuation_notes = data.get("valuationNotes") or ""
    if "findings" in data:
        obj.findings = data.get("findings") or ""
    if "documentRelevance" in data and data["documentRelevance"]:
        obj.document_relevance = data["documentRelevance"]
    # Status is controlled by approval endpoint; ignore client status except on create default
    if not obj.pk and data.get("status") in dict(DetentionAssessment.STATUS_CHOICES):
        obj.status = data["status"]
    actor = (data.get("updatedBy") or data.get("createdBy") or username or "").strip()
    if actor:
        if not obj.created_by:
            obj.created_by = (data.get("createdBy") or actor).strip()
        obj.updated_by = actor
    obj.save()
    return obj


_ASSESSMENT_FILE_TYPE_KEYS = {
    "photo": DetentionAssessmentAttachment.TYPE_PHOTO,
    "video": DetentionAssessmentAttachment.TYPE_VIDEO,
    "pdf": DetentionAssessmentAttachment.TYPE_PDF,
    "invoice": DetentionAssessmentAttachment.TYPE_INVOICE,
    "delivery_challan": DetentionAssessmentAttachment.TYPE_CHALLAN,
    "import_document": DetentionAssessmentAttachment.TYPE_IMPORT,
    "cnic": DetentionAssessmentAttachment.TYPE_CNIC,
    "other": DetentionAssessmentAttachment.TYPE_OTHER,
    "documents": DetentionAssessmentAttachment.TYPE_OTHER,
    "attachments": DetentionAssessmentAttachment.TYPE_OTHER,
}


def save_assessment_uploads(request, obj: DetentionAssessment) -> list[DetentionAssessmentAttachment]:
    created: list[DetentionAssessmentAttachment] = []
    files = getattr(request, "FILES", None)
    if not files:
        return created

    try:
        from ml.image_utils import compress_image
    except Exception:
        compress_image = None

    for key, file_type in _ASSESSMENT_FILE_TYPE_KEYS.items():
        for uploaded in files.getlist(key):
            if compress_image and file_type == DetentionAssessmentAttachment.TYPE_PHOTO:
                uploaded = compress_image(uploaded, max_width=1920, max_height=1080, quality=85)
            created.append(
                DetentionAssessmentAttachment.objects.create(
                    assessment=obj,
                    file=uploaded,
                    file_type=file_type,
                    original_filename=(getattr(uploaded, "name", "") or "")[:255],
                )
            )
    return created


def apply_recovery(obj: RecoveryMemo, data: dict, username: str = "") -> RecoveryMemo:
    if "category" in data and data["category"]:
        obj.category = data["category"]
    if "recoveryDate" in data:
        obj.recovery_date = data.get("recoveryDate") or ""
    if "recoveryOfficer" in data:
        obj.recovery_officer = data.get("recoveryOfficer") or ""
    if "goodsDescription" in data:
        obj.goods_description = data.get("goodsDescription") or ""
    if "quantity" in data:
        obj.quantity = data.get("quantity") or ""
    if "remarks" in data:
        obj.remarks = data.get("remarks") or ""
    if "approvalStatus" in data and data["approvalStatus"]:
        obj.approval_status = data["approvalStatus"]
    if "assessmentId" in data:
        aid = data.get("assessmentId")
        obj.assessment_id = aid
    actor = (data.get("updatedBy") or data.get("createdBy") or username or "").strip()
    if actor:
        if not getattr(obj, "created_by", None):
            obj.created_by = (data.get("createdBy") or actor).strip()
        obj.updated_by = actor
    obj.save()
    return obj


def maybe_create_deposit_for_recovery(recovery: RecoveryMemo) -> DepositAccountEntry | None:
    if recovery.deposit_account_id:
        return recovery.deposit_account
    memo = recovery.detention_memo
    entry = create_deposit_account_entry(
        {
            "detentionMemoId": str(memo.id),
            "depositType": "Detention",
            "caseSeizureRef": memo.case_no or "",
            "firNo": "",
            "customsStation": memo.place_of_detention or "",
            "depositDate": timezone.now().date().isoformat(),
            "status": "Pending",
            "remarks": f"Auto-created from recovery memo ({recovery.category})",
        }
    )
    recovery.deposit_account = entry
    recovery.save(update_fields=["deposit_account", "updated_at"])
    return entry


def _sync_seizure_report_legacy_columns(obj: SeizureReport, data: dict | None = None) -> None:
    """Keep live-DB legacy NOT NULL columns filled (not on the Django model)."""
    from django.db import connection

    memo = getattr(obj, "detention_memo", None)
    ref = ""
    if data and data.get("caseNo"):
        ref = str(data.get("caseNo") or "")
    elif memo is not None:
        ref = (getattr(memo, "case_no", None) or getattr(memo, "reference_number", None) or "") or ""

    pk = str(obj.pk)
    updates = [
        ("reference_number", ref),
        ("executive_summary", obj.summary or ""),
        ("recovery_summary", obj.recovery_assessment_notes or ""),
        ("created_by", obj.prepared_by or ""),
    ]
    with connection.cursor() as cursor:
        for column, value in updates:
            cursor.execute(
                """
                SELECT 1 FROM information_schema.columns
                WHERE table_name = 'seizure_management_seizurereport'
                  AND column_name = %s
                """,
                [column],
            )
            if not cursor.fetchone():
                continue
            cursor.execute(
                f"""
                UPDATE seizure_management_seizurereport
                SET {column} = COALESCE(NULLIF(%s, ''), {column}, '')
                WHERE id = %s::uuid
                """,
                [value, pk],
            )


def apply_seizure_report(obj: SeizureReport, data: dict) -> SeizureReport:
    if "reportDate" in data:
        obj.report_date = data.get("reportDate") or ""
    if "preparedBy" in data:
        obj.prepared_by = data.get("preparedBy") or ""
    if "summary" in data:
        obj.summary = data.get("summary") or ""
    if "recoveryAssessmentNotes" in data:
        obj.recovery_assessment_notes = data.get("recoveryAssessmentNotes") or ""
    if "assessmentId" in data:
        obj.assessment_id = data.get("assessmentId")
    if "recoveryMemoId" in data:
        obj.recovery_memo_id = data.get("recoveryMemoId")
    if "status" in data and data["status"]:
        obj.status = data["status"]
        if obj.status == SeizureReport.STATUS_SUBMITTED and not obj.submitted_at:
            obj.submitted_at = timezone.now()
    obj.save()
    _sync_seizure_report_legacy_columns(obj, data)
    return obj


def build_recovery_assessment_sheet(
    memo: DetentionMemo,
    assessment: DetentionAssessment | None,
    recovery: RecoveryMemo | None,
) -> str:
    parts = []
    if assessment:
        parts.append(
            f"Assessment: {assessment.findings or assessment.goods_condition or '—'} "
            f"({assessment.status}; docs: {assessment.document_relevance})"
        )
        if assessment.examining_officer:
            parts.append(f"Examining officer: {assessment.examining_officer}")
    else:
        parts.append("Assessment: not recorded")
    if recovery:
        parts.append(
            f"Recovery: {recovery.category} — {recovery.goods_description or '—'} "
            f"({recovery.approval_status})"
        )
        if recovery.recovery_officer:
            parts.append(f"Recovery officer: {recovery.recovery_officer}")
    else:
        parts.append("Recovery: no memo")
    return "\n".join(parts)
