import os

from django.apps import AppConfig


class MlConfig(AppConfig):
    default_auto_field = "django.db.models.BigAutoField"
    name = "ml"

    def ready(self):
        if os.environ.get("RUN_MAIN") != "true":
            return
        from .autostart import maybe_start_ml_service

        maybe_start_ml_service()
