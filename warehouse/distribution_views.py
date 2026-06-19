from django.utils import timezone
from rest_framework import permissions, status
from rest_framework.response import Response
from rest_framework.views import APIView

from cameras.models import Camera
from users.models import User

from .distribution_service import (
    DESTRUCTION_ALERT_ROLES,
    complete_distribution,
    report_destruction_detection,
    start_distribution_recording,
    sync_stock_items,
)
from .models import DestructionAlert, FireSmokeDetectionLog, MemoDistribution, WarehouseStockItem
from .serializers import (
    DestructionAlertSerializer,
    FireSmokeDetectionLogSerializer,
    MemoDistributionSerializer,
    WarehouseStockItemSerializer,
)


class SyncWarehouseStockAPIView(APIView):
    permission_classes = [permissions.IsAuthenticated]

    def post(self, request):
        rows = request.data.get("items") or request.data.get("rows") or []
        if not isinstance(rows, list):
            return Response({"detail": "items must be a list."}, status=status.HTTP_400_BAD_REQUEST)
        created = sync_stock_items(rows)
        return Response({"synced": len(rows), "created": created})


class WarehouseStockListAPIView(APIView):
    permission_classes = [permissions.IsAuthenticated]

    def get(self, request):
        case_ref = (request.query_params.get("case_ref") or "").strip()
        memo_id = (request.query_params.get("detention_memo_id") or "").strip()
        qs = WarehouseStockItem.objects.all()
        if memo_id:
            qs = qs.filter(detention_memo_id=memo_id)
        if case_ref:
            qs = qs.filter(case_ref__icontains=case_ref)
        return Response(WarehouseStockItemSerializer(qs[:200], many=True).data)


class MemoDistributionStartAPIView(APIView):
    permission_classes = [permissions.IsAuthenticated]

    def post(self, request):
        memo_id = (request.data.get("detention_memo_id") or "").strip()
        camera_id = request.data.get("camera_id")
        camera_ids = request.data.get("camera_ids") or []
        selected_items = request.data.get("selected_items") or []

        if not memo_id:
            return Response({"detail": "detention_memo_id is required."}, status=status.HTTP_400_BAD_REQUEST)

        ids: list[int] = []
        if isinstance(camera_ids, list) and camera_ids:
            ids = [int(c) for c in camera_ids]
        elif camera_id:
            ids = [int(camera_id)]
        if not ids:
            return Response(
                {"detail": "camera_ids (or camera_id) is required."},
                status=status.HTTP_400_BAD_REQUEST,
            )

        cameras = list(Camera.objects.filter(pk__in=ids, is_active=True).order_by("name"))
        if len(cameras) != len(set(ids)):
            return Response({"detail": "One or more cameras were not found."}, status=status.HTTP_404_NOT_FOUND)

        try:
            session = start_distribution_recording(
                detention_memo_id=memo_id,
                cameras=cameras,
                selected_items=selected_items if isinstance(selected_items, list) else [],
                performed_by=getattr(request.user, "username", "") or "",
            )
        except ValueError as exc:
            return Response({"detail": str(exc)}, status=status.HTTP_400_BAD_REQUEST)
        except FileNotFoundError as exc:
            return Response({"detail": str(exc)}, status=status.HTTP_503_SERVICE_UNAVAILABLE)
        return Response(
            MemoDistributionSerializer(session, context={"request": request}).data,
            status=status.HTTP_201_CREATED,
        )


class MemoDistributionCompleteAPIView(APIView):
    permission_classes = [permissions.IsAuthenticated]

    def post(self, request, session_id):
        try:
            session = complete_distribution(str(session_id))
        except ValueError as exc:
            return Response({"detail": str(exc)}, status=status.HTTP_400_BAD_REQUEST)
        except Exception as exc:
            return Response({"detail": str(exc)}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)
        return Response(MemoDistributionSerializer(session, context={"request": request}).data)


class MemoDistributionDetectionAPIView(APIView):
    """Report smoke/fire ML detections during an active destruction session."""

    permission_classes = [permissions.IsAuthenticated]

    def post(self, request, session_id):
        camera_id = request.data.get("camera_id")
        detections = request.data.get("detections") or []
        if not camera_id:
            return Response({"detail": "camera_id is required."}, status=status.HTTP_400_BAD_REQUEST)
        if not isinstance(detections, list):
            return Response({"detail": "detections must be a list."}, status=status.HTTP_400_BAD_REQUEST)
        try:
            log, alert = report_destruction_detection(
                str(session_id),
                camera_id=int(camera_id),
                detections=detections,
            )
        except ValueError as exc:
            return Response({"detail": str(exc)}, status=status.HTTP_400_BAD_REQUEST)
        if log is None:
            return Response({"log_created": False, "alert_created": False})
        payload = {
            "log_created": True,
            "log": FireSmokeDetectionLogSerializer(log, context={"request": request}).data,
            "alert_created": alert is not None,
        }
        if alert is not None:
            payload["alert"] = DestructionAlertSerializer(alert, context={"request": request}).data
        return Response(payload, status=status.HTTP_201_CREATED)


