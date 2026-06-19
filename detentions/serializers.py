from typing import Optional

from rest_framework import serializers

from .models import DepositAccountEntry, DetentionMemo, DetentionMemoGoodsImage, DetentionMemoGoodsLine


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


class _PersonPayloadSerializer(serializers.Serializer):
    name = serializers.CharField(required=False, allow_blank=True)
    cnic = serializers.CharField(required=False, allow_blank=True)
    contact = serializers.CharField(required=False, allow_blank=True)
    picture = serializers.CharField(required=False, allow_blank=True, allow_null=True)


class _GoodsItemPayloadSerializer(serializers.Serializer):
    id = serializers.CharField(required=False, allow_blank=True)
    qrCodeNumber = serializers.CharField(required=False, allow_blank=True)
    description = serializers.CharField(required=False, allow_blank=True)
    pctCode = serializers.CharField(required=False, allow_blank=True)
    quantity = serializers.CharField(required=False, allow_blank=True)
    unit = serializers.CharField(required=False, allow_blank=True)
    condition = serializers.CharField(required=False, allow_blank=True)
    assessableValuePkr = serializers.CharField(required=False, allow_blank=True)
    identificationRef = serializers.CharField(required=False, allow_blank=True)
    itemNotes = serializers.CharField(required=False, allow_blank=True)
    perishable = serializers.BooleanField(required=False, default=False)
    images = serializers.ListField(
        child=serializers.CharField(required=False, allow_blank=True),
        required=False,
        default=list,
    )


class DetentionMemoWriteSerializer(serializers.Serializer):
    """Create/update body — camelCase keys aligned with the React app."""

    caseNo = serializers.CharField(required=False, allow_blank=True)
    referenceNumber = serializers.CharField(required=False, allow_blank=True)
    firNumber = serializers.CharField(required=False, allow_blank=True)

    dateTimeOccurrence = serializers.CharField(required=False, allow_blank=True)
    placeOfOccurrence = serializers.CharField(required=False, allow_blank=True)
    dateTimeDetention = serializers.CharField(required=False, allow_blank=True)
    placeOfDetention = serializers.CharField(required=False, allow_blank=True)

    detentionType = serializers.CharField(required=False, allow_blank=True)
    directorate = serializers.CharField(required=False, allow_blank=True)
    reasonForDetention = serializers.CharField(required=False, allow_blank=True)

    locationOfDetention = serializers.CharField(required=False, allow_blank=True)
    gdNumber = serializers.CharField(required=False, allow_blank=True)
    gdNumber2 = serializers.CharField(required=False, allow_blank=True)
    whereDeposited = serializers.CharField(required=False, allow_blank=True)
    searchChassisNumber = serializers.CharField(required=False, allow_blank=True)
    receiptOfficer = serializers.CharField(required=False, allow_blank=True)

    settlementStatus = serializers.CharField(required=False, allow_blank=True)
    verificationStatus = serializers.CharField(required=False, allow_blank=True)

    briefFacts = serializers.CharField(required=False, allow_blank=True)
    forwardingOfficerRemarks = serializers.CharField(required=False, allow_blank=True)
    purposeOfDetention = serializers.CharField(required=False, allow_blank=True)

    owner = _PersonPayloadSerializer(required=False)
    driver = _PersonPayloadSerializer(required=False)

    goodsItems = _GoodsItemPayloadSerializer(many=True, required=False)

    seizingOfficerNotes = serializers.CharField(required=False, allow_blank=True)
    examiningOfficerNotes = serializers.CharField(required=False, allow_blank=True)
    detentionNotes = serializers.CharField(required=False, allow_blank=True)

    memoQrCodeNumber = serializers.CharField(required=False, allow_blank=True)
    memoQrCodePayload = serializers.CharField(required=False, allow_blank=True)

    createdBy = serializers.CharField(required=False, allow_blank=True)

    # Optional: browser origin (e.g. http://localhost:5173) so memo QR points at the SPA, not the API host.
    clientOrigin = serializers.CharField(required=False, allow_blank=True)


