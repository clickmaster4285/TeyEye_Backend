from django.conf import settings
from django.db import models


class FaceEnrollment(models.Model):
    """InsightFace enrollment state for a Staff member."""

    staff = models.OneToOneField(
        "users.Staff",
        on_delete=models.CASCADE,
        related_name="face_enrollment",
    )
    profile_image = models.ImageField(
        upload_to="recognition/profile/",
        blank=True,
        null=True,
    )
    dataset_folder = models.CharField(max_length=255, unique=True)
    total_images = models.PositiveIntegerField(default=0)
    is_enrolled = models.BooleanField(default=False)
    is_trained = models.BooleanField(default=False)
    model_version = models.CharField(max_length=50, default="InsightFace_v1")
    embedding = models.JSONField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["staff_id"]

    def __str__(self):
        return f"Enrollment staff={self.staff_id} trained={self.is_trained}"

    @property
    def gallery_key(self) -> str:
        """Stable key used in the recognition gallery."""
        return f"staff-{self.staff_id}"


class DetectionSnapshot(models.Model):
    """Annotated JPEG saved when InsightFace matches a staff member on CCTV."""

    staff = models.ForeignKey(
        "users.Staff",
        on_delete=models.CASCADE,
        related_name="detection_snapshots",
    )
    camera = models.ForeignKey(
        "cameras.Camera",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="recognition_snapshots",
    )
    camera_name = models.CharField(max_length=100)
    image = models.ImageField(upload_to="detections/%Y/%m/%d/")
    confidence = models.FloatField(default=0.0)
    attendance_action = models.CharField(max_length=32, blank=True)
    detected_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-detected_at"]

    def __str__(self):
        return f"{self.staff_id} @ {self.camera_name} ({self.detected_at})"
