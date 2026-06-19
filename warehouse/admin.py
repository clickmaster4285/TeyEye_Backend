from django.contrib import admin
from .models import Warehouse, SiteZone


@admin.register(Warehouse)
class WarehouseAdmin(admin.ModelAdmin):
    list_display = ["code", "name", "location_code", "status", "created_at"]
    list_filter = ["status", "location_code", "created_at"]
    search_fields = ["code", "name", "location_code"]
    readonly_fields = ["id", "created_at", "updated_at"]
    fieldsets = (
        ("Identification", {
            "fields": ["id", "code", "name", "location_code"]
        }),
        ("Status", {
            "fields": ["status", "description"]
        }),
        ("Timestamps", {
            "fields": ["created_at", "updated_at"]
        }),
    )


@admin.register(SiteZone)
class SiteZoneAdmin(admin.ModelAdmin):
    list_display = ["code", "warehouse", "name", "category", "security_level", "sort_order", "is_active"]
    list_filter = ["warehouse", "category", "security_level", "is_active"]
    search_fields = ["code", "name", "warehouse__code", "warehouse__name"]
    readonly_fields = ["id", "created_at", "updated_at"]
    fieldsets = (
        ("Identification", {
            "fields": ["id", "warehouse", "code", "name"]
        }),
        ("Classification", {
            "fields": ["category", "security_level", "sort_order"]
        }),
        ("Details", {
            "fields": ["is_active", "description"]
        }),
        ("Timestamps", {
            "fields": ["created_at", "updated_at"]
        }),
    )