def _goods_item_raw(item: dict) -> dict:
    """Normalize goods line dict from request JSON."""
    return {
        "id": item.get("id") or "",
        "qrCodeNumber": item.get("qrCodeNumber") or "",
        "description": item.get("description") or "",
        "pctCode": item.get("pctCode") or "",
        "quantity": item.get("quantity") or "",
        "unit": item.get("unit") or "",
        "condition": item.get("condition") or "",
        "assessableValuePkr": item.get("assessableValuePkr") or "",
        "identificationRef": item.get("identificationRef") or "",
        "itemNotes": item.get("itemNotes") or "",
        "perishable": bool(item.get("perishable")),
        "images": item.get("images") or [],
    }


def apply_validated_to_memo(memo: DetentionMemo, data: dict) -> None:
    owner = data.get("owner") or {}
    driver = data.get("driver") or {}

    memo.case_no = data.get("caseNo") or ""
    memo.reference_number = data.get("referenceNumber") or ""
    memo.fir_number = data.get("firNumber") or ""

    memo.date_time_occurrence = data.get("dateTimeOccurrence") or ""
    memo.place_of_occurrence = data.get("placeOfOccurrence") or ""
    memo.date_time_detention = data.get("dateTimeDetention") or ""
    memo.place_of_detention = data.get("placeOfDetention") or ""

    memo.detention_type = data.get("detentionType") or ""
    memo.directorate = data.get("directorate") or ""
    memo.reason_for_detention = data.get("reasonForDetention") or ""

    memo.location_of_detention = data.get("locationOfDetention") or ""
    memo.gd_number = data.get("gdNumber") or ""
    memo.gd_number_2 = data.get("gdNumber2") or ""
    memo.where_deposited = data.get("whereDeposited") or ""
    memo.search_chassis_number = data.get("searchChassisNumber") or ""
    memo.receipt_officer = data.get("receiptOfficer") or ""

    memo.settlement_status = data.get("settlementStatus") or ""
    memo.verification_status = data.get("verificationStatus") or ""
    memo.disposition_status = data.get("dispositionStatus") or memo.disposition_status or ""

    memo.brief_facts = data.get("briefFacts") or ""
    memo.forwarding_officer_remarks = data.get("forwardingOfficerRemarks") or ""
    memo.purpose_of_detention = data.get("purposeOfDetention") or ""

    memo.owner_name = owner.get("name") or ""
    memo.owner_cnic = owner.get("cnic") or ""
    memo.owner_contact = owner.get("contact") or ""
    memo.owner_picture = owner.get("picture") or ""

    memo.driver_name = driver.get("name") or ""
    memo.driver_cnic = driver.get("cnic") or ""
    memo.driver_contact = driver.get("contact") or ""
    memo.driver_picture = driver.get("picture") or ""

    memo.seizing_officer_notes = data.get("seizingOfficerNotes") or ""
    memo.examining_officer_notes = data.get("examiningOfficerNotes") or ""
    memo.detention_notes = data.get("detentionNotes") or ""

    memo.memo_qr_code_number = data.get("memoQrCodeNumber") or ""
    memo.memo_qr_code_payload = data.get("memoQrCodePayload") or ""

    memo.created_by = data.get("createdBy") or memo.created_by or ""


def replace_goods_lines(memo: DetentionMemo, goods_items: Optional[list]) -> None:
    memo.goods_lines.all().delete()
    if not goods_items:
        return
    bulk = []
    for raw in goods_items:
        item = _goods_item_raw(raw if isinstance(raw, dict) else {})
        bulk.append(
            DetentionMemoGoodsLine(
                memo=memo,
                client_line_id=item["id"],
                qr_code_number=item["qrCodeNumber"],
                description=item["description"],
                pct_code=item["pctCode"],
                quantity=item["quantity"],
                unit=item["unit"],
                condition=item["condition"],
                assessable_value_pkr=item["assessableValuePkr"],
                identification_ref=item["identificationRef"],
                item_notes=item["itemNotes"],
                perishable=item["perishable"],
            )
        )
    DetentionMemoGoodsLine.objects.bulk_create(bulk)


