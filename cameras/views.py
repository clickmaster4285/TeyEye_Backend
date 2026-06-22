"""Camera registry and ML detection on camera frames."""

from __future__ import annotations

from django.conf import settings
from django.http import StreamingHttpResponse
from django.utils import timezone
from django.utils.dateparse import parse_date
from django_filters.rest_framework import DjangoFilterBackend
from rest_framework import filters, status, viewsets
from rest_framework.authtoken.models import Token
from rest_framework.decorators import action
from rest_framework.permissions import AllowAny, IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from ml.client import (
    MLServiceError,
    ml_detect_image,
    ml_live_detections,
    ml_live_mjpeg_public_url,
    ml_live_mjpeg_raw_public_url,
    ml_service_enabled,
)

from .clip_capture import schedule_detection_clip
from .detection_utils import filter_detections_for_camera, resolve_staff_identity
from .detection_utils import save_detection_batch
from .search_utils import apply_detection_search
from .models import Camera, CameraPurpose, ClipStatus, DetectionEvent, Nvr, Site
from .rtsp_utils import build_rtsp_url_for_preview
from .serializers import (
    BulkCameraCreateSerializer,
    CameraSerializer,
    CameraWriteSerializer,
    DetectionEventSerializer,
    NvrSerializer,
    SiteSerializer,
    nvr_brand_options,
    purpose_options,
)
from .stream_utils import capture_jpeg_frame, ffmpeg_available, generate_mjpeg_frames


def _token_key_from_request(request) -> str | None:
    key = (request.query_params.get("token") or request.GET.get("token") or "").strip()
    if key:
        return key
    auth = (request.META.get("HTTP_AUTHORIZATION") or "").strip()
    if auth.lower().startswith("token "):
        return auth[6:].strip()
    return None


def _request_has_valid_auth(request) -> bool:
    if getattr(request.user, "is_authenticated", False) and request.user.is_authenticated:
        return True
    key = _token_key_from_request(request)
    if not key:
        return False
    return Token.objects.filter(key=key).exists()


def _capture_stream_url(camera: Camera) -> str | None:
    return camera.effective_stream_url() or None


class SiteViewSet(viewsets.ModelViewSet):
    queryset = Site.objects.all()
    serializer_class = SiteSerializer
    permission_classes = [IsAuthenticated]
    filter_backends = [DjangoFilterBackend, filters.SearchFilter, filters.OrderingFilter]
    filterset_fields = ["is_active"]
    search_fields = ["code", "name"]
    ordering_fields = ["name", "code", "created_at"]


class NvrViewSet(viewsets.ModelViewSet):
    queryset = Nvr.objects.select_related("site").all()
    serializer_class = NvrSerializer
    permission_classes = [IsAuthenticated]
    filter_backends = [DjangoFilterBackend, filters.SearchFilter, filters.OrderingFilter]
    filterset_fields = ["site", "brand", "is_active"]
    search_fields = ["name", "ip_address", "site__code", "site__name"]
    ordering_fields = ["name", "ip_address", "created_at"]

    @action(detail=False, methods=["get"], url_path="brands")
    def brands(self, request):
        return Response(nvr_brand_options())

    @action(detail=True, methods=["post"], url_path="bulk-cameras")
    def bulk_cameras(self, request, pk=None):
        """Auto-generate camera entries for channels 1..N on this NVR."""
        nvr = self.get_object()
        serializer = BulkCameraCreateSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        count = serializer.validated_data["channel_count"]
        prefix = serializer.validated_data["name_prefix"]
        zone = serializer.validated_data["zone"]
        purpose = serializer.validated_data["purpose"]

        created = []
        skipped = []
        for ch in range(1, count + 1):
            if Camera.objects.filter(nvr=nvr, channel=ch).exists():
                skipped.append(ch)
                continue
            cam = Camera.objects.create(
                nvr=nvr,
                channel=ch,
                name=f"{prefix} {ch}",
                zone=zone,
                purpose=purpose,
                location=nvr.site.code,
            )
            created.append(CameraSerializer(cam).data)

        return Response(
            {
                "created": created,
                "skipped_channels": skipped,
                "count": len(created),
            },
            status=status.HTTP_201_CREATED if created else status.HTTP_200_OK,
        )


