from rest_framework import serializers

from .distribution_service import collect_session_recording_entries
from .models import (
    DestructionAlert,
    FireSmokeDetectionLog,
    MemoDistribution,
    SiteZone,
    Warehouse,
    WarehouseStockItem,
)


class WarehouseSerializer(serializers.ModelSerializer):
    zone_count = serializers.SerializerMethodField()

    class Meta:
        model = Warehouse
        fields = ["id", "code", "name", "location_code", "status", "description", "zone_count", "created_at", "updated_at"]
        read_only_fields = ["id", "created_at", "updated_at"]

    def get_zone_count(self, obj):
        """Count active zones for this warehouse."""
        return obj.zones.filter(is_active=True).count()


class SiteZoneSerializer(serializers.ModelSerializer):
    warehouse_code = serializers.CharField(source="warehouse.code", read_only=True)
    warehouse_name = serializers.CharField(source="warehouse.name", read_only=True)
    warehouse_location = serializers.CharField(source="warehouse.location_code", read_only=True)

    class Meta:
        model = SiteZone
        fields = [
            "id",
            "warehouse",
            "warehouse_code",
            "warehouse_name",
            "warehouse_location",
            "code",
            "name",
            "purpose",
            "category",
            "security_level",
            "sort_order",
            "is_active",
            "description",
            "requires_escort",
            "access_hours_start",
            "access_hours_end",
            "weekend_access",
            "max_occupancy",
            "allowed_visitor_categories",
            "gate_ids",
            "camera_ids",
            "vms_zone_type",
            "created_at",
            "updated_at",
        ]
        read_only_fields = ["id", "created_at", "updated_at"]

    def update(self, instance, validated_data):
        """Allow updating WMS & VMS editable fields only."""
        allowed_fields = [
            "name",
            "purpose",
            "description",
            "is_active",
            "requires_escort",
            "access_hours_start",
            "access_hours_end",
            "weekend_access",
            "max_occupancy",
            "allowed_visitor_categories",
            "gate_ids",
            "camera_ids",
            "vms_zone_type",
        ]
        for field in allowed_fields:
            if field in validated_data:
                setattr(instance, field, validated_data[field])
        instance.save()
        return instance


class WarehouseStockItemSerializer(serializers.ModelSerializer):
    class Meta:
        model = WarehouseStockItem
        fields = [
            "id",
            "detention_memo_id",
            "client_row_id",
            "case_ref",
            "qr_code",
            "description",
            "pct_code",
            "quantity",
            "unit",
            "godown_warehouse",
            "status",
            "updated_at",
        ]


class MemoDistributionSerializer(serializers.ModelSerializer):
    camera_name = serializers.CharField(source="camera.name", read_only=True, default="")
    video_url = serializers.SerializerMethodField()
    camera_video_entries = serializers.SerializerMethodField()

    class Meta:
        model = MemoDistribution
        fields = [
            "id",
            "detention_memo_id",
            "detention_case_no",
            "camera",
            "camera_ids",
            "camera_name",
            "camera_videos",
            "camera_video_entries",
            "selected_items",
            "location_code",
            "smoke_fire_detected",
            "video_url",
            "outcome",
            "status",
            "performed_by",
            "notes",
            "inventory_deductions",
            "error_message",
            "created_at",
            "completed_at",
        ]

    def _absolute_media_url(self, url: str) -> str:
        request = self.context.get("request")
        if request and url.startswith("/"):
            return request.build_absolute_uri(url)
        return url

    def get_video_url(self, obj: MemoDistribution) -> str | None:
        if not obj.video:
            return None
        return self._absolute_media_url(obj.video.url)

    def get_camera_video_entries(self, obj: MemoDistribution) -> list[dict]:
        repair = bool(self.context.get("repair_recordings"))
        items = collect_session_recording_entries(obj, repair=repair)
        entries: list[dict] = []
        for item in items:
            path = str(item.get("path") or "").strip()
            filename = str(item.get("filename") or "").strip()
            camera_id = item.get("camera_id")
            url = ""
            if path:
                media_url = path if path.startswith("http") else f"/media/{path.lstrip('/')}"
                url = self._absolute_media_url(media_url)
            elif obj.video and camera_id == obj.camera_id:
                url = self._absolute_media_url(obj.video.url)
            entries.append(
                {
                    "camera_id": camera_id,
                    "filename": filename,
                    "path": path,
                    "url": url,
                    "size_bytes": item.get("size_bytes", 0),
                }
            )
        if not entries and obj.video:
            entries.append(
                {
                    "camera_id": obj.camera_id,
                    "filename": "recording.mp4",
                    "path": obj.video.name,
                    "url": self._absolute_media_url(obj.video.url),
                    "size_bytes": 0,
                }
            )
        return entries


class DestructionAlertSerializer(serializers.ModelSerializer):
    camera_name = serializers.CharField(source="camera.name", read_only=True, default="")

    class Meta:
        model = DestructionAlert
        fields = [
            "id",
            "distribution",
            "detention_memo_id",
            "detention_case_no",
            "camera",
            "camera_name",
            "location_code",
            "alert_type",
            "severity",
            "message",
            "detection_class",
            "confidence",
            "detection_data",
            "notified_user_ids",
            "acknowledged",
            "acknowledged_at",
            "acknowledged_by",
            "created_at",
        ]
        read_only_fields = fields


class FireSmokeDetectionLogSerializer(serializers.ModelSerializer):
    class Meta:
        model = FireSmokeDetectionLog
        fields = [
            "id",
            "distribution",
            "destruction_alert",
            "detention_memo_id",
            "detention_case_no",
            "detention_fir_number",
            "warehouse_name",
            "location_code",
            "place_of_detention",
            "place_of_occurrence",
            "camera",
            "camera_code",
            "camera_name",
            "camera_ip",
            "camera_zone",
            "camera_site_label",
            "detection_class",
            "detection_label",
            "confidence",
            "bbox",
            "detection_count",
            "detections",
            "alert_triggered",
            "notified_user_ids",
            "performed_by",
            "session_status",
            "created_at",
        ]
        read_only_fields = fields
