from recognition.models import DetectionSnapshot, FaceEnrollment
from recognition.services.snapshot_saver import snapshot_to_dict
from rest_framework import serializers


class FaceEnrollmentDetailSerializer(serializers.ModelSerializer):
    staff_id = serializers.IntegerField(source="staff.id", read_only=True)
    employee_id = serializers.CharField(source="staff.employee_id", read_only=True, allow_null=True)
    staff_name = serializers.CharField(source="staff.full_name", read_only=True)

    class Meta:
        model = FaceEnrollment
        fields = [
            "id",
            "staff_id",
            "employee_id",
            "staff_name",
            "is_enrolled",
            "is_trained",
            "total_images",
            "model_version",
            "dataset_folder",
            "profile_image",
            "created_at",
            "updated_at",
        ]


class DetectionSnapshotSerializer(serializers.ModelSerializer):
    staff_id = serializers.IntegerField(read_only=True)
    employee_id = serializers.CharField(source="staff.employee_id", read_only=True, allow_null=True)
    employee_name = serializers.CharField(source="staff.full_name", read_only=True)
    camera_label = serializers.SerializerMethodField()
    image_url = serializers.SerializerMethodField()

    class Meta:
        model = DetectionSnapshot
        fields = [
            "id",
            "staff_id",
            "employee_id",
            "employee_name",
            "camera_id",
            "camera_name",
            "camera_label",
            "image_url",
            "confidence",
            "attendance_action",
            "detected_at",
        ]

    def get_camera_label(self, obj):
        return f"Camera #{obj.camera_id or '?'} · {obj.camera_name}"

    def get_image_url(self, obj):
        return snapshot_to_dict(obj)["image_url"]
