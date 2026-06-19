import os
import uuid

from django.db import models
from django.utils import timezone


class Warehouse(models.Model):
    """Master warehouse record."""
    STATUS_CHOICES = [
        ("ACTIVE", "Active"),
        ("MAINTENANCE", "Maintenance"),
        ("INACTIVE", "Inactive"),
    ]

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    location_code = models.CharField(
        max_length=50,
        help_text="e.g., PESHAWAR, DI_KHAN (should match User.location)"
    )
    code = models.CharField(
        max_length=50,
        unique=True,
        help_text="e.g., WH-DIK-RETTA"
    )
    name = models.CharField(max_length=255, help_text="e.g., New Warehouse, Retta Kulachi")
    status = models.CharField(
        max_length=20,
        choices=STATUS_CHOICES,
        default="ACTIVE"
    )
    description = models.TextField(blank=True, default="")
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["location_code", "code"]
        verbose_name_plural = "Warehouses"

    def __str__(self):
        return f"{self.code} - {self.name}"


class SiteZone(models.Model):
    """Master zone record (one of the 7 canonical zones per warehouse)."""
    CATEGORY_CHOICES = [
        ("receiving", "Receiving"),
        ("detained", "Detained Articles"),
        ("seizure", "Seizure"),
        ("examination", "Examination"),
        ("stock", "General Stock"),
        ("disposal", "Disposal"),
        ("release", "Release"),
    ]
    SECURITY_LEVEL_CHOICES = [
        ("standard", "Standard"),
        ("restricted", "Restricted"),
        ("high", "High"),
    ]

    VMS_ZONE_TYPE_CHOICES = [
        ("Public", "Public"),
        ("Restricted", "Restricted"),
        ("High Security", "High Security"),
        ("Admin", "Admin"),
    ]

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    warehouse = models.ForeignKey(
        Warehouse,
        on_delete=models.CASCADE,
        related_name="zones"
    )
    code = models.CharField(
        max_length=20,
        help_text="e.g., Z-IN, Z-DA (one of the 7 canonical codes)"
    )
    name = models.CharField(max_length=255, help_text="e.g., Receiving Area")
    category = models.CharField(
        max_length=50,
        choices=CATEGORY_CHOICES,
        default="stock"
    )
    security_level = models.CharField(
        max_length=50,
        choices=SECURITY_LEVEL_CHOICES,
        default="standard"
    )
    sort_order = models.PositiveIntegerField(
        default=0,
        help_text="Display order (1-7)"
    )
    is_active = models.BooleanField(default=True)
    description = models.TextField(
        blank=True,
        default="",
        help_text="Optional SOP text"
    )
    purpose = models.CharField(
        max_length=255,
        blank=True,
        default="",
        help_text="Visitor/operational purpose of the zone"
    )
    requires_escort = models.BooleanField(default=False)
    access_hours_start = models.CharField(max_length=5, default="06:00")
    access_hours_end = models.CharField(max_length=5, default="22:00")
    weekend_access = models.BooleanField(default=False)
    max_occupancy = models.PositiveIntegerField(default=0)
    allowed_visitor_categories = models.JSONField(default=list, blank=True)
    gate_ids = models.JSONField(default=list, blank=True)
    camera_ids = models.JSONField(default=list, blank=True)
    vms_zone_type = models.CharField(
        max_length=50,
        choices=VMS_ZONE_TYPE_CHOICES,
        default="Public",
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["warehouse", "sort_order"]
        unique_together = [["warehouse", "code"]]
        verbose_name = "Site Zone"
        verbose_name_plural = "Site Zones"

    def __str__(self):
        return f"{self.warehouse.code} - {self.code} ({self.name})"


def distribution_video_path(instance: "MemoDistribution", filename: str) -> str:
    ext = os.path.splitext(filename)[1].lower() or ".mp4"
    return f"distribution/{instance.pk or 'new'}/{uuid.uuid4().hex}{ext}"


class WarehouseStockItem(models.Model):
    """Warehouse inventory line — may link to a detention memo / case."""

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    detention_memo_id = models.UUIDField(null=True, blank=True, db_index=True)
    client_row_id = models.CharField(max_length=80, blank=True, db_index=True)
    case_ref = models.CharField(max_length=200, blank=True, db_index=True)
    qr_code = models.CharField(max_length=160, blank=True, db_index=True)
    description = models.TextField(blank=True)
    pct_code = models.CharField(max_length=40, blank=True)
    quantity = models.DecimalField(max_digits=14, decimal_places=3, default=0)
    unit = models.CharField(max_length=40, blank=True, default="PCS")
    godown_warehouse = models.CharField(max_length=200, blank=True)
    status = models.CharField(max_length=80, blank=True, default="In Custody")
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["-updated_at"]

    def __str__(self):
        return f"{self.case_ref or self.qr_code or self.pk} — qty {self.quantity}"


class MemoDistribution(models.Model):
    """Recorded distribution/destruction of detained goods with camera evidence."""

    OUTCOME_INVENTORY = "inventory_deducted"
    OUTCOME_DESTRUCTED = "destructed"
    OUTCOME_CHOICES = [
        (OUTCOME_INVENTORY, "Inventory deducted"),
        (OUTCOME_DESTRUCTED, "Marked destructed"),
    ]

    STATUS_RECORDING = "recording"
    STATUS_COMPLETED = "completed"
    STATUS_FAILED = "failed"
    STATUS_CHOICES = [
        (STATUS_RECORDING, "Recording"),
        (STATUS_COMPLETED, "Completed"),
        (STATUS_FAILED, "Failed"),
    ]

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    detention_memo_id = models.UUIDField(db_index=True)
    detention_case_no = models.CharField(max_length=120, blank=True)
    camera = models.ForeignKey(
        "cameras.Camera",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="distributions",
    )
    video = models.FileField(upload_to=distribution_video_path, blank=True, null=True)
    camera_ids = models.JSONField(default=list, blank=True)
    camera_videos = models.JSONField(default=list, blank=True)
    selected_items = models.JSONField(default=list, blank=True)
    location_code = models.CharField(max_length=64, blank=True, default="")
    smoke_fire_detected = models.BooleanField(default=False)
    outcome = models.CharField(max_length=32, choices=OUTCOME_CHOICES, blank=True, default="")
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default=STATUS_RECORDING)
    performed_by = models.CharField(max_length=150, blank=True)
    notes = models.TextField(blank=True)
    inventory_deductions = models.JSONField(default=list, blank=True)
    error_message = models.TextField(blank=True)
    created_at = models.DateTimeField(default=timezone.now)
    completed_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering = ["-created_at"]

    def __str__(self):
        return f"Distribution {self.detention_case_no or self.detention_memo_id} ({self.outcome or self.status})"


