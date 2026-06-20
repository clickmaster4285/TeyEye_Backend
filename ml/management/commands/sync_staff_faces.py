"""Enroll staff profile photos into DB embeddings and reload the ML service."""

from __future__ import annotations

from django.core.management.base import BaseCommand

from ml.client import MLServiceError, ml_service_enabled
from ml.face_sync import enroll_all_staff_faces, enroll_missing_staff_faces, push_face_embeddings_to_ml


class Command(BaseCommand):
    help = "Enroll staff photos into database face vectors and reload ML from the database."

    def add_arguments(self, parser):
        parser.add_argument(
            "--force",
            action="store_true",
            help="Re-extract embeddings for all staff with photos, even if already enrolled.",
        )
        parser.add_argument(
            "--missing-only",
            action="store_true",
            help="Only enroll staff that have a photo but no current embedding (default).",
        )

    def handle(self, *args, **options):
        force = bool(options.get("force"))
        missing_only = bool(options.get("missing_only")) or not force

        if force:
            enrolled, skipped = enroll_all_staff_faces(push_ml=False, force=True)
        elif missing_only:
            enrolled, skipped = enroll_missing_staff_faces(push_ml=False)
        else:
            enrolled, skipped = enroll_all_staff_faces(push_ml=False)

        self.stdout.write(
            self.style.SUCCESS(f"Enrolled {enrolled} staff face(s) in database (skipped {skipped}).")
        )

        if ml_service_enabled():
            try:
                result = push_face_embeddings_to_ml() or {}
                self.stdout.write(
                    self.style.SUCCESS(
                        f"ML service reloaded from database: {result.get('known_faces', 0)} face(s)."
                    )
                )
            except MLServiceError as exc:
                self.stdout.write(self.style.WARNING(f"Could not reload ML service: {exc}"))
        else:
            self.stdout.write(
                "ML_SERVICE_URL not set — restart ML API or call POST /api/ml/reload-faces/ after starting it."
            )
