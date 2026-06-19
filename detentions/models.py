import os
import re
import uuid

from django.db import models


def _sanitize_filename(filename: str) -> str:
    base = os.path.basename(filename)
    return re.sub(r"[^\w.\-]", "_", base)[:180]


def detention_owner_photo_path(instance: "DetentionMemo", filename: str) -> str:
    sid = instance.pk or "new"
    ext = os.path.splitext(filename)[1].lower()
    return f"detention_memos/{sid}/owner_photo{ext or '.jpg'}"


def detention_driver_photo_path(instance: "DetentionMemo", filename: str) -> str:
    sid = instance.pk or "new"
    ext = os.path.splitext(filename)[1].lower()
    return f"detention_memos/{sid}/driver_photo{ext or '.jpg'}"


def detention_attachment_path(instance, filename: str) -> str:
    safe = _sanitize_filename(filename)
    return f"detention_memos/{instance.memo_id}/{instance.kind}s/{uuid.uuid4().hex}_{safe}"


def detention_goods_image_path(instance: "DetentionMemoGoodsImage", filename: str) -> str:
    goods_line = instance.goods_line
    memo_id = goods_line.memo_id
    goods_id = goods_line.pk or "new"
    ext = os.path.splitext(filename)[1].lower()
    return f"detention_memos/{memo_id}/goods/{goods_id}/{uuid.uuid4().hex}{ext or '.jpg'}"


class DetentionMemo(models.Model):
    """Pakistan Customs detention memo — header and narrative fields."""

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)

    case_no = models.CharField(max_length=120, blank=True, db_index=True)
    reference_number = models.CharField(max_length=200, blank=True)
    fir_number = models.CharField(max_length=120, blank=True)

    date_time_occurrence = models.CharField(max_length=80, blank=True)
    place_of_occurrence = models.CharField(max_length=300, blank=True)
    date_time_detention = models.CharField(max_length=80, blank=True)
    place_of_detention = models.CharField(max_length=300, blank=True)

    detention_type = models.CharField(max_length=80, blank=True)
    directorate = models.CharField(max_length=200, blank=True)
    reason_for_detention = models.CharField(max_length=200, blank=True)

    location_of_detention = models.CharField(max_length=300, blank=True)
    gd_number = models.CharField(max_length=120, blank=True)
    gd_number_2 = models.CharField(max_length=120, blank=True)
    where_deposited = models.CharField(max_length=400, blank=True)
    search_chassis_number = models.CharField(max_length=120, blank=True)
    receipt_officer = models.CharField(max_length=200, blank=True)

    settlement_status = models.CharField(max_length=80, blank=True)
    verification_status = models.CharField(max_length=80, blank=True)
    disposition_status = models.CharField(
        max_length=80,
        blank=True,
        default="",
        help_text="e.g. In Warehouse, Destructed, Released",
    )

    brief_facts = models.TextField(blank=True)
    forwarding_officer_remarks = models.TextField(blank=True)
    purpose_of_detention = models.TextField(blank=True)

    owner_name = models.CharField(max_length=200, blank=True)
    owner_cnic = models.CharField(max_length=30, blank=True)
    owner_contact = models.CharField(max_length=50, blank=True)
    # Legacy/base64 fallback (prefer owner_photo_upload for large binaries)
    owner_picture = models.TextField(blank=True)
    owner_photo_upload = models.FileField(
        upload_to=detention_owner_photo_path, blank=True, null=True,
    )

    driver_name = models.CharField(max_length=200, blank=True)
    driver_cnic = models.CharField(max_length=30, blank=True)
    driver_contact = models.CharField(max_length=50, blank=True)
    driver_picture = models.TextField(blank=True)
    driver_photo_upload = models.FileField(
        upload_to=detention_driver_photo_path, blank=True, null=True,
    )

    seizing_officer_notes = models.TextField(blank=True)
    examining_officer_notes = models.TextField(blank=True)
    detention_notes = models.TextField(blank=True)

    memo_qr_code_number = models.CharField(max_length=160, blank=True)
    memo_qr_code_payload = models.TextField(blank=True)

    created_by = models.CharField(max_length=150, blank=True)

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["-created_at"]

    def __str__(self):
        return self.case_no or str(self.pk)


class DetentionMemoGoodsLine(models.Model):
    """Goods line items for a detention memo (each may have its own QR reference)."""

    memo = models.ForeignKey(
        DetentionMemo,
        on_delete=models.CASCADE,
        related_name="goods_lines",
    )
    client_line_id = models.CharField(max_length=80, blank=True)
    qr_code_number = models.CharField(max_length=160, blank=True)
    description = models.TextField(blank=True)
    pct_code = models.CharField(max_length=40, blank=True)
    quantity = models.CharField(max_length=40, blank=True)
    unit = models.CharField(max_length=40, blank=True)
    condition = models.CharField(max_length=80, blank=True)
    assessable_value_pkr = models.CharField(max_length=40, blank=True)
    identification_ref = models.CharField(max_length=200, blank=True)
    item_notes = models.TextField(blank=True)
    perishable = models.BooleanField(default=False)

    class Meta:
        ordering = ["id"]

    def __str__(self):
        return f"{self.memo_id} — {self.description[:40] if self.description else self.pk}"


class DetentionMemoGoodsImage(models.Model):
    """Images for goods line items (up to 10 per goods line)."""

    goods_line = models.ForeignKey(
        DetentionMemoGoodsLine,
        on_delete=models.CASCADE,
        related_name="images",
    )
    image = models.FileField(upload_to=detention_goods_image_path)
    uploaded_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["uploaded_at"]

    def __str__(self):
        return f"Goods image {self.pk} for {self.goods_line_id}"


class DetentionMemoAttachment(models.Model):
    KIND_DOCUMENT = "document"
    KIND_VIDEO = "video"
    KIND_CHOICES = [
        (KIND_DOCUMENT, "Document"),
        (KIND_VIDEO, "Video"),
    ]

    memo = models.ForeignKey(
        DetentionMemo,
        on_delete=models.CASCADE,
        related_name="attachments",
    )
    kind = models.CharField(max_length=20, choices=KIND_CHOICES)
    file = models.FileField(upload_to=detention_attachment_path)
    original_filename = models.CharField(max_length=255, blank=True)
    uploaded_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["uploaded_at", "id"]

    def __str__(self):
        return f"{self.memo_id} [{self.kind}] {self.original_filename or self.pk}"


class DepositAccountEntry(models.Model):
    """
    Treasury / deposit lines (bail, security, duty, detention, etc.).
    Detention Memo "Deposit" creates a row linked via detention_memo.
    """

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    detention_memo = models.ForeignKey(
        DetentionMemo,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="deposit_entries",
    )

    treasury_challan_no = models.CharField(max_length=120, blank=True)
    deposit_type = models.CharField(max_length=80, blank=True)
    case_seizure_ref = models.CharField(max_length=200, blank=True)
    fir_no = models.CharField(max_length=120, blank=True)
    customs_station = models.CharField(max_length=200, blank=True)
    amount = models.CharField(max_length=120, blank=True)
    deposit_date = models.CharField(max_length=40, blank=True)
    bank_treasury_name = models.CharField(max_length=255, blank=True)
    status = models.CharField(max_length=80, blank=True)
    remarks = models.TextField(blank=True)

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["-created_at"]

    def __str__(self):
        return self.treasury_challan_no or self.case_seizure_ref or str(self.pk)