def memo_to_frontend_dict(memo: DetentionMemo, request=None) -> dict:
    """Serialize ORM memo to the shape expected by the React app (camelCase)."""

    def _picture_out(upload_field_name: str, text_field_name: str) -> str:
        upload = getattr(memo, upload_field_name)
        if upload and getattr(upload, "name", None):
            u = _absolute_media_url(request, upload)
            if u:
                return u
        return (getattr(memo, text_field_name) or "") or ""

    goods_items = []
    for gl in memo.goods_lines.all():
        goods_images = []
        for img in gl.images.all():
            url = _absolute_media_url(request, img.image)
            if url:
                goods_images.append(url)
        goods_items.append(
            {
                "id": gl.client_line_id or str(gl.pk),
                "qrCodeNumber": gl.qr_code_number,
                "description": gl.description,
                "pctCode": gl.pct_code,
                "quantity": gl.quantity,
                "unit": gl.unit,
                "condition": gl.condition,
                "assessableValuePkr": gl.assessable_value_pkr,
                "identificationRef": gl.identification_ref,
                "itemNotes": gl.item_notes,
                "perishable": gl.perishable,
                "images": goods_images,
            }
        )

    created = memo.created_at
    updated = memo.updated_at
    created_str = created.date().isoformat() if created else ""
    updated_str = updated.date().isoformat() if updated else ""

    media_attachments = []
    qs_att = []
    pref = getattr(memo, "_prefetched_objects_cache", None)
    if pref and "attachments" in pref:
        qs_att = list(pref["attachments"])
    else:
        qs_att = list(memo.attachments.all())

    for att in qs_att:
        url = _absolute_media_url(request, att.file)
        media_attachments.append(
            {
                "id": str(att.pk),
                "kind": att.kind,
                "url": url,
                "originalFilename": att.original_filename or "",
            }
        )

    return {
        "id": str(memo.pk),
        "caseNo": memo.case_no,
        "referenceNumber": memo.reference_number,
        "firNumber": memo.fir_number,
        "dateTimeOccurrence": memo.date_time_occurrence,
        "placeOfOccurrence": memo.place_of_occurrence,
        "dateTimeDetention": memo.date_time_detention,
        "placeOfDetention": memo.place_of_detention,
        "detentionType": memo.detention_type,
        "directorate": memo.directorate,
        "reasonForDetention": memo.reason_for_detention,
        "locationOfDetention": memo.location_of_detention,
        "gdNumber": memo.gd_number,
        "gdNumber2": memo.gd_number_2,
        "whereDeposited": memo.where_deposited,
        "searchChassisNumber": memo.search_chassis_number,
        "receiptOfficer": memo.receipt_officer,
        "settlementStatus": memo.settlement_status,
        "verificationStatus": memo.verification_status,
        "dispositionStatus": memo.disposition_status,
        "briefFacts": memo.brief_facts,
        "forwardingOfficerRemarks": memo.forwarding_officer_remarks,
        "purposeOfDetention": memo.purpose_of_detention,
        "owner": {
            "name": memo.owner_name,
            "cnic": memo.owner_cnic,
            "contact": memo.owner_contact,
            "picture": _picture_out("owner_photo_upload", "owner_picture"),
        },
        "driver": {
            "name": memo.driver_name,
            "cnic": memo.driver_cnic,
            "contact": memo.driver_contact,
            "picture": _picture_out("driver_photo_upload", "driver_picture"),
        },
        "goodsItems": goods_items,
        "seizingOfficerNotes": memo.seizing_officer_notes,
        "examiningOfficerNotes": memo.examining_officer_notes,
        "detentionNotes": memo.detention_notes,
        "memoQrCodeNumber": memo.memo_qr_code_number,
        "memoQrCodePayload": memo.memo_qr_code_payload,
        "createdBy": memo.created_by,
        "createdAt": created_str,
        "updatedAt": updated_str,
        "mediaAttachments": media_attachments,
    }


# ---------- Deposit Account Register ----------


