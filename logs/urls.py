from django.urls import path, include
from rest_framework.routers import DefaultRouter
from .views import ActivityLogViewSet, ReportActivityView

router = DefaultRouter()
router.register(r"activity-logs", ActivityLogViewSet, basename="activity-log")

urlpatterns = [
    path("activity-logs/report/", ReportActivityView.as_view(), name="activity-log-report"),
    path("", include(router.urls)),
]
