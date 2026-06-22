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

        from . import signals  # noqa: F401

        def _deferred_clip_boot() -> None:
            try:
                close_old_connections = __import__(
                    "django.db", fromlist=["close_old_connections"]
                ).close_old_connections
                close_old_connections()
                from .clip_capture import requeue_pending_clips

                requeue_pending_clips()
            except Exception:
                logger.exception("[clip-capture] Could not re-queue pending clips")

        try:
            import threading

            threading.Timer(3.0, _deferred_clip_boot).start()
        except Exception:
            logger.exception("[clip-capture] Could not schedule pending clip re-queue")

        try:
            from .detection_worker import maybe_start_background_worker

            maybe_start_background_worker()
        except Exception:
            logger.exception("[detection-worker] Could not start background worker")
