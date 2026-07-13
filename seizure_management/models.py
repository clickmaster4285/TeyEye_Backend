import os
import re
import uuid

from django.db import models


def _sanitize_filename(filename: str) -> str:
    """Keep a short, storage-safe basename (FileField default max_length is 100)."""
    base = os.path.basename((filename or "file").replace("\\", "/"))
    name, ext = os.path.splitext(base)
    safe_name = re.sub(r"[^\w.\-]", "_", name).strip("._")[:40] or "file"
    safe_ext = re.sub(r"[^\w.]", "", ext).lower()[:10]
    if safe_ext and not safe_ext.startswith("."):
        safe_ext = f".{safe_ext}"
    return f"{safe_name}{safe_ext}"


def note_sheet_attachment_path(instance, filename: str) -> str:
    safe = _sanitize_filename(filename)
    # Short path: avoid Windows long-path / DB max_length issues
    return f"note_sheets/{instance.note_sheet_id}/{instance.file_type}/{uuid.uuid4().hex}_{safe}"


def note_sheet_item_image_path(instance, filename: str) -> str:
    ext = os.path.splitext(os.path.basename((filename or "").replace("\\", "/")))[1].lower()
    ext = re.sub(r"[^\w.]", "", ext)[:10]
    if not ext.startswith("."):
        ext = f".{ext}" if ext else ".jpg"
    # Flat under goods/ — item id already unique; keeps stored path under max_length
    return f"note_sheets/{instance.item.note_sheet_id}/goods/{uuid.uuid4().hex}{ext}"


def assessment_attachment_path(instance, filename: str) -> str:
    ext = os.path.splitext(os.path.basename((filename or "").replace("\\", "/")))[1].lower()
    ext = re.sub(r"[^\w.]", "", ext)[:10]
    if not ext.startswith("."):
        ext = f".{ext}" if ext else ".bin"
    kind = getattr(instance, "file_type", "other") or "other"
    return f"assessments/{instance.assessment_id}/{kind}/{uuid.uuid4().hex}{ext}"


