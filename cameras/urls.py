from django.urls import include, path
from rest_framework.routers import DefaultRouter

from .views import (
    CameraMlLiveMjpegView,
    CameraMjpegStreamView,
    CameraPreviewMjpegView,
    CameraStreamListView,
    CameraViewSet,
    NvrViewSet,
    SiteViewSet,
)

router = DefaultRouter()
router.register(r"sites", SiteViewSet, basename="site")
router.register(r"nvrs", NvrViewSet, basename="nvr")
router.register(r"cameras", CameraViewSet, basename="camera")

urlpatterns = [
    path("cameras/streams/", CameraStreamListView.as_view(), name="camera-stream-list"),
    path(
        "cameras/streams/<int:camera_id>/mjpeg/",
        CameraMjpegStreamView.as_view(),
        name="camera-mjpeg-stream",
    ),
    path("cameras/preview/mjpeg/", CameraPreviewMjpegView.as_view(), name="camera-preview-mjpeg"),
    path(
        "cameras/<int:camera_id>/ml-live/mjpeg/",
        CameraMlLiveMjpegView.as_view(),
        name="camera-ml-live-mjpeg",
    ),
    path("", include(router.urls)),
]
