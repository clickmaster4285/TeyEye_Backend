from rest_framework import viewsets, status
from rest_framework.pagination import PageNumberPagination
from rest_framework.permissions import IsAuthenticated
from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework.request import Request
from .models import UserActivityLog
from .serializers import ActivityLogSerializer
from .middleware import create_activity_log


class ActivityLogPagination(PageNumberPagination):
    page_size = 50
    page_size_query_param = "page_size"
    max_page_size = 200


class ActivityLogViewSet(viewsets.ReadOnlyModelViewSet):
    """List and retrieve user activity logs. Newest first. Requires authentication."""
    queryset = UserActivityLog.objects.all().select_related("user").order_by("-time")
    serializer_class = ActivityLogSerializer
    permission_classes = [IsAuthenticated]
    pagination_class = ActivityLogPagination


class ReportActivityView(APIView):
    """POST /api/activity-logs/report/ with { \"action\": \"Viewed /settings/logs\" } to record app-level actions."""
    permission_classes = [IsAuthenticated]

    def post(self, request: Request):
        action = (request.data.get("action") or "").strip()
        if not action:
            return Response({"detail": "action is required"}, status=status.HTTP_400_BAD_REQUEST)
        create_activity_log(request.user, request, action[:255])
        return Response({"ok": True}, status=status.HTTP_201_CREATED)
