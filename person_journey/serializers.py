from rest_framework import serializers

from .models import CameraTrack, JourneyEvent, JourneyPerson
from .snapshot_utils import journey_event_snapshot_url, journey_person_latest_snapshot_url


class JourneyPersonListSerializer(serializers.ModelSerializer):
    latest_camera_name = serializers.CharField(source="latest_camera.name", read_only=True, default="")
    staff_name = serializers.CharField(source="staff.full_name", read_only=True, default="")
    visitor_name = serializers.CharField(source="visitor.full_name", read_only=True, default="")
    latest_snapshot_url = serializers.SerializerMethodField()

    class Meta:
        model = JourneyPerson
        fields = [
            "uuid",
            "code",
            "person_type",
            "display_name",
            "staff_name",
            "visitor_name",
            "latest_camera_name",
            "latest_zone",
            "latest_seen_at",
            "latest_snapshot_url",
            "status",
            "created_at",
        ]

    def get_latest_snapshot_url(self, obj: JourneyPerson) -> str:
        cached = getattr(obj, "_latest_snapshot_url", None)
        if cached is not None:
            return cached
        return journey_person_latest_snapshot_url(obj)


class JourneyEventSerializer(serializers.ModelSerializer):
    camera_name = serializers.CharField(source="camera.name", read_only=True, default="")
    camera_code = serializers.CharField(source="camera.code", read_only=True, default="")
    snapshot_url = serializers.SerializerMethodField()
    person_code = serializers.CharField(source="journey_person.code", read_only=True, default="")
    person_name = serializers.CharField(source="journey_person.display_name", read_only=True, default="")

    class Meta:
        model = JourneyEvent
        fields = [
            "id",
            "event_type",
            "title",
            "description",
            "camera_name",
            "camera_code",
            "camera",
            "zone",
            "gate",
            "confidence",
            "match_score",
            "bbox",
            "snapshot_path",
            "snapshot_url",
            "person_code",
            "person_name",
            "metadata",
            "created_at",
        ]

    def get_snapshot_url(self, obj: JourneyEvent) -> str:
        path = (obj.snapshot_path or "").strip()
        if path:
            return path
        clip_map: dict[int, str] | None = self.context.get("detection_clip_map")
        if clip_map is not None and obj.detection_event_id:
            return clip_map.get(obj.detection_event_id) or ""
        return ""


class CameraTrackSerializer(serializers.ModelSerializer):
    camera_name = serializers.CharField(source="camera.name", read_only=True, default="")

    class Meta:
        model = CameraTrack
        fields = [
            "id",
            "track_id",
            "camera_name",
            "status",
            "started_at",
            "ended_at",
            "last_bbox",
        ]


class JourneyPersonDetailSerializer(JourneyPersonListSerializer):
    events = JourneyEventSerializer(many=True, read_only=True)
    tracks = CameraTrackSerializer(many=True, read_only=True)

    class Meta(JourneyPersonListSerializer.Meta):
        fields = JourneyPersonListSerializer.Meta.fields + [
            "face_embedding",
            "reid_embedding",
            "metadata",
            "events",
            "tracks",
        ]


class IngestObservationSerializer(serializers.Serializer):
    camera_id = serializers.IntegerField(required=False, allow_null=True)
    camera_key = serializers.CharField(required=False, allow_blank=True, default="")
    track_id = serializers.IntegerField(min_value=0)
    track_status = serializers.ChoiceField(choices=["active", "finished"], default="active")
    bbox = serializers.ListField(child=serializers.FloatField(), required=False, default=list)
    confidence = serializers.FloatField(required=False, default=0.0)
    face_embedding = serializers.ListField(child=serializers.FloatField(), required=False, default=list)
    reid_embedding = serializers.ListField(child=serializers.FloatField(), required=False, default=list)
    face_label = serializers.CharField(required=False, allow_blank=True, default="")
    face_match_score = serializers.FloatField(required=False, allow_null=True)
    detections = serializers.ListField(child=serializers.DictField(), required=False, default=list)
    snapshot_path = serializers.CharField(required=False, allow_blank=True, default="")


class MergeVisitorSerializer(serializers.Serializer):
    person_uuid = serializers.UUIDField()
    visitor_id = serializers.IntegerField(min_value=1)
    face_match_score = serializers.FloatField(required=False, allow_null=True)
