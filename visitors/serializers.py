from rest_framework import serializers
from django.utils import timezone

from .models import Visitor, ZoneAccessLog, SecurityAlert, Vehicle, VisitorNotification, VmsListRecord
from .payload_utils import (
    merge_extra_into_response,
    split_visitor_payload,
    strip_large_fields_for_list,
    visitor_created_by_label,
    visitor_has_profile_photo,
)


class VisitorSerializer(serializers.ModelSerializer):
    """Full visitor schema for API responses."""

    created_by = serializers.SerializerMethodField()

    class Meta:
        model = Visitor
        fields = [
            "id",
            "created_at",
            "updated_at",
            "visitor_type",
            "full_name",
            "gender",
            "cnic_number",
            "passport_number",
            "nationality",
            "date_of_birth",
            "mobile_number",
            "email_address",
            "residential_address",
            "visit_purpose",
            "visit_description",
            "department_to_visit",
            "host_officer_name",
            "host_officer_designation",
            "preferred_visit_date",
            "preferred_time_slot",
            "expected_duration",
            "preferred_view_visit",
            "document_type",
            "document_no",
            "issuing_authority",
            "expiry_date",
            "front_image",
            "back_image",
            "support_doc_type",
            "application_letter",
            "letter_ref_no",
            "additional_document",
            "upload_procedure",
            "organization_name",
            "organization_type",
            "ntn_registration_no",
            "designation",
            "office_address",
            "capture_date",
            "capture_time",
            "captured_by",
            "camera_location",
            "photo_quality_score",
            "face_match_status",
            "captured_photo",
            "disclaimer_accepted",
            "terms_accepted",
            "previous_visit_reference",
            "registration_type",
            "cnic_passport",
            "visit_purpose_description",
            "visit_type",
            "reference_number",
            "preferred_date",
            "preferred_time_slot_walkin",
            "department_for_slot",
            "slot_duration",
            "host_id",
            "host_full_name",
            "host_designation",
            "host_department",
            "host_email",
            "host_contact_number",
            "watchlist_check_status",
            "approver_required",
            "temporary_access_granted",
            "guard_remarks",
            "qr_code_id",
            "visitor_ref_number",
            "visit_date",
            "time_validity_start",
            "time_validity_end",
            "access_zone",
            "entry_gate",
            "expiry_status",
            "scan_count",
            "generated_on",
            "generated_by",
            "flow_stage",
            "registration_source",
            "registration_status",
            "approval_status",
            "approved_by",
            "denied_by",
            "rejection_reason",
            "location",
            "registered_by_user_id",
            "registered_by_username",
            "created_by",
            "profile_image",
            "guard_entry_time",
            "guard_name",
            "host_notified_at",
            "extra_data",
        ]
        read_only_fields = ["id", "created_at", "updated_at", "qr_code_id", "scan_count"]
        extra_kwargs = {
            "gender": {"allow_blank": True},
            "host_officer_designation": {"allow_blank": True},
            "preferred_time_slot": {"allow_blank": True},
            "expected_duration": {"allow_blank": True},
            "preferred_view_visit": {"allow_blank": True},
            "document_type": {"allow_blank": True},
            "issuing_authority": {"allow_blank": True},
            "support_doc_type": {"allow_blank": True},
            "upload_procedure": {"allow_blank": True},
            "access_zone": {"allow_blank": True},
            "entry_gate": {"allow_blank": True},
            "expiry_status": {"allow_blank": True},
            "generated_by": {"allow_blank": True},
            "email_address": {"allow_blank": True},
            "residential_address": {"allow_blank": True},
            "visit_description": {"allow_blank": True},
            "host_officer_name": {"allow_blank": True},
        }

    def validate(self, attrs):
        attrs = super().validate(attrs)
        reg_status = attrs.get("registration_status")
        if reg_status is None and self.instance is not None:
            reg_status = self.instance.registration_status
        if str(reg_status or "").strip().lower() == "draft":
            return attrs
        access_zone = attrs.get("access_zone")
        if access_zone is None and self.instance is not None:
            access_zone = self.instance.access_zone
        if not str(access_zone or "").strip():
            raise serializers.ValidationError(
                {"access_zone": "Access zone is required."}
            )
        return attrs

    def get_created_by(self, obj):
        label = visitor_created_by_label(obj)
        return label or None

    def to_representation(self, instance):
        data = super().to_representation(instance)
        data = merge_extra_into_response(data, instance)
        if self.context.get("omit_blobs"):
            data = strip_large_fields_for_list(data)
        return data


class VisitorListSerializer(VisitorSerializer):
    """List responses without multi-megabyte image payloads."""

    def to_representation(self, instance):
        data = super().to_representation(instance)
        if self.context.get("omit_blobs"):
            request = self.context.get("request")
            if request and instance.pk and visitor_has_profile_photo(instance):
                path = f"/api/visitors/{instance.pk}/profile-image/"
                try:
                    data["profile_image_url"] = request.build_absolute_uri(path)
                except Exception:
                    data["profile_image_url"] = path
        return data


