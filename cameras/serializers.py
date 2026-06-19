from rest_framework import serializers

from .models import Camera, CameraPurpose, DetectionEvent, Nvr, NvrBrand, Site


class SiteSerializer(serializers.ModelSerializer):
    nvr_count = serializers.SerializerMethodField()
    camera_count = serializers.SerializerMethodField()

    class Meta:
        model = Site
        fields = [
            "id",
            "code",
            "name",
            "description",
            "is_active",
            "nvr_count",
            "camera_count",
            "created_at",
            "updated_at",
        ]
        read_only_fields = ["id", "created_at", "updated_at", "nvr_count", "camera_count"]

    def get_nvr_count(self, obj: Site) -> int:
        return obj.nvrs.filter(is_active=True).count()

    def get_camera_count(self, obj: Site) -> int:
        return Camera.objects.filter(nvr__site=obj, is_active=True).count()


class NvrSerializer(serializers.ModelSerializer):
    site_code = serializers.CharField(source="site.code", read_only=True)
    site_name = serializers.CharField(source="site.name", read_only=True)
    brand_label = serializers.CharField(source="get_brand_display", read_only=True)
    password_set = serializers.SerializerMethodField()
    camera_count = serializers.SerializerMethodField()

    class Meta:
        model = Nvr
        fields = [
            "id",
            "site",
            "site_code",
            "site_name",
            "name",
            "ip_address",
            "port",
            "username",
            "password",
            "password_set",
            "brand",
            "brand_label",
            "stream_path_template",
            "is_active",
            "camera_count",
            "created_at",
            "updated_at",
        ]
        read_only_fields = ["id", "created_at", "updated_at", "site_code", "site_name", "brand_label", "camera_count"]
        extra_kwargs = {"password": {"write_only": True, "required": False, "allow_blank": True}}

    def get_password_set(self, obj: Nvr) -> bool:
        return bool(obj.password)

    def get_camera_count(self, obj: Nvr) -> int:
        return obj.cameras.filter(is_active=True).count()

    def to_representation(self, instance):
        data = super().to_representation(instance)
        data.pop("password", None)
        return data

    def update(self, instance, validated_data):
        if validated_data.get("password") == "":
            validated_data.pop("password")
        return super().update(instance, validated_data)


class CameraSerializer(serializers.ModelSerializer):
    ml_enabled = serializers.BooleanField(read_only=True)
    is_rtsp = serializers.BooleanField(read_only=True)
    stream_path = serializers.SerializerMethodField()
    ml_live_stream_path = serializers.SerializerMethodField()
    purpose_label = serializers.CharField(source="get_purpose_display", read_only=True)
    site_code = serializers.CharField(source="nvr.site.code", read_only=True)
    site_name = serializers.CharField(source="nvr.site.name", read_only=True)
    nvr_name = serializers.CharField(source="nvr.name", read_only=True)
    nvr_ip = serializers.CharField(source="nvr.ip_address", read_only=True)
    channel_label = serializers.SerializerMethodField()

    class Meta:
        model = Camera
        fields = [
            "id",
            "code",
            "name",
            "nvr",
            "channel",
            "channel_label",
            "site_code",
            "site_name",
            "nvr_name",
            "nvr_ip",
            "location",
            "zone",
            "purpose",
            "purpose_label",
            "status",
            "is_active",
            "ml_enabled",
            "is_rtsp",
            "stream_path",
            "ml_live_stream_path",
            "created_at",
            "updated_at",
        ]
        read_only_fields = [
            "id",
            "code",
            "location",
            "created_at",
            "updated_at",
            "stream_path",
            "site_code",
            "site_name",
            "nvr_name",
            "nvr_ip",
        ]

    def get_channel_label(self, obj: Camera) -> str:
        return f"Channel {obj.channel}"

    def get_stream_path(self, obj: Camera) -> str:
        return f"/api/cameras/streams/{obj.pk}/mjpeg/"

    def get_ml_live_stream_path(self, obj: Camera) -> str:
        if not obj.is_active or not obj.nvr_id:
            return ""
        return f"/api/cameras/{obj.pk}/ml-live/mjpeg/"


class CameraWriteSerializer(serializers.ModelSerializer):
    class Meta:
        model = Camera
        fields = ["name", "nvr", "channel", "zone", "purpose", "status", "is_active"]

    def validate_channel(self, value: int) -> int:
        if value < 1:
            raise serializers.ValidationError("Channel must be at least 1.")
        return value

    def validate(self, attrs):
        nvr = attrs.get("nvr") or (self.instance.nvr if self.instance else None)
        channel = attrs.get("channel") or (self.instance.channel if self.instance else None)
        if nvr and channel:
            qs = Camera.objects.filter(nvr=nvr, channel=channel)
            if self.instance:
                qs = qs.exclude(pk=self.instance.pk)
            if qs.exists():
                raise serializers.ValidationError(
                    {"channel": f"Channel {channel} already exists on this NVR."}
                )
        return attrs


class BulkCameraCreateSerializer(serializers.Serializer):
    channel_count = serializers.IntegerField(min_value=1, max_value=64)
    name_prefix = serializers.CharField(max_length=80, required=False, default="Camera")
    zone = serializers.CharField(max_length=64, required=False, allow_blank=True, default="")
    purpose = serializers.ChoiceField(choices=CameraPurpose.choices, required=False, default=CameraPurpose.SURVEILLANCE)


def purpose_options():
    return [{"value": c.value, "label": c.label} for c in CameraPurpose]


def nvr_brand_options():
    return [{"value": c.value, "label": c.label} for c in NvrBrand]


class DetectionEventSerializer(serializers.ModelSerializer):
    camera_code = serializers.CharField(source="camera.code", read_only=True)
    name = serializers.CharField(source="camera.name", read_only=True)
    site_code = serializers.CharField(source="camera.nvr.site.code", read_only=True)
    site_name = serializers.CharField(source="camera.nvr.site.name", read_only=True)
    nvr_name = serializers.CharField(source="camera.nvr.name", read_only=True)
    nvr_ip = serializers.CharField(source="camera.nvr.ip_address", read_only=True)
    channel = serializers.IntegerField(source="camera.channel", read_only=True)
    zone = serializers.CharField(source="camera.zone", read_only=True)
    purpose = serializers.CharField(source="camera.purpose", read_only=True)
    purpose_label = serializers.CharField(source="camera.get_purpose_display", read_only=True)

    class Meta:
        model = DetectionEvent
        fields = [
            "id",
            "camera",
            "camera_code",
            "name",
            "site_code",
            "site_name",
            "nvr_name",
            "nvr_ip",
            "channel",
            "zone",
            "purpose",
            "purpose_label",
            "class_name",
            "label",
            "confidence",
            "bbox",
            "is_alert",
            "created_at",
        ]
