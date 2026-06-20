"""Build RTSP URLs dynamically from NVR credentials + channel (never stored in DB)."""

from __future__ import annotations

from urllib.parse import quote

from .models import Nvr, NvrBrand


def _encode_credentials(username: str, password: str) -> tuple[str, str]:
    return quote(username or "admin", safe=""), quote(password or "", safe="")


def nvr_stream_path(nvr: Nvr, channel: int) -> str:
    """
    Return the RTSP path for a channel on the given NVR.
    channel may be a logical channel (1, 2, 3) or Hikvision stream ID (101, 201).
    """
    ch = int(channel)
    template = (nvr.stream_path_template or "").strip()
    if template:
        return template.format(channel=ch)

    brand = nvr.brand

    if brand == NvrBrand.HIKVISION:
        stream_id = ch if ch >= 100 else ch * 100 + 1
        return f"/Streaming/Channels/{stream_id}"

    if brand == NvrBrand.DAHUA:
        logical = ch if ch <= 64 else ch
        return f"/cam/realmonitor?channel={logical}&subtype=0"

    if brand == NvrBrand.UNIVIEW:
        logical = ch if ch <= 64 else ch
        return f"/media/video{logical}"

    stream_id = ch if ch >= 100 else ch * 100 + 1
    return f"/Streaming/Channels/{stream_id}"


def build_rtsp_url_from_nvr(nvr: Nvr, channel: int) -> str:
    """Construct full RTSP URL at runtime from NVR record + channel number."""
    ip = (nvr.ip_address or "").strip()
    if not ip:
        return ""
    user_enc, pass_enc = _encode_credentials(nvr.username, nvr.password)
    port = int(nvr.port or 554)
    path = nvr_stream_path(nvr, channel)
    if not path.startswith("/"):
        path = f"/{path}"
    return f"rtsp://{user_enc}:{pass_enc}@{ip}:{port}{path}"


def build_rtsp_url_for_preview(nvr: Nvr, channel: int) -> str:
    return build_rtsp_url_from_nvr(nvr, channel)


def nvr_substream_path(nvr: Nvr, channel: int) -> str:
    """Lower-bandwidth substream path (separate RTSP session from ML main stream)."""
    ch = int(channel)
    brand = nvr.brand

    if brand == NvrBrand.HIKVISION:
        stream_id = ch if ch >= 100 else ch * 100 + 2
        if ch >= 100 and ch % 100 == 1:
            stream_id = ch + 1
        return f"/Streaming/Channels/{stream_id}"

    if brand == NvrBrand.DAHUA:
        logical = ch if ch <= 64 else ch
        return f"/cam/realmonitor?channel={logical}&subtype=1"

    if brand == NvrBrand.UNIVIEW:
        logical = ch if ch <= 64 else ch
        return f"/media/video{logical}/substream"

    stream_id = ch if ch >= 100 else ch * 100 + 2
    return f"/Streaming/Channels/{stream_id}"


def build_rtsp_substream_url_from_nvr(nvr: Nvr, channel: int) -> str:
    ip = (nvr.ip_address or "").strip()
    if not ip:
        return ""
    user_enc, pass_enc = _encode_credentials(nvr.username, nvr.password)
    port = int(nvr.port or 554)
    path = nvr_substream_path(nvr, channel)
    if not path.startswith("/"):
        path = f"/{path}"
    return f"rtsp://{user_enc}:{pass_enc}@{ip}:{port}{path}"
