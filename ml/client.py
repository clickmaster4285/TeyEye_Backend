"""HTTP client for the external ML inference service (ml_services/api_server.py)."""

from __future__ import annotations

from typing import Any
from urllib.parse import urlencode

import requests
from django.conf import settings


class MLServiceError(Exception):
    def __init__(self, message: str, status_code: int | None = None):
        super().__init__(message)
        self.status_code = status_code


def ml_service_enabled() -> bool:
    return bool(getattr(settings, "ML_SERVICE_URL", "").strip())


def _base_url() -> str:
    url = getattr(settings, "ML_SERVICE_URL", "").strip().rstrip("/")
    if not url:
        raise MLServiceError("ML service is not configured. Set ML_SERVICE_URL in .env.", 503)
    return url


def _timeout() -> int:
    return int(getattr(settings, "ML_SERVICE_TIMEOUT", 60))


def _live_timeout() -> tuple[float, float]:
    return (3.0, min(float(_timeout()), 30.0))


def _live_rtsp_params(rtsp_url: str | None) -> dict[str, str]:
    url = (rtsp_url or "").strip()
    if not url:
        return {}
    return {"rtsp_url": url}


def _request(method: str, path: str, *, timeout: float | tuple[float, float] | None = None, **kwargs) -> requests.Response:
    url = f"{_base_url()}{path}"
    req_timeout = _timeout() if timeout is None else timeout
    try:
        return requests.request(method, url, timeout=req_timeout, **kwargs)
    except requests.RequestException as exc:
        raise MLServiceError(
            f"ML service unreachable at {_base_url()}. "
            f"Start the ML server: cd ml_services && python api_server.py ({exc})",
            503,
        ) from exc


def ml_health() -> dict[str, Any]:
    res = _request("GET", "/health")
    if res.status_code != 200:
        raise MLServiceError(f"ML health check failed ({res.status_code})", res.status_code)
    return res.json()


def ml_reload_faces(embeddings: list[dict[str, Any]] | None = None) -> dict[str, Any]:
    payload = [
        {"identity": entry["identity"], "embedding": entry["embedding"]}
        for entry in (embeddings or [])
    ]
    res = _request("POST", "/reload/faces", json=payload)
    if res.status_code != 200:
        raise MLServiceError("Failed to reload known faces.", res.status_code)
    return res.json()


def ml_extract_face_embedding(file_bytes: bytes, filename: str = "face.jpg") -> dict[str, Any]:
    res = _request(
        "POST",
        "/faces/extract",
        files={"image": (filename, file_bytes, "application/octet-stream")},
    )
    if res.status_code != 200:
        detail = res.text[:300]
        raise MLServiceError(f"Face embedding extraction failed: {detail}", res.status_code)
    return res.json()


def ml_detect_image(
    file_bytes: bytes,
    filename: str = "image.jpg",
    *,
    conf: float = 0.25,
    recognize_faces: bool = True,
) -> dict[str, Any]:
    res = _request(
        "POST",
        "/detect/image",
        files={"image": (filename, file_bytes, "application/octet-stream")},
        params={"conf": conf, "recognize_faces": str(recognize_faces).lower()},
    )
    if res.status_code != 200:
        detail = res.text[:300]
        raise MLServiceError(f"Detection failed: {detail}", res.status_code)
    return res.json()


def ml_recognize_face(file_bytes: bytes, filename: str = "face.jpg") -> dict[str, Any]:
    res = _request(
        "POST",
        "/recognize/face",
        files={"image": (filename, file_bytes, "application/octet-stream")},
    )
    if res.status_code != 200:
        detail = res.text[:300]
        raise MLServiceError(f"Face recognition failed: {detail}", res.status_code)
    return res.json()


def ml_live_status() -> dict[str, Any]:
    res = _request("GET", "/live/status")
    if res.status_code != 200:
        raise MLServiceError(f"Live stream status failed ({res.status_code})", res.status_code)
    return res.json()


def ml_live_detections(stream_key: str, rtsp_url: str | None = None) -> dict[str, Any]:
    key = (stream_key or "").strip()
    res = _request(
        "GET",
        f"/live/cam/{key}/detections",
        params=_live_rtsp_params(rtsp_url),
        timeout=_live_timeout(),
    )
    if res.status_code != 200:
        detail = res.text[:300]
        raise MLServiceError(
            f"Live detections failed ({res.status_code}): {detail}",
            res.status_code,
        )
    return res.json()


def ml_live_mjpeg_url(stream_key: str, rtsp_url: str | None = None) -> str:
    key = (stream_key or "").strip()
    base = f"{_base_url()}/live/cam/{key}/mjpeg"
    params = _live_rtsp_params(rtsp_url)
    if not params:
        return base
    return f"{base}?{urlencode(params)}"


def ml_live_mjpeg_public_url(stream_key: str) -> str:
    """Direct browser URL — no RTSP credentials, camera must be registered on ML service."""
    from django.conf import settings

    key = (stream_key or "").strip()
    base = getattr(settings, "ML_SERVICE_PUBLIC_URL", "").strip().rstrip("/")
    if not base or not key:
        return ""
    return f"{base}/live/cam/{key}/mjpeg"


def ml_live_mjpeg_raw_public_url(stream_key: str) -> str:
    from django.conf import settings

    key = (stream_key or "").strip()
    base = getattr(settings, "ML_SERVICE_PUBLIC_URL", "").strip().rstrip("/")
    if not base or not key:
        return ""
    return f"{base}/live/cam/{key}/mjpeg/raw"


def ml_live_mjpeg_raw_url(stream_key: str, rtsp_url: str | None = None) -> str:
    key = (stream_key or "").strip()
    base = f"{_base_url()}/live/cam/{key}/mjpeg/raw"
    params = _live_rtsp_params(rtsp_url)
    if not params:
        return base
    return f"{base}?{urlencode(params)}"


def ml_register_cameras_bulk(entries: list[dict[str, str]]) -> dict[str, Any]:
    payload = [
        {
            "key": str(item["key"]).strip(),
            "rtsp_url": str(item["rtsp_url"]).strip(),
            **({"purpose": str(item["purpose"]).strip()} if str(item.get("purpose") or "").strip() else {}),
        }
        for item in entries
        if str(item.get("key") or "").strip() and str(item.get("rtsp_url") or "").strip()
    ]
    if not payload:
        return {"registered": 0, "total": 0}
    res = _request("POST", "/live/register/bulk", json=payload)
    if res.status_code != 200:
        raise MLServiceError("Failed to register cameras with ML service.", res.status_code)
    return res.json()


def ml_unregister_camera(stream_key: str) -> dict[str, Any]:
    key = (stream_key or "").strip()
    if not key:
        return {"removed": False}
    res = _request("DELETE", f"/live/cam/{key}/register")
    if res.status_code != 200:
        raise MLServiceError(f"Failed to unregister camera {key}.", res.status_code)
    return res.json()


def ml_validate_human_face(file_bytes: bytes, filename: str = "face.jpg") -> dict[str, Any]:
    res = _request(
        "POST",
        "/validate/human-face",
        files={"image": (filename, file_bytes, "application/octet-stream")},
    )
    if res.status_code != 200:
        detail = res.text[:300]
        raise MLServiceError(f"Face validation failed: {detail}", res.status_code)
    return res.json()
