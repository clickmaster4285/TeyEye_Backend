"""Export staff profile photos to the ML known_faces folder for face recognition."""

from __future__ import annotations

import shutil
from pathlib import Path

from django.conf import settings
from django.core.management.base import BaseCommand

from ml.client import MLServiceError, ml_reload_faces, ml_service_enabled
from users.models import Staff


class Command(BaseCommand):
    help = "Sync staff profile images to ML known_faces (filename = username)."

    def handle(self, *args, **options):
        ml_root = Path(settings.ML_ROOT_PATH)
        known_dir = Path(getattr(settings, "ML_KNOWN_FACES_DIR", str(ml_root / "known_faces")))
        known_dir.mkdir(parents=True, exist_ok=True)

        synced = 0
        skipped = 0
        for staff in Staff.objects.select_related("user").filter(user__isnull=False, user__is_deleted=False):
            user = staff.user
            if not user:
                skipped += 1
                continue
            if not staff.profile_image:
                skipped += 1
                continue
            try:
                src = staff.profile_image.path
            except (ValueError, OSError):
                skipped += 1
                continue
            ext = Path(src).suffix.lower() or ".jpg"
            dest = known_dir / f"{user.username}{ext}"
            shutil.copy2(src, dest)
            synced += 1
            self.stdout.write(f"  {user.username} <- {staff.profile_image.name}")

        self.stdout.write(self.style.SUCCESS(f"Synced {synced} face(s) to {known_dir} (skipped {skipped})."))

        if ml_service_enabled():
            try:
                result = ml_reload_faces()
                self.stdout.write(
                    self.style.SUCCESS(f"ML service reloaded: {result.get('known_faces', 0)} known face(s).")
                )
            except MLServiceError as exc:
                self.stdout.write(self.style.WARNING(f"Could not reload ML service: {exc}"))
        else:
            self.stdout.write(
                "ML_SERVICE_URL not set — restart ML API or call POST /api/ml/reload-faces/ after starting it."
            )
