from django.contrib import admin
from .models import (
    Visitor,
    ZoneAccessLog,
    SecurityAlert,
    Vehicle,
    VisitorNotification,
    VmsListRecord,
)


@admin.register(Visitor)
class VisitorAdmin(admin.ModelAdmin):
    list_display = (
        "full_name",
        "visitor_type",
        "registration_source",
        "registration_status",
        "approval_status",
        "flow_stage",
        "preferred_visit_date",
    )
    list_filter = ("flow_stage", "visitor_type", "registration_source", "approval_status")
    search_fields = ("full_name", "cnic_number", "passport_number", "qr_code_id")


@admin.register(ZoneAccessLog)
class ZoneAccessLogAdmin(admin.ModelAdmin):
    list_display = ("visitor", "zone", "gate", "scan_type", "allowed", "scanned_at")
    list_filter = ("allowed", "scan_type", "zone")


@admin.register(SecurityAlert)
class SecurityAlertAdmin(admin.ModelAdmin):
    list_display = ("alert_type", "severity", "visitor", "acknowledged", "created_at")
    list_filter = ("acknowledged", "severity", "alert_type")


@admin.register(Vehicle)
class VehicleAdmin(admin.ModelAdmin):
    list_display = ("plate_number", "visitor", "vehicle_type", "created_at")


@admin.register(VisitorNotification)
class VisitorNotificationAdmin(admin.ModelAdmin):
    list_display = ("visitor", "notification_type", "recipient", "success", "sent_at")


@admin.register(VmsListRecord)
class VmsListRecordAdmin(admin.ModelAdmin):
    list_display = ("module", "record_id", "location", "updated_at")
    list_filter = ("module",)
