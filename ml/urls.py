from django.urls import path

from .views import (
  MLDetectImageAPIView,
  MLHealthAPIView,
  MLReloadFacesAPIView,
  MLValidateHumanFaceAPIView,
)

urlpatterns = [
  path("ml/health/", MLHealthAPIView.as_view(), name="ml-health"),
  path("ml/detect/", MLDetectImageAPIView.as_view(), name="ml-detect"),
  path("ml/validate/human-face/", MLValidateHumanFaceAPIView.as_view(), name="ml-validate-face"),
  path("ml/reload-faces/", MLReloadFacesAPIView.as_view(), name="ml-reload-faces"),
]
