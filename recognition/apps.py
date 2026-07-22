import os
import sys

from django.apps import AppConfig
from django.conf import settings


class RecognitionConfig(AppConfig):
    default_auto_field = "django.db.models.BigAutoField"
    name = "recognition"
    verbose_name = "Face Recognition Attendance"

    def ready(self):
        if not getattr(settings, "ATTENDANCE_CCTV_AUTOSTART", True):
            return

        # Skip management commands (migrate, shell, test, ...) — only start
        # with a real server process.
        argv = " ".join(sys.argv).lower()
        is_runserver = "runserver" in argv
        is_wsgi_server = any(k in argv for k in ("gunicorn", "daphne", "uvicorn", "waitress"))
        if not (is_runserver or is_wsgi_server):
            return

        # Under runserver the autoreloader spawns two processes; only the
        # child with RUN_MAIN=true serves requests.
        if is_runserver and os.environ.get("RUN_MAIN") != "true":
            return

        from recognition.services.autostart import schedule_autostart

        schedule_autostart(delay_seconds=3.0)