class CameraViewSet(viewsets.ModelViewSet):
    queryset = Camera.objects.select_related("nvr", "nvr__site").all()
    serializer_class = CameraSerializer
    permission_classes = [IsAuthenticated]
    filter_backends = [DjangoFilterBackend, filters.SearchFilter, filters.OrderingFilter]
    filterset_fields = ["nvr", "nvr__site", "location", "purpose", "status", "is_active"]
    search_fields = ["name", "code", "zone", "nvr__name", "nvr__site__code"]
    ordering_fields = ["name", "channel", "location", "created_at"]

    def get_serializer_class(self):
        if self.action in ("create", "update", "partial_update"):
            return CameraWriteSerializer
        return CameraSerializer

    def create(self, request, *args, **kwargs):
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        cam = serializer.save()
        return Response(CameraSerializer(cam).data, status=status.HTTP_201_CREATED)

    def update(self, request, *args, **kwargs):
        partial = kwargs.pop("partial", False)
        cam = self.get_object()
        serializer = self.get_serializer(cam, data=request.data, partial=partial)
        serializer.is_valid(raise_exception=True)
        cam = serializer.save()
        return Response(CameraSerializer(cam).data)

    def partial_update(self, request, *args, **kwargs):
        kwargs["partial"] = True
        return self.update(request, *args, **kwargs)

    @action(detail=False, methods=["get"], url_path="purposes")
    def purposes(self, request):
        return Response(purpose_options())

    @action(detail=False, methods=["get"], url_path="detection-events")
    def detection_events(self, request):
        qs = (
            DetectionEvent.objects.select_related("camera", "camera__nvr", "camera__nvr__site")
            .order_by("-created_at")
        )
        camera_id = request.query_params.get("camera")
        if camera_id:
            qs = qs.filter(camera_id=camera_id)
        site_code = request.query_params.get("site")
        if site_code:
            qs = qs.filter(camera__nvr__site__code__iexact=site_code.strip())
        site_id = request.query_params.get("site_id")
        if site_id:
            qs = qs.filter(camera__nvr__site_id=site_id)
        nvr_id = request.query_params.get("nvr")
        if nvr_id:
            qs = qs.filter(camera__nvr_id=nvr_id)
        channel = request.query_params.get("channel")
        if channel:
            try:
                qs = qs.filter(camera__channel=int(channel))
            except (TypeError, ValueError):
                pass
        zone = request.query_params.get("zone")
        if zone and zone.strip():
            qs = qs.filter(camera__zone__iexact=zone.strip())
        date_from = request.query_params.get("date_from")
        if date_from:
            parsed = parse_date(date_from.strip())
            if parsed:
                qs = qs.filter(created_at__date__gte=parsed)
        date_to = request.query_params.get("date_to")
        if date_to:
            parsed = parse_date(date_to.strip())
            if parsed:
                qs = qs.filter(created_at__date__lte=parsed)
        search_q = request.query_params.get("q") or request.query_params.get("search")
        if search_q and search_q.strip():
            qs = apply_detection_search(qs, search_q.strip())

        try:
            page = max(1, int(request.query_params.get("page", 1)))
        except (TypeError, ValueError):
            page = 1
        try:
            page_size = int(request.query_params.get("page_size", 25))
        except (TypeError, ValueError):
            page_size = 25
        if request.query_params.get("limit") and "page_size" not in request.query_params:
            try:
                page_size = int(request.query_params.get("limit", page_size))
            except (TypeError, ValueError):
                pass
        page_size = min(max(page_size, 1), 100)

        is_alert = request.query_params.get("is_alert")
        if is_alert is not None and str(is_alert).strip().lower() in ("true", "1", "yes"):
            qs = qs.filter(is_alert=True)
        elif is_alert is not None and str(is_alert).strip().lower() in ("false", "0", "no"):
            qs = qs.filter(is_alert=False)

        class_name = request.query_params.get("class_name")
        if class_name and class_name.strip():
            qs = qs.filter(class_name__icontains=class_name.strip())

        total = qs.count()
        offset = (page - 1) * page_size
        events = qs[offset : offset + page_size]
        total_pages = (total + page_size - 1) // page_size if total else 0

        return Response(
            {
                "count": total,
                "page": page,
                "page_size": page_size,
                "total_pages": total_pages,
                "results": DetectionEventSerializer(
                    events, many=True, context={"request": request}
                ).data,
            }
        )

    @action(detail=False, methods=["get"], url_path="detection-summary")
    def detection_summary(self, request):
        today = timezone.localdate()
        qs = DetectionEvent.objects.filter(created_at__date=today)
        alert_count = qs.filter(is_alert=True).count()
        classes = qs.values_list("class_name", flat=True).distinct()
        return Response(
            {
                "detections_today": qs.count(),
                "classes_tracked": len(set(classes)),
                "alerts_today": alert_count,
            }
        )

    @action(detail=True, methods=["get"], url_path="ml-live/detections")
    def ml_live_detections_action(self, request, pk=None):
        camera = self.get_object()
        if not ml_service_enabled():
            return Response(
                {"detail": "ML service is not reachable. Start ml_services: python api_server.py"},
                status=status.HTTP_503_SERVICE_UNAVAILABLE,
            )
        try:
            stream_url = camera.effective_stream_url()
            result = ml_live_detections(camera.stream_key, rtsp_url=stream_url)
        except MLServiceError as exc:
            return Response({"detail": str(exc)}, status=exc.status_code or status.HTTP_503_SERVICE_UNAVAILABLE)

        detections = result.get("detections") or []
        detections = filter_detections_for_camera(camera, detections)
        save_param = request.query_params.get("save", "true").lower()
        saved_count = 0
        if save_param in ("true", "1", "yes") and detections:
            saved_count = save_detection_batch(camera, detections)

        return Response(
            {
                "camera_id": camera.pk,
                "camera_code": camera.code,
                "name": camera.name,
                "site_code": camera.nvr.site.code if camera.nvr_id else "",
                "site_name": camera.nvr.site.name if camera.nvr_id else "",
                "nvr_name": camera.nvr.name if camera.nvr_id else "",
                "nvr_ip": camera.nvr.ip_address if camera.nvr_id else "",
                "channel": camera.channel,
                "zone": camera.zone,
                "purpose": camera.purpose,
                "purpose_label": camera.get_purpose_display(),
                "detections": detections,
                "count": len(detections),
                "saved_count": saved_count,
            }
        )

    @action(detail=True, methods=["post"], url_path="detect")
    def detect(self, request, pk=None):
        camera = self.get_object()
        if not ml_service_enabled():
            return Response(
                {"detail": "ML service is not reachable. Start ml_services: python api_server.py"},
                status=status.HTTP_503_SERVICE_UNAVAILABLE,
            )

        stream = _capture_stream_url(camera)
        if not stream:
            return Response(
                {"detail": "No stream URL could be generated for this camera."},
                status=status.HTTP_400_BAD_REQUEST,
            )

        frame = capture_jpeg_frame(stream)
        if not frame:
            return Response(
                {"detail": "Could not capture a frame from the camera stream. Check NVR credentials and ffmpeg."},
                status=status.HTTP_503_SERVICE_UNAVAILABLE,
            )

        try:
            result = ml_detect_image(frame, filename=f"{camera.code}.jpg", recognize_faces=True)
        except MLServiceError as exc:
            return Response({"detail": str(exc)}, status=exc.status_code or status.HTTP_503_SERVICE_UNAVAILABLE)

        detections = filter_detections_for_camera(camera, result.get("detections") or [])
        saved = []
        clip_enabled = bool(getattr(settings, "DETECTION_CLIP_ENABLED", True))
        for det in detections:
            class_name = str(det.get("class_name", ""))
            label = str(det.get("label", det.get("class_name", "")))
            employee_name, personal_number = resolve_staff_identity(label, class_name)
            event = DetectionEvent.objects.create(
                camera=camera,
                class_name=class_name,
                label=label,
                employee_name=employee_name,
                personal_number=personal_number,
                confidence=float(det.get("confidence", 0)),
                bbox=det.get("bbox") or [],
                is_alert=bool(det.get("alert")),
                clip_status=ClipStatus.PENDING if clip_enabled else ClipStatus.SKIPPED,
            )
            schedule_detection_clip(camera.pk, event.pk)
            saved.append(event)

        return Response(
            {
                "camera_id": camera.pk,
                "camera_code": camera.code,
                "name": camera.name,
                "site_code": camera.nvr.site.code,
                "site_name": camera.nvr.site.name,
                "nvr_name": camera.nvr.name,
                "nvr_ip": camera.nvr.ip_address,
                "channel": camera.channel,
                "detections": detections,
                "count": len(detections),
                "events_saved": len(saved),
            }
        )


