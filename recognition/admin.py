from django.contrib import admin

from recognition.models import DetectionSnapshot, FaceEnrollment


@admin.register(FaceEnrollment)
class FaceEnrollmentAdmin(admin.ModelAdmin):
    list_display = ("id", "staff", "total_images", "is_enrolled", "is_trained", "updated_at")
    list_filter = ("is_enrolled", "is_trained")
    search_fields = ("staff__full_name", "staff__employee_id", "staff__cnic")
    raw_id_fields = ("staff",)


@admin.register(DetectionSnapshot)
class DetectionSnapshotAdmin(admin.ModelAdmin):
    list_display = ("id", "staff", "camera_name", "confidence", "attendance_action", "detected_at")
    list_filter = ("attendance_action",)
    search_fields = ("staff__full_name", "camera_name")
    raw_id_fields = ("staff", "camera")
