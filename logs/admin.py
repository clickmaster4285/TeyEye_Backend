from django.contrib import admin
from .models import UserActivityLog


@admin.register(UserActivityLog)
class UserActivityLogAdmin(admin.ModelAdmin):
    list_display = (
        "user",
        "ip_address",
        "country",
        "city",
        "device",
        "os",
        "browser",
        "action",
        "time",
    )