"""Run the detection worker as a dedicated long-lived process (systemd)."""

import os
import signal

from django.core.management.base import BaseCommand

from cameras.detection_worker import run_worker_forever, stop_background_worker


class Command(BaseCommand):
    help = "Poll ML live detections for all active cameras and save readings to the database."

    def handle(self, *args, **options):
        os.environ["TEKEYE_DETECTION_WORKER"] = "1"

        def _shutdown(signum, _frame):
            self.stdout.write(self.style.WARNING(f"Stopping detection worker (signal {signum})…"))
            stop_background_worker()

        signal.signal(signal.SIGINT, _shutdown)
        signal.signal(signal.SIGTERM, _shutdown)

        self.stdout.write(self.style.SUCCESS("Detection worker running — Ctrl+C to stop"))
        run_worker_forever()
