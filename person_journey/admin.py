from django.contrib import admin

from .models import CameraTrack, JourneyEvent, JourneyPerson


@admin.register(JourneyPerson)
class JourneyPersonAdmin(admin.ModelAdmin):
    list_display = ("code", "person_type", "display_name", "latest_zone", "latest_seen_at", "status")
    list_filter = ("person_type", "status")
    search_fields = ("code", "display_name", "uuid")
    readonly_fields = ("uuid", "created_at", "updated_at")


@admin.register(CameraTrack)
class CameraTrackAdmin(admin.ModelAdmin):
    list_display = ("track_id", "camera", "journey_person", "status", "started_at", "ended_at")
    list_filter = ("status",)


@admin.register(JourneyEvent)
class JourneyEventAdmin(admin.ModelAdmin):
    list_display = ("journey_person", "event_type", "title", "zone", "created_at")
    list_filter = ("event_type",)