class CameraStreamListView(APIView):
    """Dashboard stream metadata from database cameras only."""

    authentication_classes = []
    permission_classes = [AllowAny]

    def get(self, request):
        if not _request_has_valid_auth(request):
            return Response({"detail": "Authentication required."}, status=status.HTTP_401_UNAUTHORIZED)

        cameras = []
        for cam in Camera.objects.filter(is_active=True).select_related("nvr", "nvr__site").order_by(
            "nvr__site__name", "nvr__name", "channel"
        ):
            cameras.append(
                {
                    "id": cam.pk,
                    "code": cam.code,
                    "label": cam.name,
                    "location": cam.location or cam.nvr.site.code,
                    "site_label": cam.nvr.site.name,
                    "site_code": cam.nvr.site.code,
                    "nvr_name": cam.nvr.name,
                    "channel": cam.channel,
                    "purpose": cam.purpose,
                    "purpose_label": cam.get_purpose_display(),
                    "ml_enabled": cam.ml_enabled,
                    "is_rtsp": cam.is_rtsp,
                    "ml_stream_key": cam.stream_key,
                    "ml_live_stream_url": ml_live_mjpeg_public_url(cam.stream_key),
                    "raw_stream_url": ml_live_mjpeg_raw_public_url(cam.stream_key),
                }
            )

        return Response(
            {
                "cameras": cameras,
                "ml_service_enabled": ml_service_enabled(),
                "ml_service_public_url": getattr(settings, "ML_SERVICE_PUBLIC_URL", ""),
            }
        )