class MemoDistributionListAPIView(APIView):
    permission_classes = [permissions.IsAuthenticated]

    def get(self, request):
        memo_id = (request.query_params.get("detention_memo_id") or "").strip()
        case_ref = (request.query_params.get("case_ref") or "").strip()
        qs = MemoDistribution.objects.select_related("camera").order_by("-created_at")
        if memo_id:
            qs = qs.filter(detention_memo_id=memo_id)
        if case_ref:
            qs = qs.filter(detention_case_no__icontains=case_ref)
        return Response(
            MemoDistributionSerializer(qs[:100], many=True, context={"request": request}).data
        )


class MemoDistributionDetailAPIView(APIView):
    permission_classes = [permissions.IsAuthenticated]

    def get(self, request, session_id):
        try:
            session = MemoDistribution.objects.select_related("camera").get(pk=session_id)
        except MemoDistribution.DoesNotExist:
            return Response({"detail": "Destruction record not found."}, status=status.HTTP_404_NOT_FOUND)
        return Response(
            MemoDistributionSerializer(
                session,
                context={"request": request, "repair_recordings": True},
            ).data
        )


class DestructionAlertListAPIView(APIView):
    permission_classes = [permissions.IsAuthenticated]

    def get(self, request):
        user: User = request.user
        role = getattr(user, "role", "") or ""
        location = getattr(user, "location", "") or ""
        qs = DestructionAlert.objects.select_related("camera").order_by("-created_at")

        if role == "ADMIN":
            pass
        elif role in DESTRUCTION_ALERT_ROLES:
            if location:
                qs = qs.filter(location_code=location)
            else:
                qs = qs.filter(notified_user_ids__contains=[user.pk])
        else:
            qs = qs.filter(notified_user_ids__contains=[user.pk])

        session_id = (request.query_params.get("distribution_id") or "").strip()
        if session_id:
            qs = qs.filter(distribution_id=session_id)

        unack_only = (request.query_params.get("unacknowledged") or "").lower() in ("1", "true", "yes")
        if unack_only:
            qs = qs.filter(acknowledged=False)

        return Response(
            DestructionAlertSerializer(qs[:100], many=True, context={"request": request}).data
        )


class FireSmokeLogListAPIView(APIView):
    permission_classes = [permissions.IsAuthenticated]

    def get(self, request):
        user: User = request.user
        role = getattr(user, "role", "") or ""
        location = getattr(user, "location", "") or ""
        qs = FireSmokeDetectionLog.objects.select_related("camera", "distribution").order_by("-created_at")

        if role == "ADMIN":
            pass
        elif role in DESTRUCTION_ALERT_ROLES:
            if location:
                qs = qs.filter(location_code=location)
        else:
            qs = qs.filter(performed_by=getattr(user, "username", "") or "")

        distribution_id = (request.query_params.get("distribution_id") or "").strip()
        if distribution_id:
            qs = qs.filter(distribution_id=distribution_id)

        memo_id = (request.query_params.get("detention_memo_id") or "").strip()
        if memo_id:
            qs = qs.filter(detention_memo_id=memo_id)

        camera_id = (request.query_params.get("camera_id") or "").strip()
        if camera_id:
            qs = qs.filter(camera_id=camera_id)

        location_code = (request.query_params.get("location_code") or "").strip()
        if location_code:
            qs = qs.filter(location_code=location_code)

        return Response(
            FireSmokeDetectionLogSerializer(qs[:200], many=True, context={"request": request}).data
        )


class DestructionAlertAcknowledgeAPIView(APIView):
    permission_classes = [permissions.IsAuthenticated]

    def post(self, request, alert_id):
        try:
            alert = DestructionAlert.objects.get(pk=alert_id)
        except DestructionAlert.DoesNotExist:
            return Response({"detail": "Alert not found."}, status=status.HTTP_404_NOT_FOUND)

        user: User = request.user
        role = getattr(user, "role", "") or ""
        if role not in DESTRUCTION_ALERT_ROLES:
            return Response({"detail": "Not permitted."}, status=status.HTTP_403_FORBIDDEN)

        alert.acknowledged = True
        alert.acknowledged_at = timezone.now()
        alert.acknowledged_by = getattr(user, "username", "") or ""
        alert.save(update_fields=["acknowledged", "acknowledged_at", "acknowledged_by"])
        return Response(DestructionAlertSerializer(alert, context={"request": request}).data)
