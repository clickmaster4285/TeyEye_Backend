from django.urls import path

from recognition.camera_views import (
    CCTVCameraActionView,
    CCTVControlView,
    CCTVEventsView,
    DetectionSnapshotListView,
)
from recognition.dashboard_views import DailyReportView, DashboardSummaryView
from recognition.views import (
    CaptureFaceView,
    EnrollmentStatusView,
    GalleryStatsView,
    IdentifyFaceView,
    TrainEmbeddingsView,
)

urlpatterns = [
    path("gallery/stats/", GalleryStatsView.as_view(), name="gallery-stats"),
    path("identify/", IdentifyFaceView.as_view(), name="identify-face"),
    path("cctv/", CCTVControlView.as_view(), name="cctv-control"),
    path("cctv/events/", CCTVEventsView.as_view(), name="cctv-events"),
    path(
        "cctv/cameras/<int:camera_id>/<str:action_name>/",
        CCTVCameraActionView.as_view(),
        name="cctv-camera-action",
    ),
    path("detections/", DetectionSnapshotListView.as_view(), name="detection-snapshots"),
    path("enroll/<int:staff_id>/", EnrollmentStatusView.as_view(), name="enrollment-status"),
    path("enroll/<int:staff_id>/capture/", CaptureFaceView.as_view(), name="capture-face"),
    path("enroll/<int:staff_id>/train/", TrainEmbeddingsView.as_view(), name="train-embeddings"),
    path("dashboard/summary/", DashboardSummaryView.as_view(), name="attendance-dashboard-summary"),
    path("dashboard/daily-report/", DailyReportView.as_view(), name="attendance-daily-report"),
]
