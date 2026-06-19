from django.db import models
from django.conf import settings


class UserActivityLog(models.Model):
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True
    )
    ip_address = models.GenericIPAddressField(null=True, blank=True)
    country = models.CharField(max_length=100, null=True, blank=True)
    city = models.CharField(max_length=100, null=True, blank=True)
    device = models.CharField(max_length=50, null=True, blank=True)
    os = models.CharField(max_length=50, null=True, blank=True)
    browser = models.CharField(max_length=50, null=True, blank=True)
    action = models.CharField(max_length=255)
    time = models.DateTimeField(auto_now_add=True)

    @property
    def username(self):
        return self.user.username if self.user_id else None

    def __str__(self):
        return f"{self.user} - {self.action}"