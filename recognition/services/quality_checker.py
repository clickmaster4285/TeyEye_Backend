import cv2
import numpy as np


class FaceQualityChecker:
    """Quality gates for webcam enrollment images."""

    MIN_FACE_AREA_RATIO = 0.02
    MIN_DET_SCORE = 0.5
    MIN_BLUR_VARIANCE = 40.0

    @staticmethod
    def laplacian_blur_score(image: np.ndarray) -> float:
        if image is None or image.size == 0:
            return 0.0
        gray = cv2.cvtColor(image, cv2.COLOR_BGR2GRAY) if len(image.shape) == 3 else image
        return float(cv2.Laplacian(gray, cv2.CV_64F).var())

    @classmethod
    def evaluate(cls, image: np.ndarray, face) -> dict:
        h, w = image.shape[:2]
        bbox = face.bbox.astype(int)
        x1, y1, x2, y2 = [int(v) for v in bbox]
        x1, y1 = max(0, x1), max(0, y1)
        x2, y2 = min(w, x2), min(h, y2)
        face_w = max(x2 - x1, 1)
        face_h = max(y2 - y1, 1)
        face_area_ratio = (face_w * face_h) / (w * h)
        det_score = float(getattr(face, "det_score", 0.0))
        crop = image[y1:y2, x1:x2]
        blur_score = cls.laplacian_blur_score(crop)

        checks = {
            "det_score_ok": det_score >= cls.MIN_DET_SCORE,
            "face_size_ok": face_area_ratio >= cls.MIN_FACE_AREA_RATIO,
            "blur_ok": blur_score >= cls.MIN_BLUR_VARIANCE,
        }
        passed = all(checks.values())

        return {
            "passed": passed,
            "det_score": round(det_score, 4),
            "face_area_ratio": round(face_area_ratio, 4),
            "blur_score": round(blur_score, 2),
            "checks": checks,
            "message": cls._message(checks),
        }

    @staticmethod
    def _message(checks: dict) -> str:
        if checks["det_score_ok"] and checks["face_size_ok"] and checks["blur_ok"]:
            return "Face quality acceptable"
        if not checks["det_score_ok"]:
            return "Face detection confidence too low — move closer and face the camera"
        if not checks["face_size_ok"]:
            return "Face too small — move closer to the camera"
        if not checks["blur_ok"]:
            return "Image too blurry — hold still and improve lighting"
        return "Face quality check failed"
