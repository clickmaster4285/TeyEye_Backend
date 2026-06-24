"""RTSP → MJPEG helpers (ffmpeg must be on PATH or FFMPEG_PATH in .env)."""

from __future__ import annotations

import os
import re
import shutil
import subprocess
from typing import Iterator


def resolve_ffmpeg_path() -> str | None:
    import sys

    from django.conf import settings

    custom = getattr(settings, "FFMPEG_PATH", "").strip()
    if custom and os.path.isfile(custom):
        if sys.platform == "win32" or not custom.lower().endswith(".exe"):
            if os.access(custom, os.X_OK):
                return custom
    found = shutil.which("ffmpeg")
    if found:
        return found
    return None


def ffmpeg_available() -> bool:
    return resolve_ffmpeg_path() is not None


def ffmpeg_path() -> str:
    path = resolve_ffmpeg_path()
    if not path:
        raise FileNotFoundError(
            "ffmpeg not found. Place ffmpeg in tools/ffmpeg/bin/ inside the project "
            "or set FFMPEG_PATH in backend/.env."
        )
    return path


def camera_label_from_url(url: str, index: int) -> str:
    match = re.search(r"@([\d.]+)", url)
    if match:
        return f"Camera {index + 1} ({match.group(1)})"
    return f"Camera {index + 1}"


def capture_jpeg_frame(stream_url: str, timeout: float = 12.0) -> bytes | None:
    """Grab a single JPEG frame from RTSP or HTTP video via ffmpeg."""
    url = (stream_url or "").strip()
    if not url:
        return None
    exe = ffmpeg_path()
    cmd = [
        exe,
        "-nostdin",
        "-hide_banner",
        "-loglevel",
        "error",
        "-rtsp_transport",
        "tcp",
        "-fflags",
        "+discardcorrupt",
        "-err_detect",
        "ignore_err",
        "-i",
        url,
        "-frames:v",
        "1",
        "-f",
        "image2",
        "-q:v",
        "2",
        "pipe:1",
    ]
    try:
        proc = subprocess.run(cmd, capture_output=True, timeout=timeout)
    except (FileNotFoundError, subprocess.TimeoutExpired):
        return None
    if proc.returncode != 0 or not proc.stdout:
        return None
    return proc.stdout


def _stream_fps() -> int:
    from django.conf import settings

    raw = getattr(settings, "CAMERA_STREAM_FPS", None) or os.getenv("ML_LIVE_STREAM_FPS", "25")
    try:
        return max(1, int(float(raw)))
    except (TypeError, ValueError):
        return 25


def generate_mjpeg_frames(rtsp_url: str) -> Iterator[bytes]:
    """Yield multipart MJPEG chunks from an RTSP source via ffmpeg."""
    fps = _stream_fps()
    exe = ffmpeg_path()
    cmd = [
        exe,
        "-nostdin",
        "-hide_banner",
        "-loglevel",
        "error",
        "-rtsp_transport",
        "tcp",
        "-fflags",
        "+discardcorrupt",
        "-err_detect",
        "ignore_err",
        "-i",
        rtsp_url,
        "-an",
        "-vf",
        f"fps={fps},scale=640:-1",
        "-f",
        "mjpeg",
        "-q:v",
        "8",
        "-",
    ]
    try:
        proc = subprocess.Popen(
            cmd,
            stdout=subprocess.PIPE,
            stderr=subprocess.DEVNULL,
            bufsize=0,
        )
    except FileNotFoundError:
        return
    if not proc.stdout:
        proc.kill()
        return

    buffer = b""
    try:
        while True:
            chunk = proc.stdout.read(4096)
            if not chunk:
                break
            buffer += chunk
            start = buffer.find(b"\xff\xd8")
            end = buffer.find(b"\xff\xd9")
            if start == -1 or end == -1 or end < start:
                continue
            jpg = buffer[start : end + 2]
            buffer = buffer[end + 2 :]
            yield (
                b"--frame\r\n"
                b"Content-Type: image/jpeg\r\n\r\n" + jpg + b"\r\n"
            )
    finally:
        proc.kill()
        try:
            proc.wait(timeout=2)
        except subprocess.TimeoutExpired:
            proc.kill()
