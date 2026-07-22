from __future__ import annotations

import logging
import os
import re
import threading
import time
from urllib.parse import quote, unquote

import cv2

logger = logging.getLogger(__name__)

_open_lock = threading.Lock()


def encode_rtsp_url(url: str) -> str:
    """Encode RTSP credentials so passwords containing '@' work with OpenCV."""
    if not url or not url.startswith("rtsp://"):
        return url

    rest = url[len("rtsp://") :]
    match = re.match(
        r"^([^:/]+):(.+)@(\d{1,3}(?:\.\d{1,3}){3})(:\d+)?(/.*)?$",
        rest,
    )
    if not match:
        return url

    user, password, host, port, path = match.groups()
    # unquote first so already-encoded credentials (e.g. from
    # cameras.rtsp_utils.build_rtsp_url_from_nvr) aren't double-encoded.
    return (
        f"rtsp://{quote(unquote(user), safe='')}:{quote(unquote(password), safe='')}"
        f"@{host}{port or ''}{path or ''}"
    )


def _substream_url(url: str) -> str | None:
    """Hikvision main=101 → sub=102."""
    if "/channels/101" in url:
        return url.replace("/channels/101", "/channels/102")
    if "/Channels/101" in url:
        return url.replace("/Channels/101", "/Channels/102")
    return None


def open_rtsp_capture(rtsp_url: str, timeout_ms: int = 8000):
    """
    Open an RTSP stream with TCP/UDP and main/substream fallbacks.
    Serialized so concurrent camera boots don't hammer the NVR.
    """
    candidates = [rtsp_url]
    sub = _substream_url(rtsp_url)
    if sub:
        candidates.append(sub)

    transports = ("tcp", "udp")
    last_error = "Cannot open RTSP stream"

    with _open_lock:
        for candidate in candidates:
            encoded = encode_rtsp_url(candidate)
            for transport in transports:
                os.environ["OPENCV_FFMPEG_CAPTURE_OPTIONS"] = (
                    f"rtsp_transport;{transport}|stimeout;{timeout_ms * 1000}"
                    f"|fflags;nobuffer|max_delay;500000"
                )
                cap = None
                try:
                    cap = cv2.VideoCapture(encoded, cv2.CAP_FFMPEG)
                    cap.set(cv2.CAP_PROP_BUFFERSIZE, 1)
                    if not cap.isOpened():
                        last_error = f"RTSP open failed ({transport})"
                        cap.release()
                        continue

                    ok, frame = False, None
                    deadline = time.time() + (timeout_ms / 1000.0)
                    while time.time() < deadline:
                        ok, frame = cap.read()
                        if ok and frame is not None:
                            stream_note = "sub" if candidate != rtsp_url else "main"
                            logger.info("RTSP connected via %s/%s", transport, stream_note)
                            return cap, f"{transport}/{stream_note}"
                        time.sleep(0.15)

                    last_error = (
                        f"RTSP SETUP/read failed ({transport}) — "
                        "camera busy or stream limit reached"
                    )
                    cap.release()
                except Exception as exc:
                    last_error = str(exc)
                    if cap is not None:
                        try:
                            cap.release()
                        except Exception:
                            pass
                time.sleep(0.4)

    return None, last_error
