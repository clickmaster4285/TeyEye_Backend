from __future__ import annotations

import base64
import logging
import threading
from pathlib import Path

import cv2
import numpy as np
from django.conf import settings
from PIL import Image

from recognition.services.quality_checker import FaceQualityChecker

logger = logging.getLogger(__name__)

_engine = None
_engine_lock = threading.Lock()


def _webcam_threshold() -> float:
    return float(getattr(settings, "ATTENDANCE_WEBCAM_SIMILARITY_THRESHOLD", 0.45))


def _cctv_threshold() -> float:
    return float(getattr(settings, "ATTENDANCE_CCTV_SIMILARITY_THRESHOLD", 0.38))


# Backwards-compatible module constants (resolved at import; settings override in match)
SIMILARITY_THRESHOLD = 0.45
CCTV_SIMILARITY_THRESHOLD = 0.38


def _provider_loads(provider: str) -> bool:
    """True if ORT can create a session with this EP."""
    try:
        from onnx import TensorProto, helper
        import onnxruntime as ort

        graph = helper.make_graph(
            [helper.make_node("Identity", ["x"], ["y"])],
            "probe",
            [helper.make_tensor_value_info("x", TensorProto.FLOAT, [1])],
            [helper.make_tensor_value_info("y", TensorProto.FLOAT, [1])],
        )
        model = helper.make_model(graph, opset_imports=[helper.make_opsetid("", 13)])
        sess = ort.InferenceSession(model.SerializeToString(), providers=[provider])
        active = sess.get_providers()
        return bool(active) and active[0] == provider
    except Exception:
        return False


def _select_onnx_providers() -> list[str]:
    """Prefer CUDA, then DirectML (Windows), else CPU. Override via ATTENDANCE_ONNX_PROVIDERS."""
    import onnxruntime as ort

    override = getattr(settings, "ATTENDANCE_ONNX_PROVIDERS", "") or ""
    if override.strip():
        return [p.strip() for p in override.split(",") if p.strip()]

    available = set(ort.get_available_providers())
    preferred = (
        "CUDAExecutionProvider",
        "DmlExecutionProvider",
        "CPUExecutionProvider",
    )
    providers: list[str] = []
    for name in preferred:
        if name not in available:
            continue
        if name == "CPUExecutionProvider" or _provider_loads(name):
            providers.append(name)
    if not providers:
        providers = ["CPUExecutionProvider"]
    logger.info("ONNX Runtime providers: %s", providers)
    return providers


def get_face_engine():
    global _engine
    if _engine is None:
        with _engine_lock:
            if _engine is None:
                _engine = FaceEngine()
    return _engine


