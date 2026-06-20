from django.db import models


class CameraPurpose(models.TextChoices):
    SURVEILLANCE = "surveillance", "General Surveillance"
    OBJECT_DETECTION = "object_detection", "Object Detection (YOLO)"
    FACE_RECOGNITION = "face_recognition", "Face Recognition"
    ATTENDANCE = "attendance", "Attendance Check-in"
    ANPR = "anpr", "ANPR / Vehicle"
    ZONE_MONITORING = "zone_monitoring", "Zone Access Monitoring"
    THERMAL = "thermal", "Thermal Anomaly"


class CameraType(models.TextChoices):
    PTZ = "PTZ", "PTZ"
    FIXED = "Fixed", "Fixed"
    THERMAL = "Thermal", "Thermal"
    THREE_SIXTY = "360", "360°"


class CameraStatus(models.TextChoices):
    ONLINE = "Online", "Online"
    OFFLINE = "Offline", "Offline"


class NvrBrand(models.TextChoices):
    HIKVISION = "hikvision", "Hikvision"
    DAHUA = "dahua", "Dahua"
    UNIVIEW = "uniview", "Uniview"
    GENERIC = "generic", "Generic RTSP"


class Site(models.Model):
    """Physical location (city, branch, facility)."""

    code = models.CharField(max_length=64, unique=True, help_text="Short code e.g. PESHAWAR")
    name = models.CharField(max_length=150)
    description = models.TextField(blank=True, default="")
    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = "cameras_site"
        ordering = ["name"]

    def __str__(self):
        return f"{self.code} — {self.name}"


class Nvr(models.Model):
    """Network Video Recorder — credentials stored here only."""

    site = models.ForeignKey(Site, on_delete=models.CASCADE, related_name="nvrs")
    name = models.CharField(max_length=150)
    ip_address = models.CharField(max_length=45)
    port = models.PositiveIntegerField(default=554)
    username = models.CharField(max_length=64, default="admin")
    password = models.CharField(max_length=128, blank=True, default="")
    brand = models.CharField(max_length=32, choices=NvrBrand.choices, default=NvrBrand.HIKVISION)
    stream_path_template = models.CharField(
        max_length=255,
        blank=True,
        default="",
        help_text="Optional path template with {channel}, e.g. /Streaming/Channels/{channel}",
    )
    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = "cameras_nvrdevice"
        ordering = ["site__name", "name"]
        verbose_name = "NVR"
        verbose_name_plural = "NVRs"

    def __str__(self):
        return f"{self.name} @ {self.ip_address}"


class Camera(models.Model):
    """Camera channel on an NVR — no credentials or RTSP URLs stored."""

    nvr = models.ForeignKey(Nvr, on_delete=models.CASCADE, related_name="cameras")
    channel = models.PositiveSmallIntegerField(
        db_column="rtsp_channel",
        help_text="NVR channel number (1–32+, or Hikvision stream ID e.g. 101)",
    )
    code = models.CharField(max_length=32, unique=True, blank=True)
    name = models.CharField(max_length=150, help_text="User-defined label e.g. Main Gate")
    location = models.CharField(max_length=64, help_text="Denormalized site code")
    zone = models.CharField(max_length=64, blank=True, default="")
    camera_type = models.CharField(max_length=16, choices=CameraType.choices, default=CameraType.FIXED)
    purpose = models.CharField(
        max_length=32,
        choices=CameraPurpose.choices,
        default=CameraPurpose.SURVEILLANCE,
    )
    resolution = models.CharField(max_length=32, blank=True, default="1920x1080")
    frame_rate = models.CharField(max_length=8, blank=True, default="25")
    status = models.CharField(max_length=16, choices=CameraStatus.choices, default=CameraStatus.ONLINE)
    recording = models.BooleanField(default=True)
    storage_path = models.CharField(max_length=255, blank=True, default="")
    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["nvr__site__name", "nvr__name", "channel"]
        unique_together = [("nvr", "channel")]

    def __str__(self):
        return f"{self.code or self.pk} — {self.name} (Ch {self.channel})"

    @property
    def ml_enabled(self) -> bool:
        return self.is_active

    @property
    def stream_key(self) -> str:
        return f"cam-{self.pk}"

    def effective_stream_url(self) -> str:
        from .rtsp_utils import build_rtsp_url_from_nvr

        return build_rtsp_url_from_nvr(self.nvr, self.channel)

    @property
    def is_rtsp(self) -> bool:
        return bool(self.nvr_id)

    def save(self, *args, **kwargs):
        if self.nvr_id and not self.location:
            self.location = self.nvr.site.code
        is_new = self.pk is None
        super().save(*args, **kwargs)
        if is_new and not self.code:
            self.code = f"CAM-{self.pk:04d}"
            super().save(update_fields=["code"])


class ClipStatus(models.TextChoices):
    PENDING = "pending", "Pending"
    RECORDING = "recording", "Recording"
    READY = "ready", "Ready"
    FAILED = "failed", "Failed"
    SKIPPED = "skipped", "Skipped"


class DetectionEvent(models.Model):
    camera = models.ForeignKey(Camera, on_delete=models.CASCADE, related_name="detection_events")
    class_name = models.CharField(max_length=80)
    label = models.CharField(max_length=120)
    confidence = models.FloatField()
    bbox = models.JSONField(default=list)
    is_alert = models.BooleanField(default=False)
    clip = models.FileField(
        upload_to="detection_clips/%Y/%m/%d/",
        blank=True,
        help_text="Short MP4 captured when this detection was saved (5–10 s).",
    )
    clip_status = models.CharField(
        max_length=16,
        choices=ClipStatus.choices,
        default=ClipStatus.PENDING,
    )
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-created_at"]

    def __str__(self):
        return f"{self.camera.code} {self.label} @ {self.created_at:%Y-%m-%d %H:%M}"
