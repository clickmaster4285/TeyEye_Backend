from django.contrib import admin

from .models import Camera, DetectionEvent, Nvr, Site


@admin.register(Site)
class SiteAdmin(admin.ModelAdmin):
    list_display = ["code", "name", "is_active", "created_at"]
    list_filter = ["is_active"]
    search_fields = ["code", "name"]


@admin.register(Nvr)
class NvrAdmin(admin.ModelAdmin):
    list_display = ["name", "site", "ip_address", "port", "brand", "is_active"]
    list_filter = ["brand", "is_active", "site"]
    search_fields = ["name", "ip_address", "site__code"]


@admin.register(Camera)
class CameraAdmin(admin.ModelAdmin):
    list_display = ["code", "name", "nvr", "channel", "location", "purpose", "status", "is_active"]
    list_filter = ["location", "purpose", "status", "is_active", "nvr__site"]
    search_fields = ["code", "name", "zone", "nvr__name"]
    raw_id_fields = ["nvr"]


@admin.register(DetectionEvent)
class DetectionEventAdmin(admin.ModelAdmin):
    list_display = ["camera", "label", "confidence", "is_alert", "created_at"]
    list_filter = ["is_alert", "camera__location"]
