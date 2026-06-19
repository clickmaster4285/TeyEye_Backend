"""Remove cameras without an NVR assignment."""

from django.core.management.base import BaseCommand

from cameras.models import Camera


class Command(BaseCommand):
    help = "Delete cameras not linked to an NVR."

    def handle(self, *args, **options):
        qs = Camera.objects.filter(nvr__isnull=True)
        count = qs.count()
        qs.delete()
        self.stdout.write(self.style.SUCCESS(f"Removed {count} invalid camera record(s)."))