class NoteSheet(models.Model):
    """Pre-detention note sheet — first legal document; must be approved before detention memo."""

    STATUS_DRAFT = "Draft"
    STATUS_SUBMITTED = "Submitted"
    STATUS_APPROVED = "Approved"
    STATUS_REJECTED = "Rejected"
    STATUS_CHOICES = [
        (STATUS_DRAFT, "Draft"),
        (STATUS_SUBMITTED, "Submitted"),
        (STATUS_APPROVED, "Approved"),
        (STATUS_REJECTED, "Rejected"),
    ]

    PRIORITY_NORMAL = "Normal"
    PRIORITY_URGENT = "Urgent"
    PRIORITY_CHOICES = [
        (PRIORITY_NORMAL, "Normal"),
        (PRIORITY_URGENT, "Urgent"),
    ]

    RECOMMENDATION_NO_ACTION = "No Action"
    RECOMMENDATION_WARNING = "Warning"
    RECOMMENDATION_FURTHER = "Further Investigation"
    RECOMMENDATION_DETENTION = "Issue Detention Memo"
    RECOMMENDATION_RELEASE = "Release Goods"
    RECOMMENDATION_CHOICES = [
        (RECOMMENDATION_NO_ACTION, "No Action"),
        (RECOMMENDATION_WARNING, "Warning"),
        (RECOMMENDATION_FURTHER, "Further Investigation"),
        (RECOMMENDATION_DETENTION, "Issue Detention Memo"),
        (RECOMMENDATION_RELEASE, "Release Goods"),
    ]

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)

    # 1. Basic Information
    note_sheet_no = models.CharField(max_length=80, blank=True, db_index=True)
    date_time = models.CharField(max_length=80, blank=True)
    office = models.CharField(max_length=500, blank=True)
    case_no = models.CharField(max_length=120, blank=True, db_index=True)
    priority = models.CharField(max_length=20, choices=PRIORITY_CHOICES, default=PRIORITY_NORMAL)
    status = models.CharField(max_length=40, choices=STATUS_CHOICES, default=STATUS_DRAFT, db_index=True)
    subject = models.CharField(max_length=400, blank=True)

    # Legacy alias fields kept in sync for older clients
    reference_number = models.CharField(max_length=200, blank=True, db_index=True)

    # 2. Officer Information
    prepared_by = models.CharField(max_length=500, blank=True)
    badge_id = models.CharField(max_length=80, blank=True)
    designation = models.CharField(max_length=200, blank=True)
    department = models.CharField(max_length=500, blank=True)
    officer_contact = models.CharField(max_length=80, blank=True)

    # 3. Suspect / Accused
    accused_name = models.CharField(max_length=500, blank=True)
    accused_father_name = models.CharField(max_length=500, blank=True)
    accused_cnic = models.CharField(max_length=40, blank=True)
    accused_mobile = models.CharField(max_length=50, blank=True)
    accused_address = models.TextField(blank=True)
    business_name = models.CharField(max_length=500, blank=True)
    ntn_strn = models.CharField(max_length=80, blank=True)

    # 5. Location
    place_of_inspection = models.CharField(max_length=500, blank=True)
    warehouse_shop = models.CharField(max_length=500, blank=True)
    gps_location = models.CharField(max_length=120, blank=True)
    inspection_date = models.CharField(max_length=80, blank=True)

    # 6–9 Narrative
    grounds_of_suspicion = models.TextField(blank=True)
    evidence_collected = models.JSONField(default=list, blank=True)
    preliminary_findings = models.TextField(blank=True)
    recommendation = models.CharField(
        max_length=60,
        choices=RECOMMENDATION_CHOICES,
        default=RECOMMENDATION_DETENTION,
        blank=True,
    )

    # Legacy free-text body (optional extra notes)
    content = models.TextField(blank=True)

    # 11–12 Approval
    prepared_signature = models.CharField(max_length=500, blank=True)
    prepared_date = models.CharField(max_length=80, blank=True)
    forward_to = models.CharField(max_length=500, blank=True)
    forward_to_user_id = models.IntegerField(null=True, blank=True, db_index=True)
    approved_by = models.CharField(max_length=500, blank=True)
    approved_at = models.DateTimeField(null=True, blank=True)
    approval_remarks = models.TextField(blank=True)
    rejection_reason = models.TextField(blank=True)

    submitted_at = models.DateTimeField(null=True, blank=True)
    viewed_at = models.DateTimeField(null=True, blank=True)

    # Audit
    created_by = models.CharField(max_length=150, blank=True)
    updated_by = models.CharField(max_length=150, blank=True)

    detention_memo = models.OneToOneField(
        "detentions.DetentionMemo",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="note_sheet",
    )

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["-created_at"]

    def __str__(self):
        return self.note_sheet_no or self.reference_number or self.subject or str(self.pk)

    def ensure_note_sheet_no(self):
        if self.note_sheet_no:
            return
        # NS-YYYY-XXXX style using short uuid fragment
        year = (self.created_at.year if self.created_at else None) or __import__("datetime").datetime.now().year
        self.note_sheet_no = f"NS-{year}-{str(self.pk).replace('-', '')[:8].upper()}"
        if not self.reference_number:
            self.reference_number = self.note_sheet_no


class NoteSheetItem(models.Model):
    """Goods lines on a note sheet (aligned with detention memo goods columns)."""

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    note_sheet = models.ForeignKey(NoteSheet, on_delete=models.CASCADE, related_name="items")
    client_line_id = models.CharField(max_length=80, blank=True, db_index=True)
    qr_code_number = models.CharField(max_length=160, blank=True)
    product = models.CharField(max_length=300, blank=True)  # Description of Goods
    pct_code = models.CharField(max_length=40, blank=True)
    quantity = models.CharField(max_length=80, blank=True)
    unit = models.CharField(max_length=80, blank=True)
    condition = models.CharField(max_length=80, blank=True)
    estimated_value = models.CharField(max_length=120, blank=True)  # Assessable Value (PKR)
    perishable = models.BooleanField(default=False)
    identification_ref = models.CharField(max_length=500, blank=True)  # ID / Chassis No.
    remarks = models.CharField(max_length=400, blank=True)  # Item Notes
    sort_order = models.PositiveIntegerField(default=0)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["sort_order", "created_at"]

    def __str__(self):
        return self.product or str(self.pk)


