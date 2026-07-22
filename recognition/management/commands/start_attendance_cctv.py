from django.core.management.base import BaseCommand

from cameras.models import Camera, CameraPurpose
from recognition.services.cctv_worker import get_cctv_manager


class Command(BaseCommand):
    help = "Start InsightFace CCTV attendance workers for online attendance cameras (managed, not auto)."

    def add_arguments(self, parser):
        parser.add_argument(
            "--stop",
            action="store_true",
            help="Stop all running attendance CCTV workers instead of starting.",
        )

    def handle(self, *args, **options):
        manager = get_cctv_manager()
        if options["stop"]:
            statuses = manager.stop_all()
            self.stdout.write(self.style.SUCCESS(f"Stopped {len(statuses)} workers"))
            return

        purposes = [
            CameraPurpose.ATTENDANCE,
            CameraPurpose.FACE_RECOGNITION,
            CameraPurpose.SURVEILLANCE,
            CameraPurpose.ZONE_MONITORING,
        ]
        cameras = []
        for cam in Camera.objects.filter(is_active=True, purpose__in=purposes).select_related("nvr"):
            try:
                url = cam.effective_stream_url()
            except Exception as exc:
                self.stderr.write(f"Skip camera {cam.id}: {exc}")
                continue
            if not url:
                continue
            cameras.append({
                "id": cam.id,
                "name": cam.name or cam.code or f"Camera {cam.id}",
                "rtsp_url": url,
            })

        statuses = manager.start_all(cameras)
        self.stdout.write(self.style.SUCCESS(f"Started {len(statuses)} CCTV attendance workers"))
        for s in statuses:
            self.stdout.write(f"  camera {s['camera_id']}: running={s['running']}")
