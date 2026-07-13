"""Backfill journey event snapshots — one crop image per timeline record."""

from __future__ import annotations

from datetime import timedelta

from django.core.management.base import BaseCommand
from django.utils import timezone


class Command(BaseCommand):
    help = "Capture missing journey crop snapshots (one image per event)."

    def add_arguments(self, parser):
        parser.add_argument("--hours", type=int, default=0, help="Only events from last N hours (0 = all)")
        parser.add_argument("--capture-limit", type=int, default=200, help="Max captures to run")
        parser.add_argument("--person-uuid", type=str, default="", help="Limit to one journey person UUID")
        parser.add_argument(
            "--force",
            action="store_true",
            help="Re-capture even when a snapshot already exists (e.g. upgrade to 4K)",
        )

    def handle(self, *args, **options):
        from person_journey.models import JourneyEvent, JourneyPerson
        from person_journey.snapshot_capture import capture_journey_crop_sync

        hours = int(options["hours"])
        capture_limit = max(1, int(options["capture_limit"]))
        person_uuid = (options["person_uuid"] or "").strip()
        force = bool(options["force"])

        qs = JourneyEvent.objects.filter(camera__isnull=False)
        if not force:
            qs = qs.filter(snapshot_path="")
        if person_uuid:
            qs = qs.filter(journey_person__uuid=person_uuid)
        if hours > 0:
            since = timezone.now() - timedelta(hours=hours)
            qs = qs.filter(created_at__gte=since)

        event_ids = list(qs.order_by("-created_at").values_list("id", flat=True)[:capture_limit])
        captured = 0
        for ev_id in event_ids:
            if force:
                JourneyEvent.objects.filter(pk=ev_id).update(snapshot_path="")
            url = capture_journey_crop_sync(ev_id)
            if url:
                captured += 1
                if captured % 10 == 0:
                    self.stdout.write(f"  captured {captured}...")

        self.stdout.write(
            self.style.SUCCESS(
                f"Done: captured {captured}/{len(event_ids)} journey snapshots"
            )
        )
