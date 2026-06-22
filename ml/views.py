from rest_framework import permissions, status
from rest_framework.parsers import FormParser, MultiPartParser
from rest_framework.response import Response
from rest_framework.views import APIView

from .client import (
    MLServiceError,
    ml_detect_image,
    ml_health,
    ml_reload_faces,
    ml_service_enabled,
    ml_validate_human_face,
)
from .face_sync import collect_db_face_embeddings


class MLHealthAPIView(APIView):
    permission_classes = [permissions.IsAuthenticated]

    def get(self, request):
        if not ml_service_enabled():
            return Response(
                {
                    "status": "disabled",
                    "message": "Set ML_SERVICE_URL in backend/.env and start ml_services/api_server.py.",
                },
                status=status.HTTP_503_SERVICE_UNAVAILABLE,
            )
        try:
            data = ml_health()
        except MLServiceError as exc:
            return Response(
                {"status": "error", "message": str(exc)},
                status=exc.status_code or status.HTTP_503_SERVICE_UNAVAILABLE,
            )
        return Response({"status": "ok", **data})


class MLDetectImageAPIView(APIView):
    permission_classes = [permissions.IsAuthenticated]
    parser_classes = [MultiPartParser, FormParser]

    def post(self, request):
        image = request.FILES.get("image")
        if not image:
            return Response({"detail": "image file is required."}, status=400)
        try:
            result = ml_detect_image(image.read(), filename=image.name or "image.jpg")
        except MLServiceError as exc:
            return Response({"detail": str(exc)}, status=exc.status_code or 503)
        return Response(result)


class MLValidateHumanFaceAPIView(APIView):
    permission_classes = [permissions.IsAuthenticated]
    parser_classes = [MultiPartParser, FormParser]

    def post(self, request):
        image = request.FILES.get("image")
        if not image:
            return Response({"detail": "image file is required."}, status=400)
        try:
            result = ml_validate_human_face(image.read(), filename=image.name or "face.jpg")
        except MLServiceError as exc:
            return Response({"detail": str(exc)}, status=exc.status_code or 503)
        return Response(result)


class MLReloadFacesAPIView(APIView):
    permission_classes = [permissions.IsAuthenticated]

    def post(self, request):
        try:
            result = ml_reload_faces(embeddings=collect_db_face_embeddings())
        except MLServiceError as exc:
            return Response({"detail": str(exc)}, status=exc.status_code or 503)
        return Response(result)
