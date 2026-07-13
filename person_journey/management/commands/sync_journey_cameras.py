from django.core.management.base import BaseCommand

from person_journey.journey_worker import sync_cameras_to_journey_ml


class Command(BaseCommand):
    help = "Sync active cameras to the ML Person Journey pipeline (ByteTrack + ReID)."

    def handle(self, *args, **options):
        result = sync_cameras_to_journey_ml()
        self.stdout.write(self.style.SUCCESS(str(result)))