class NoteSheetItemImage(models.Model):
    """Images for a note sheet goods line (up to 10 per line)."""

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    item = models.ForeignKey(NoteSheetItem, on_delete=models.CASCADE, related_name="images")
    image = models.FileField(upload_to=note_sheet_item_image_path, max_length=500)
    uploaded_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["uploaded_at"]

    def __str__(self):
        return f"Note sheet goods image {self.pk}"


class NoteSheetAttachment(models.Model):
    """Uploaded evidence/documents for a note sheet."""

    TYPE_PHOTO = "photo"
    TYPE_VIDEO = "video"
    TYPE_PDF = "pdf"
    TYPE_INVOICE = "invoice"
    TYPE_CHALLAN = "delivery_challan"
    TYPE_IMPORT = "import_document"
    TYPE_CNIC = "cnic"
    TYPE_OTHER = "other"
    TYPE_CHOICES = [
        (TYPE_PHOTO, "Photo"),
        (TYPE_VIDEO, "Video"),
        (TYPE_PDF, "PDF"),
        (TYPE_INVOICE, "Invoice"),
        (TYPE_CHALLAN, "Delivery Challan"),
        (TYPE_IMPORT, "Import Document"),
        (TYPE_CNIC, "CNIC"),
        (TYPE_OTHER, "Other"),
    ]

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    note_sheet = models.ForeignKey(NoteSheet, on_delete=models.CASCADE, related_name="attachments")
    file = models.FileField(upload_to=note_sheet_attachment_path, max_length=500)
    file_type = models.CharField(max_length=40, choices=TYPE_CHOICES, default=TYPE_OTHER)
    original_filename = models.CharField(max_length=255, blank=True)
    uploaded_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["uploaded_at"]

    def __str__(self):
        return self.original_filename or str(self.pk)


