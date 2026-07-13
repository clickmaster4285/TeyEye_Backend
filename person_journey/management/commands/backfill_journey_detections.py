from django.core.management.base import BaseCommand

from person_journey.bridge_detection import backfill_from_detections


class Command(BaseCommand):
    help = "Backfill Person Journey from recent person DetectionEvents."

    def add_arguments(self, parser):
        parser.add_argument("--hours", type=int, default=24, help="Look back window in hours")
        parser.add_argument("--limit", type=int, default=500, help="Max events to process")

    def handle(self, *args, **options):
        count = backfill_from_detections(hours=options["hours"], limit=options["limit"])
        self.stdout.write(self.style.SUCCESS(f"Bridged {count} person detection(s) into journey."))