class VisitorWriteSerializer(serializers.Serializer):
    """Accept flexible frontend payload for create/update."""

    def create(self, validated_data):
        from users.permissions import resolve_location_for_write
        from .payload_utils import apply_registered_by_from_request

        source = self.context.get("registration_source", "")
        model_fields, extra = split_visitor_payload(validated_data, registration_source=source)
        request = self.context.get("request")
        if request and getattr(request.user, "is_authenticated", False):
            model_fields["location"] = resolve_location_for_write(
                request.user,
                model_fields.get("location") or validated_data.get("location") or "",
            )
        apply_registered_by_from_request(model_fields, request)
        model_fields["extra_data"] = extra
        if model_fields.get("registration_status") == "draft":
            model_fields["flow_stage"] = "arrived"
        visitor = Visitor.objects.create(**model_fields)
        if str(model_fields.get("registration_status") or "").strip().lower() != "draft":
            from .screening_utils import apply_visitor_screening

            apply_visitor_screening(visitor)
        return visitor

    def update(self, instance, validated_data):
        partial = bool(self.partial)
        model_fields, extra = split_visitor_payload(validated_data, partial=partial)
        existing_extra = dict(instance.extra_data or {})
        existing_extra.update(extra)
        model_fields["extra_data"] = existing_extra
        for key, value in model_fields.items():
            if key == "id":
                continue
            setattr(instance, key, value)
        instance.save()
        reg_status = model_fields.get("registration_status", instance.registration_status)
        if str(reg_status or "").strip().lower() != "draft":
            from .screening_utils import apply_visitor_screening

            apply_visitor_screening(instance)
        return instance

    def to_internal_value(self, data):
        if not isinstance(data, dict):
            raise serializers.ValidationError("Expected object.")
        return data


class FaceCaptureSerializer(serializers.Serializer):
    capture_date = serializers.CharField(required=False, allow_blank=True)
    capture_time = serializers.CharField(required=False, allow_blank=True)
    captured_by = serializers.CharField(required=False, allow_blank=True)
    camera_location = serializers.CharField(required=False, allow_blank=True)
    photo_quality_score = serializers.CharField(required=False, allow_blank=True)
    face_match_status = serializers.CharField(required=False, allow_blank=True)
    captured_photo = serializers.CharField(required=False, allow_blank=True)


class ZoneScanSerializer(serializers.Serializer):
    qr_code_id = serializers.CharField(required=True)
    zone = serializers.CharField(required=True)
    gate = serializers.CharField(required=False, default="")
    scan_type = serializers.ChoiceField(
        choices=[("entry", "Entry"), ("exit", "Exit")],
        default="entry",
    )
    scanner_id = serializers.CharField(required=False, default="")


class ZoneAccessLogSerializer(serializers.ModelSerializer):
    visitor_name = serializers.CharField(source="visitor.full_name", read_only=True)

    class Meta:
        model = ZoneAccessLog
        fields = [
            "id",
            "visitor",
            "visitor_name",
            "zone",
            "gate",
            "scan_type",
            "allowed",
            "message",
            "scanned_at",
            "scanner_id",
        ]
        read_only_fields = ["id", "scanned_at"]


class SecurityAlertSerializer(serializers.ModelSerializer):
    visitor_name = serializers.SerializerMethodField()

    def get_visitor_name(self, obj):
        return obj.visitor.full_name if obj.visitor else None

    class Meta:
        model = SecurityAlert
        fields = [
            "id",
            "visitor",
            "visitor_name",
            "alert_type",
            "severity",
            "message",
            "zone",
            "gate",
            "created_at",
            "acknowledged",
            "acknowledged_at",
            "acknowledged_by",
        ]
        read_only_fields = ["id", "created_at"]


class ApproveDenySerializer(serializers.Serializer):
    approved_by = serializers.CharField(required=False, allow_blank=True, default="")
    denied_by = serializers.CharField(required=False, allow_blank=True, default="")
    rejection_reason = serializers.CharField(required=False, allow_blank=True, default="")


class NotifyHostSerializer(serializers.Serializer):
    recipient = serializers.CharField(required=False, allow_blank=True, default="")


class VehicleSerializer(serializers.ModelSerializer):
    visitor_name = serializers.CharField(source="visitor.full_name", read_only=True)

    class Meta:
        model = Vehicle
        fields = [
            "id",
            "visitor",
            "visitor_name",
            "plate_number",
            "vehicle_type",
            "contractor_company",
            "driver_name",
            "remarks",
            "extra_data",
            "created_at",
        ]
        read_only_fields = ["id", "created_at"]


class VisitorNotificationSerializer(serializers.ModelSerializer):
    visitor_name = serializers.CharField(source="visitor.full_name", read_only=True)

    class Meta:
        model = VisitorNotification
        fields = [
            "id",
            "visitor",
            "visitor_name",
            "notification_type",
            "recipient",
            "message",
            "success",
            "sent_at",
        ]
        read_only_fields = ["id", "sent_at"]


class VmsListRecordSerializer(serializers.ModelSerializer):
    class Meta:
        model = VmsListRecord
        fields = ["id", "module", "record_id", "data", "location", "created_at", "updated_at"]
        read_only_fields = ["id", "created_at", "updated_at"]


class VmsListBulkSerializer(serializers.Serializer):
    module = serializers.CharField(max_length=80)
    rows = serializers.ListField(child=serializers.DictField(), allow_empty=True)
    location = serializers.CharField(required=False, allow_blank=True, default="")