class NoteSheetNotification(models.Model):
    """In-app notification for note sheet approval requests."""

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    recipient_user_id = models.IntegerField(db_index=True)
    note_sheet = models.ForeignKey(
        NoteSheet,
        on_delete=models.CASCADE,
        related_name="notifications",
    )
    title = models.CharField(max_length=255)
    message = models.TextField(blank=True)
    is_read = models.BooleanField(default=False, db_index=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-created_at"]
        indexes = [
            models.Index(fields=["recipient_user_id", "is_read", "-created_at"]),
        ]

    def __str__(self):
        return f"{self.title} → user {self.recipient_user_id}"


class DetentionAssessment(models.Model):
    """Examination of detained goods/documents; approval workflow mirrors note sheet."""

    STATUS_DRAFT = "Draft"
    STATUS_SUBMITTED = "Submitted"
    STATUS_APPROVED = "Approved"
    STATUS_REJECTED = "Rejected"
    # Legacy aliases (migrated rows / older clients)
    STATUS_IN_PROGRESS = "In Progress"
    STATUS_COMPLETED = "Completed"
    STATUS_CHOICES = [
        (STATUS_DRAFT, "Draft"),
        (STATUS_SUBMITTED, "Submitted"),
        (STATUS_APPROVED, "Approved"),
        (STATUS_REJECTED, "Rejected"),
    ]

    RELEVANCE_PENDING = "Pending"
    RELEVANCE_RELEVANT = "Relevant"
    RELEVANCE_NOT_RELEVANT = "Not Relevant"
    RELEVANCE_CHOICES = [
        (RELEVANCE_PENDING, "Pending"),
        (RELEVANCE_RELEVANT, "Relevant"),
        (RELEVANCE_NOT_RELEVANT, "Not Relevant"),
    ]

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    detention_memo = models.ForeignKey(
        "detentions.DetentionMemo",
        on_delete=models.CASCADE,
        related_name="assessments",
    )
    assessment_date = models.CharField(max_length=40, blank=True)
    examining_officer = models.CharField(max_length=200, blank=True)
    goods_condition = models.CharField(max_length=400, blank=True)
    valuation_notes = models.TextField(blank=True)
    findings = models.TextField(blank=True)
    document_relevance = models.CharField(
        max_length=40,
        choices=RELEVANCE_CHOICES,
        default=RELEVANCE_PENDING,
        db_index=True,
    )
    status = models.CharField(max_length=40, choices=STATUS_CHOICES, default=STATUS_DRAFT, db_index=True)

    # Approval (same pattern as note sheet)
    approved_by = models.CharField(max_length=500, blank=True)
    approved_at = models.DateTimeField(null=True, blank=True)
    approval_remarks = models.TextField(blank=True)
    rejection_reason = models.TextField(blank=True)
    submitted_at = models.DateTimeField(null=True, blank=True)
    viewed_at = models.DateTimeField(null=True, blank=True)

    created_by = models.CharField(max_length=150, blank=True)
    updated_by = models.CharField(max_length=150, blank=True)

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["-created_at"]

    def __str__(self):
        return f"Assessment {self.detention_memo_id}"


class DetentionAssessmentAttachment(models.Model):
    """Supporting documents uploaded with an assessment."""

    TYPE_PHOTO = "photo"
    TYPE_VIDEO = "video"
    TYPE_PDF = "pdf"
    TYPE_INVOICE = "invoice"
    TYPE_CHALLAN = "delivery_challan"
    TYPE_IMPORT = "import_document"
    TYPE_CNIC = "cnic"
    TYPE_OTHER = "other"
    TYPE_CHOICES = [
        (TYPE_PHOTO, "Photo"),
        (TYPE_VIDEO, "Video"),
        (TYPE_PDF, "PDF"),
        (TYPE_INVOICE, "Invoice"),
        (TYPE_CHALLAN, "Delivery Challan"),
        (TYPE_IMPORT, "Import Document"),
        (TYPE_CNIC, "CNIC"),
        (TYPE_OTHER, "Other"),
    ]

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    assessment = models.ForeignKey(
        DetentionAssessment,
        on_delete=models.CASCADE,
        related_name="attachments",
    )
    file = models.FileField(upload_to=assessment_attachment_path, max_length=500)
    file_type = models.CharField(max_length=40, choices=TYPE_CHOICES, default=TYPE_OTHER)
    original_filename = models.CharField(max_length=255, blank=True)
    uploaded_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["uploaded_at"]

    def __str__(self):
        return self.original_filename or str(self.pk)


class AssessmentNotification(models.Model):
    """In-app notification for assessment approval requests."""

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    recipient_user_id = models.IntegerField(db_index=True)
    assessment = models.ForeignKey(
        DetentionAssessment,
        on_delete=models.CASCADE,
        related_name="notifications",
    )
    title = models.CharField(max_length=255)
    message = models.TextField(blank=True)
    is_read = models.BooleanField(default=False, db_index=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-created_at"]
        indexes = [
            models.Index(fields=["recipient_user_id", "is_read", "-created_at"]),
        ]

    def __str__(self):
        return f"{self.title} → user {self.recipient_user_id}"


class RecoveryMemo(models.Model):
    """Recovery memo created when assessment finds documents not relevant; sent for approval."""

    CATEGORY_DANGEROUS = "Dangerous/Chemical"
    CATEGORY_PERISHABLE = "Perishable"
    CATEGORY_OTHER = "Other"
    CATEGORY_CHOICES = [
        (CATEGORY_DANGEROUS, "Dangerous/Chemical"),
        (CATEGORY_PERISHABLE, "Perishable"),
        (CATEGORY_OTHER, "Other"),
    ]

    STATUS_DRAFT = "Draft"
    STATUS_PENDING = "Pending Approval"
    STATUS_APPROVED = "Approved"
    STATUS_REJECTED = "Rejected"
    STATUS_CHOICES = [
        (STATUS_DRAFT, "Draft"),
        (STATUS_PENDING, "Pending Approval"),
        (STATUS_APPROVED, "Approved"),
        (STATUS_REJECTED, "Rejected"),
    ]

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    detention_memo = models.ForeignKey(
        "detentions.DetentionMemo",
        on_delete=models.CASCADE,
        related_name="recovery_memos",
    )
    assessment = models.ForeignKey(
        DetentionAssessment,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="recovery_memos",
    )
    category = models.CharField(max_length=40, choices=CATEGORY_CHOICES, default=CATEGORY_OTHER)
    recovery_date = models.CharField(max_length=40, blank=True)
    recovery_officer = models.CharField(max_length=200, blank=True)
    goods_description = models.TextField(blank=True)
    quantity = models.CharField(max_length=120, blank=True)
    remarks = models.TextField(blank=True)
    approval_status = models.CharField(
        max_length=40,
        choices=STATUS_CHOICES,
        default=STATUS_DRAFT,
        db_index=True,
    )
    approved_by = models.CharField(max_length=200, blank=True)
    approved_at = models.DateTimeField(null=True, blank=True)
    rejection_reason = models.TextField(blank=True)
    approval_remarks = models.TextField(blank=True)
    submitted_at = models.DateTimeField(null=True, blank=True)
    viewed_at = models.DateTimeField(null=True, blank=True)

    deposit_account = models.ForeignKey(
        "detentions.DepositAccountEntry",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="recovery_memos",
    )

    created_by = models.CharField(max_length=150, blank=True)
    updated_by = models.CharField(max_length=150, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["-created_at"]

    def __str__(self):
        return f"Recovery {self.detention_memo_id} ({self.category})"


class RecoveryNotification(models.Model):
    """In-app notification for recovery memo approval requests (same roles as note sheet)."""

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    recipient_user_id = models.IntegerField(db_index=True)
    recovery_memo = models.ForeignKey(
        RecoveryMemo,
        on_delete=models.CASCADE,
        related_name="notifications",
    )
    title = models.CharField(max_length=255)
    message = models.TextField(blank=True)
    is_read = models.BooleanField(default=False, db_index=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-created_at"]
        indexes = [
            models.Index(fields=["recipient_user_id", "is_read", "-created_at"]),
        ]

    def __str__(self):
        return f"{self.title} → user {self.recipient_user_id}"


class SeizureReport(models.Model):
    """Final seizure report built from Recovery Memo + Assessment sheet."""

    STATUS_DRAFT = "Draft"
    STATUS_SUBMITTED = "Submitted"
    STATUS_CHOICES = [
        (STATUS_DRAFT, "Draft"),
        (STATUS_SUBMITTED, "Submitted"),
    ]

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    detention_memo = models.ForeignKey(
        "detentions.DetentionMemo",
        on_delete=models.CASCADE,
        related_name="seizure_reports",
    )
    assessment = models.ForeignKey(
        DetentionAssessment,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="seizure_reports",
    )
    recovery_memo = models.ForeignKey(
        RecoveryMemo,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="seizure_reports",
    )
    report_date = models.CharField(max_length=40, blank=True)
    prepared_by = models.CharField(max_length=200, blank=True)
    summary = models.TextField(blank=True)
    recovery_assessment_notes = models.TextField(blank=True)
    status = models.CharField(max_length=40, choices=STATUS_CHOICES, default=STATUS_DRAFT)
    submitted_at = models.DateTimeField(null=True, blank=True)

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["-created_at"]

    def __str__(self):
        return f"Seizure Report {self.detention_memo_id}"