class FaceEngine:
    def __init__(self):
        from insightface.app import FaceAnalysis

        providers = _select_onnx_providers()
        ctx_id = -1 if providers == ["CPUExecutionProvider"] else 0
        self.providers = providers
        model_name = getattr(settings, "ATTENDANCE_INSIGHTFACE_MODEL", "buffalo_l")
        self.app = FaceAnalysis(name=model_name, providers=providers)
        self.app.prepare(ctx_id=ctx_id, det_size=(640, 640))
        self.quality = FaceQualityChecker()
        self._infer_lock = threading.Lock()

    @staticmethod
    def decode_image(image_bytes: bytes) -> np.ndarray:
        arr = np.frombuffer(image_bytes, dtype=np.uint8)
        image = cv2.imdecode(arr, cv2.IMREAD_COLOR)
        if image is None:
            raise ValueError("Invalid image data")
        return image

    @staticmethod
    def decode_base64(data: str) -> np.ndarray:
        if "," in data:
            data = data.split(",", 1)[1]
        return FaceEngine.decode_image(base64.b64decode(data))

    def detect_faces(self, image: np.ndarray):
        with self._infer_lock:
            return self.app.get(image)

    @staticmethod
    def resize_max(image: np.ndarray, max_side: int = 640) -> np.ndarray:
        h, w = image.shape[:2]
        side = max(h, w)
        if side <= max_side:
            return image
        scale = max_side / side
        return cv2.resize(image, (int(w * scale), int(h * scale)), interpolation=cv2.INTER_AREA)

    def get_single_face(self, image: np.ndarray, allow_largest: bool = False):
        faces = self.detect_faces(image)
        if not faces:
            return None, "No face detected"
        if len(faces) > 1 and not allow_largest:
            return None, "Multiple faces detected — only one person allowed"
        if len(faces) == 1:
            return faces[0], None

        def face_area(f):
            x1, y1, x2, y2 = f.bbox
            return max(float(x2 - x1), 1.0) * max(float(y2 - y1), 1.0)

        return max(faces, key=face_area), None

    def extract_embedding(self, image: np.ndarray) -> np.ndarray | None:
        face, error = self.get_single_face(image, allow_largest=True)
        if error:
            return None
        return face.embedding

    def check_quality(self, image: np.ndarray) -> dict:
        small = self.resize_max(image, 640)
        face, error = self.get_single_face(small, allow_largest=True)
        if error:
            return {"passed": False, "message": error}
        result = self.quality.evaluate(small, face)
        result["bbox"] = face.bbox.astype(int).tolist()
        result["image"] = small
        return result

    def generate_embeddings_from_folder(self, folder_path: Path) -> list[np.ndarray]:
        embeddings = []
        for img_path in sorted(folder_path.glob("*.jpg")):
            image = cv2.imread(str(img_path))
            if image is None:
                continue
            image = self.resize_max(image, 640)
            emb = self.extract_embedding(image)
            if emb is not None:
                embeddings.append(emb)
        return embeddings

    @staticmethod
    def average_embedding(embeddings: list[np.ndarray]) -> list[float]:
        if not embeddings:
            return []
        mean = np.mean(np.stack(embeddings), axis=0)
        norm = np.linalg.norm(mean)
        if norm > 0:
            mean = mean / norm
        return mean.tolist()

    def save_dataset_image(self, image: np.ndarray, folder: Path, index: int) -> Path:
        folder.mkdir(parents=True, exist_ok=True)
        path = folder / f"face_{index:03d}.jpg"
        cv2.imwrite(str(path), image)
        return path

    def save_profile_image(self, image: np.ndarray, staff_id: int) -> str:
        profile_dir = Path(settings.MEDIA_ROOT) / "recognition" / "profile"
        profile_dir.mkdir(parents=True, exist_ok=True)
        path = profile_dir / f"staff_{staff_id}.jpg"
        rgb = cv2.cvtColor(image, cv2.COLOR_BGR2RGB)
        Image.fromarray(rgb).save(path, format="JPEG", quality=90)
        return str(path.relative_to(settings.MEDIA_ROOT)).replace("\\", "/")

    def match_embedding(
        self,
        probe: np.ndarray | list[float],
        gallery: dict[str, list[float]],
        threshold: float | None = None,
    ) -> tuple[str | None, float]:
        if not gallery:
            return None, 0.0
        min_sim = _webcam_threshold() if threshold is None else threshold
        probe_vec = np.array(probe, dtype=np.float32)
        norm = np.linalg.norm(probe_vec)
        if norm == 0:
            return None, 0.0
        probe_vec = probe_vec / norm

        best_id = None
        best_sim = -1.0
        for key, stored in gallery.items():
            stored_vec = np.array(stored, dtype=np.float32)
            stored_norm = np.linalg.norm(stored_vec)
            if stored_norm == 0:
                continue
            stored_vec = stored_vec / stored_norm
            sim = float(np.dot(probe_vec, stored_vec))
            if sim > best_sim:
                best_sim = sim
                best_id = key

        if best_sim >= min_sim:
            return best_id, best_sim
        return None, best_sim

    def identify_from_image(
        self,
        image: np.ndarray,
        gallery: dict[str, list[float]],
        threshold: float | None = None,
    ) -> dict:
        face, error = self.get_single_face(image)
        if error:
            return {"matched": False, "message": error, "confidence": 0.0}

        gallery_key, confidence = self.match_embedding(
            face.embedding, gallery, threshold=threshold
        )
        if gallery_key:
            return {
                "matched": True,
                "gallery_key": gallery_key,
                "staff_id": int(gallery_key.replace("staff-", "")) if gallery_key.startswith("staff-") else None,
                "confidence": round(confidence, 4),
                "message": "Face recognized",
            }
        return {
            "matched": False,
            "confidence": round(confidence, 4),
            "message": "Unknown face",
        }
