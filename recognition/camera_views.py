from django.http import HttpResponse
from rest_framework import status
from rest_framework.response import Response
from rest_framework.views import APIView

from cameras.models import Camera, CameraPurpose, CameraStatus
from recognition.models import DetectionSnapshot
from recognition.serializers import DetectionSnapshotSerializer
from recognition.services.cctv_worker import get_cctv_manager
from recognition.services.snapshot_saver import snapshot_to_dict
from users.permissions import IsAdminOrHR


def _attendance_cameras():
    """Active cameras suitable for InsightFace CCTV attendance."""
    purposes = [
        CameraPurpose.ATTENDANCE,
        CameraPurpose.FACE_RECOGNITION,
        CameraPurpose.SURVEILLANCE,
        CameraPurpose.ZONE_MONITORING,
    ]
    return (
        Camera.objects.filter(is_active=True, purpose__in=purposes)
        .select_related("nvr")
        .order_by("code", "id")
    )


def _camera_payload(camera: Camera, manager) -> dict:
    runtime = manager.get_status(camera.id) if manager else None
    return {
        "id": camera.id,
        "name": camera.name or camera.code or f"Camera {camera.id}",
        "location": camera.zone or "",
        "code": camera.code,
        "purpose": camera.purpose,
        "status": camera.status,
        "is_active": camera.is_active and camera.status == CameraStatus.ONLINE,
        "runtime": runtime,
    }


class CCTVControlView(APIView):
    permission_classes = [IsAdminOrHR]

    def get(self, request):
        manager = get_cctv_manager()
        cameras = list(_attendance_cameras())
        recent = (
            DetectionSnapshot.objects.select_related("staff", "camera")
            .order_by("-detected_at")[:24]
        )
        return Response({
            "cameras": [_camera_payload(c, manager) for c in cameras],
            "events": manager.get_events(limit=40),
            "snapshots": [snapshot_to_dict(s) for s in recent],
            "running_count": sum(1 for s in manager.list_status() if s["running"]),
        })

    def post(self, request):
        action_name = request.data.get("action", "start_all")
        manager = get_cctv_manager()

        if action_name == "start_all":
            cameras = []
            for cam in _attendance_cameras():
                try:
                    url = cam.effective_stream_url()
                except Exception:
                    continue
                if not url:
                    continue
                cameras.append({
                    "id": cam.id,
                    "name": cam.name or cam.code or f"Camera {cam.id}",
                    "rtsp_url": url,
                })
            statuses = manager.start_all(cameras)
            return Response({"action": "start_all", "statuses": statuses})

        if action_name == "stop_all":
            statuses = manager.stop_all()
            return Response({"action": "stop_all", "statuses": statuses})

        return Response(
            {"error": "Unknown action. Use start_all or stop_all."},
            status=status.HTTP_400_BAD_REQUEST,
        )


class CCTVCameraActionView(APIView):
    permission_classes = [IsAdminOrHR]

    def post(self, request, camera_id, action_name):
        camera = Camera.objects.filter(pk=camera_id).select_related("nvr").first()
        if not camera:
            return Response({"error": "Camera not found"}, status=status.HTTP_404_NOT_FOUND)

        manager = get_cctv_manager()
        if action_name == "start":
            if not camera.is_active:
                return Response(
                    {"error": "Camera is inactive"},
                    status=status.HTTP_400_BAD_REQUEST,
                )
            try:
                url = camera.effective_stream_url()
            except Exception as exc:
                return Response({"error": str(exc)}, status=status.HTTP_400_BAD_REQUEST)
            runtime = manager.start_camera(
                camera.id,
                camera.name or camera.code or f"Camera {camera.id}",
                url,
            )
            return Response({"camera": _camera_payload(camera, manager), "runtime": runtime})

        if action_name == "stop":
            runtime = manager.stop_camera(camera.id)
            return Response({"runtime": runtime})

        return Response({"error": "Unknown action"}, status=status.HTTP_400_BAD_REQUEST)

    def get(self, request, camera_id, action_name):
        camera = Camera.objects.filter(pk=camera_id).first()
        if not camera:
            return Response({"error": "Camera not found"}, status=status.HTTP_404_NOT_FOUND)

        manager = get_cctv_manager()
        if action_name == "snapshot":
            jpeg = manager.get_snapshot_jpeg(camera.id)
            if not jpeg:
                return Response(
                    {"error": "No snapshot available. Start the camera first."},
                    status=status.HTTP_404_NOT_FOUND,
                )
            return HttpResponse(jpeg, content_type="image/jpeg")

        if action_name == "status":
            return Response({
                "camera_id": camera.id,
                "name": camera.name or camera.code,
                "runtime": manager.get_status(camera.id),
            })

        return Response({"error": "Unknown action"}, status=status.HTTP_400_BAD_REQUEST)


class CCTVEventsView(APIView):
    permission_classes = [IsAdminOrHR]

    def get(self, request):
        camera_id = request.query_params.get("camera_id")
        manager = get_cctv_manager()
        events = manager.get_events(
            camera_id=int(camera_id) if camera_id else None,
            limit=50,
        )
        return Response({"events": events})


class DetectionSnapshotListView(APIView):
    permission_classes = [IsAdminOrHR]

    def get(self, request):
        qs = DetectionSnapshot.objects.select_related("staff", "camera").order_by("-detected_at")
        camera_id = request.query_params.get("camera_id")
        staff_id = request.query_params.get("staff_id")
        if camera_id:
            qs = qs.filter(camera_id=camera_id)
        if staff_id:
            qs = qs.filter(staff_id=staff_id)
        limit = min(int(request.query_params.get("limit", 40)), 100)
        serializer = DetectionSnapshotSerializer(qs[:limit], many=True)
        return Response({"snapshots": serializer.data})