class DestructionAlert(models.Model):
    """Smoke/fire alert raised during a destruction session."""

    SEVERITY_CRITICAL = "critical"
    SEVERITY_HIGH = "high"
    SEVERITY_CHOICES = [
        (SEVERITY_CRITICAL, "Critical"),
        (SEVERITY_HIGH, "High"),
    ]

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    distribution = models.ForeignKey(
        MemoDistribution,
        on_delete=models.CASCADE,
        related_name="alerts",
        null=True,
        blank=True,
    )
    detention_memo_id = models.UUIDField(db_index=True)
    detention_case_no = models.CharField(max_length=120, blank=True)
    camera = models.ForeignKey(
        "cameras.Camera",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="destruction_alerts",
    )
    location_code = models.CharField(max_length=64, blank=True, default="")
    alert_type = models.CharField(max_length=40, default="fire_smoke")
    severity = models.CharField(max_length=20, choices=SEVERITY_CHOICES, default=SEVERITY_CRITICAL)
    message = models.TextField()
    detection_class = models.CharField(max_length=80, blank=True)
    confidence = models.FloatField(default=0)
    detection_data = models.JSONField(default=dict, blank=True)
    notified_user_ids = models.JSONField(default=list, blank=True)
    acknowledged = models.BooleanField(default=False)
    acknowledged_at = models.DateTimeField(null=True, blank=True)
    acknowledged_by = models.CharField(max_length=150, blank=True)
    created_at = models.DateTimeField(default=timezone.now)

    class Meta:
        ordering = ["-created_at"]

    def __str__(self):
        return f"{self.alert_type} @ {self.detention_case_no or self.detention_memo_id}"


class FireSmokeDetectionLog(models.Model):
    """Immutable audit log for every smoke/fire ML detection during destruction."""

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    distribution = models.ForeignKey(
        MemoDistribution,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="fire_smoke_logs",
    )
    destruction_alert = models.ForeignKey(
        DestructionAlert,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="detection_logs",
    )
    detention_memo_id = models.UUIDField(db_index=True)
    detention_case_no = models.CharField(max_length=120, blank=True)
    detention_fir_number = models.CharField(max_length=120, blank=True)
    warehouse_name = models.CharField(max_length=400, blank=True, default="")
    location_code = models.CharField(max_length=64, blank=True, default="", db_index=True)
    place_of_detention = models.CharField(max_length=300, blank=True, default="")
    place_of_occurrence = models.CharField(max_length=300, blank=True, default="")
    camera = models.ForeignKey(
        "cameras.Camera",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="fire_smoke_logs",
    )
    camera_code = models.CharField(max_length=32, blank=True, default="")
    camera_name = models.CharField(max_length=150, blank=True, default="")
    camera_ip = models.CharField(max_length=45, blank=True, default="")
    camera_zone = models.CharField(max_length=64, blank=True, default="")
    camera_site_label = models.CharField(max_length=150, blank=True, default="")
    detection_class = models.CharField(max_length=80, blank=True)
    detection_label = models.CharField(max_length=120, blank=True)
    confidence = models.FloatField(default=0)
    bbox = models.JSONField(default=list, blank=True)
    detection_count = models.PositiveIntegerField(default=1)
    detections = models.JSONField(default=list, blank=True)
    alert_triggered = models.BooleanField(default=False)
    notified_user_ids = models.JSONField(default=list, blank=True)
    performed_by = models.CharField(max_length=150, blank=True)
    session_status = models.CharField(max_length=20, blank=True, default="")
    created_at = models.DateTimeField(default=timezone.now, db_index=True)

    class Meta:
        ordering = ["-created_at"]
        verbose_name = "Fire/Smoke detection log"
        verbose_name_plural = "Fire/Smoke detection logs"

    def __str__(self):
        return f"{self.detection_class or 'fire_smoke'} @ {self.camera_name or 'camera'} ({self.created_at:%Y-%m-%d %H:%M})"
