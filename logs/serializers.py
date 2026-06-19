from rest_framework import serializers
from .models import UserActivityLog


class ActivityLogSerializer(serializers.ModelSerializer):
    username = serializers.CharField(read_only=True, allow_null=True, default=None)

    class Meta:
        model = UserActivityLog
        fields = [
            "id",
            "username",
            "ip_address",
            "country",
            "city",
            "device",
            "os",
            "browser",
            "action",
            "time",
        ]
