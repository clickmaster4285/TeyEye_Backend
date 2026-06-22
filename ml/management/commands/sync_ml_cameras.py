"""Register active camera RTSP URLs on the ML service (one session per camera key)."""

from __future__ import annotations

from django.core.management.base import BaseCommand

from ml.camera_sync import collect_active_camera_entries, sync_cameras_to_ml
from ml.client import ml_service_enabled


class Command(BaseCommand):
    help = "Push active camera streams to the ML service for direct browser MJPEG."

    def handle(self, *args, **options):
        if not ml_service_enabled():
            self.stderr.write("ML_SERVICE_URL is not configured.")
            return

        entries = collect_active_camera_entries()
        self.stdout.write(f"Found {len(entries)} active camera stream(s).")
        result = sync_cameras_to_ml()
        if result is None:
            self.stderr.write("Camera sync failed — is the ML service running?")
            return
        self.stdout.write(
            self.style.SUCCESS(
                f"Registered {result.get('registered', 0)}/{result.get('total', len(entries))} on ML service."
            )
        )