class CameraPreviewMjpegView(APIView):
    """Live MJPEG preview for an NVR channel before saving a camera row."""

    authentication_classes = []
    permission_classes = [AllowAny]

    def get(self, request):
        if not _request_has_valid_auth(request):
            return Response({"detail": "Authentication required."}, status=status.HTTP_401_UNAUTHORIZED)

        nvr_id = request.query_params.get("nvr_id")
        channel = request.query_params.get("channel", "1")
        if not nvr_id:
            return Response({"detail": "nvr_id query parameter is required."}, status=status.HTTP_400_BAD_REQUEST)

        if not ffmpeg_available():
            return Response(
                {"detail": "ffmpeg is not installed. Set FFMPEG_PATH in backend/.env."},
                status=status.HTTP_503_SERVICE_UNAVAILABLE,
            )

        try:
            nvr = Nvr.objects.get(pk=int(nvr_id), is_active=True)
            ch = max(1, int(channel))
        except (Nvr.DoesNotExist, ValueError):
            return Response({"detail": "NVR not found or invalid channel."}, status=status.HTTP_404_NOT_FOUND)

        stream_url = build_rtsp_url_for_preview(nvr, ch)
        if not stream_url:
            return Response({"detail": "Could not build RTSP URL."}, status=status.HTTP_400_BAD_REQUEST)

        response = StreamingHttpResponse(
            generate_mjpeg_frames(stream_url),
            content_type="multipart/x-mixed-replace; boundary=frame",
        )
        response["Cache-Control"] = "no-cache, no-store, must-revalidate"
        response["Pragma"] = "no-cache"
        response["X-Accel-Buffering"] = "no"
        return response
