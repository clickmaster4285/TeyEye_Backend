import logging
import sys

from django.apps import AppConfig

logger = logging.getLogger(__name__)


class CamerasConfig(AppConfig):
    default_auto_field = "django.db.models.BigAutoField"
    name = "cameras"

    def ready(self):
        if "migrate" in sys.argv or "makemigrations" in sys.argv:
            return
        try:
            from .detection_worker import maybe_start_background_worker

            maybe_start_background_worker()
        except Exception:
            logger.exception("[detection-worker] Could not start background worker")
