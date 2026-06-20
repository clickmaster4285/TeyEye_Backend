import logging
import os
import sys
import threading

from django.apps import AppConfig

logger = logging.getLogger(__name__)


class MlConfig(AppConfig):
    default_auto_field = "django.db.models.BigAutoField"
    name = "ml"

    def ready(self):
        # runserver autoreload parent — skip; gunicorn / worker have no RUN_MAIN
        if "runserver" in sys.argv and os.environ.get("RUN_MAIN") != "true":
            return
        if "migrate" in sys.argv or "makemigrations" in sys.argv:
            return

        from .autostart import maybe_start_ml_service

        maybe_start_ml_service()

        def _deferred_face_reload() -> None:
            try:
                close_old_connections = __import__(
                    "django.db", fromlist=["close_old_connections"]
                ).close_old_connections
                close_old_connections()
                from .face_sync import enroll_missing_staff_faces, push_face_embeddings_to_ml

                enrolled, skipped = enroll_missing_staff_faces(push_ml=False)
                if enrolled:
                    logger.info("[face-sync] Auto-enrolled %s staff face(s) on startup (skipped %s)", enrolled, skipped)
                result = push_face_embeddings_to_ml()
                if result:
                    logger.info(
                        "[face-sync] ML known faces loaded: %s (%s from DB)",
                        result.get("known_faces", 0),
                        result.get("db_embeddings", 0),
                    )
            except Exception:
                logger.exception("[face-sync] Could not push face embeddings to ML")

        try:
            threading.Timer(5.0, _deferred_face_reload).start()
        except Exception:
            logger.exception("[face-sync] Could not schedule ML face reload")