class DepositAccountWriteSerializer(serializers.Serializer):
    detentionMemoId = serializers.CharField(required=False, allow_blank=True, max_length=36)
    treasuryChallanNo = serializers.CharField(required=False, allow_blank=True)
    depositType = serializers.CharField(required=False, allow_blank=True)
    caseSeizureRef = serializers.CharField(required=False, allow_blank=True)
    firNo = serializers.CharField(required=False, allow_blank=True)
    customsStation = serializers.CharField(required=False, allow_blank=True)
    amount = serializers.CharField(required=False, allow_blank=True)
    depositDate = serializers.CharField(required=False, allow_blank=True)
    bankTreasuryName = serializers.CharField(required=False, allow_blank=True)
    status = serializers.CharField(required=False, allow_blank=True)
    remarks = serializers.CharField(required=False, allow_blank=True)


def apply_partial_to_deposit_entry(entry: DepositAccountEntry, data: dict) -> None:
    """Update deposit row from PATCH body (camelCase keys). Only keys present in `data` are applied."""

    def _present(key: str) -> bool:
        return key in data

    if _present("detentionMemoId"):
        raw = (data.get("detentionMemoId") or "").strip()
        entry.detention_memo = DetentionMemo.objects.filter(pk=raw).first() if raw else None
    if _present("treasuryChallanNo"):
        entry.treasury_challan_no = (data.get("treasuryChallanNo") or "")[:120]
    if _present("depositType"):
        entry.deposit_type = (data.get("depositType") or "")[:80]
    if _present("caseSeizureRef"):
        entry.case_seizure_ref = (data.get("caseSeizureRef") or "")[:200]
    if _present("firNo"):
        entry.fir_no = (data.get("firNo") or "")[:120]
    if _present("customsStation"):
        entry.customs_station = (data.get("customsStation") or "")[:200]
    if _present("amount"):
        entry.amount = (data.get("amount") or "")[:120]
    if _present("depositDate"):
        entry.deposit_date = (data.get("depositDate") or "")[:40]
    if _present("bankTreasuryName"):
        entry.bank_treasury_name = (data.get("bankTreasuryName") or "")[:255]
    if _present("status"):
        entry.status = (data.get("status") or "")[:80]
    if _present("remarks"):
        entry.remarks = data.get("remarks") or ""


def create_deposit_account_entry(validated_data: dict) -> DepositAccountEntry:
    memo = None
    raw_id = (validated_data.get("detentionMemoId") or "").strip()
    if raw_id:
        memo = DetentionMemo.objects.filter(pk=raw_id).first()

    return DepositAccountEntry.objects.create(
        detention_memo=memo,
        treasury_challan_no=(validated_data.get("treasuryChallanNo") or "")[:120],
        deposit_type=(validated_data.get("depositType") or "")[:80],
        case_seizure_ref=(validated_data.get("caseSeizureRef") or "")[:200],
        fir_no=(validated_data.get("firNo") or "")[:120],
        customs_station=(validated_data.get("customsStation") or "")[:200],
        amount=(validated_data.get("amount") or "")[:120],
        deposit_date=(validated_data.get("depositDate") or "")[:40],
        bank_treasury_name=(validated_data.get("bankTreasuryName") or "")[:255],
        status=(validated_data.get("status") or "")[:80],
        remarks=validated_data.get("remarks") or "",
    )


def deposit_entry_to_frontend_dict(entry: DepositAccountEntry) -> dict:
    dd = entry.deposit_date or ""
    memo = getattr(entry, "detention_memo", None)
    linked_case = memo.case_no if memo else ""
    created = entry.created_at
    updated = entry.updated_at
    return {
        "id": str(entry.pk),
        "detentionMemoId": str(entry.detention_memo_id) if entry.detention_memo_id else "",
        "linkedMemoCaseNo": linked_case,
        "treasuryChallanNo": entry.treasury_challan_no,
        "depositType": entry.deposit_type,
        "caseSeizureRef": entry.case_seizure_ref,
        "firNo": entry.fir_no,
        "customsStation": entry.customs_station,
        "amount": entry.amount,
        "depositDate": dd,
        "bankTreasuryName": entry.bank_treasury_name,
        "status": entry.status,
        "remarks": entry.remarks,
        "createdAt": created.isoformat() if created else "",
        "updatedAt": updated.isoformat() if updated else "",
    }
