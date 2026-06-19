"""Start the ML inference API as a child process when Django runs (runserver / gunicorn)."""

from __future__ import annotations

import atexit
import os
import subprocess
import sys
import time
from pathlib import Path

import requests

_process: subprocess.Popen | None = None
_log_file = None


def _ml_root() -> Path:
    try:
        from django.conf import settings

        configured = getattr(settings, "ML_ROOT_PATH", "")
        if configured:
            return Path(configured)
    except Exception:
        pass
    return Path(__file__).resolve().parent.parent / "ml_service"


def _python_works(exe: str) -> bool:
    try:
        subprocess.run(
            [exe, "-c", "import sys"],
            capture_output=True,
            timeout=10,
            check=True,
        )
        return True
    except (OSError, subprocess.SubprocessError):
        return False


def _resolve_python() -> str:
    candidates: list[str] = []
    custom = os.getenv("ML_PYTHON", "").strip()
    if custom:
        candidates.append(custom)
    backend_dir = Path(__file__).resolve().parent.parent
    root = _ml_root()
    for base in (backend_dir, root):
        for venv_parts in ((".venv", "Scripts", "python.exe"), (".venv", "bin", "python"), ("venv", "Scripts", "python.exe"), ("venv", "bin", "python")):
            venv_py = base.joinpath(*venv_parts)
            if venv_py.is_file():
                candidates.append(str(venv_py))
    candidates.append(sys.executable)

    for exe in candidates:
        if Path(exe).is_file() and _python_works(exe):
            return exe

    return sys.executable


def _log_path() -> Path:
    log_dir = _ml_root() / "logs"
    log_dir.mkdir(parents=True, exist_ok=True)
    return log_dir / "ml-api-server.log"


def _shutdown_ml_service():
    global _process, _log_file
    if _process is None:
        return
    if _process.poll() is None:
        _process.terminate()
        try:
            _process.wait(timeout=8)
        except subprocess.TimeoutExpired:
            _process.kill()
    _process = None
    if _log_file is not None:
        try:
            _log_file.close()
        except OSError:
            pass
        _log_file = None


def _expected_yolo_weights() -> str:
    weights = os.getenv("ML_YOLO_WEIGHTS", "").strip()
    if weights:
        candidate = Path(weights)
        if not candidate.is_absolute():
            candidate = _ml_root() / weights
        if candidate.is_file():
            return str(candidate.resolve())
    default = _ml_root() / "runs" / "train" / "stage3_finetune3" / "weights" / "yolo26l.pt"
    if default.is_file():
        return str(default.resolve())
    return ""


def _health_matches_config(base_url: str) -> bool:
    """True when /health reports the configured ML root and YOLO weights."""
    try:
        res = requests.get(f"{base_url.rstrip('/')}/health", timeout=3)
        if res.status_code != 200:
            return False
        data = res.json()
        weights = str(data.get("yolo_general_weights") or data.get("yolo_weights") or "")
        root = str(_ml_root().resolve())
        if root.lower() not in weights.replace("/", "\\").lower():
            return False
        expected = _expected_yolo_weights()
        if expected:
            return Path(weights).resolve() == Path(expected).resolve()
        return True
    except (requests.RequestException, ValueError, TypeError, OSError):
        return False


def _stop_listeners_on_port(port: int) -> None:
    """Stop processes listening on a TCP port."""
    if os.name == "nt":
        try:
            result = subprocess.run(
                ["netstat", "-ano"],
                capture_output=True,
                text=True,
                timeout=10,
                check=False,
            )
        except (OSError, subprocess.SubprocessError):
            return
        needle = f":{port}"
        for line in result.stdout.splitlines():
            if needle not in line or "LISTENING" not in line:
                continue
            parts = line.split()
            if not parts:
                continue
            try:
                pid = int(parts[-1])
            except ValueError:
                continue
            if pid in (0, os.getpid()):
                continue
            subprocess.run(
                ["taskkill", "/PID", str(pid), "/F"],
                capture_output=True,
                timeout=10,
                check=False,
            )
        return
    try:
        result = subprocess.run(
            ["fuser", "-k", f"{port}/tcp"],
            capture_output=True,
            timeout=10,
            check=False,
        )
    except (OSError, subprocess.SubprocessError):
        pass


def _wait_for_health(base_url: str, timeout_sec: float = 120.0) -> bool:
    deadline = time.time() + timeout_sec
    url = f"{base_url.rstrip('/')}/health"
    while time.time() < deadline:
        try:
            res = requests.get(url, timeout=3)
            if res.status_code == 200:
                return True
        except requests.RequestException:
            pass
        if _process is not None and _process.poll() is not None:
            return False
        time.sleep(1.0)
    return False


def maybe_start_ml_service():
    global _process, _log_file

    auto = os.getenv("ML_AUTO_START", "True").lower() in ("true", "1", "yes")
    if not auto:
        return

    if _process is not None and _process.poll() is None:
        return

    api_script = _ml_root() / "api_server.py"
    if not api_script.is_file():
        print(f"[ml] Skipping auto-start: {api_script} not found")
        return

    port = os.getenv("ML_API_PORT", "8100")
    host = os.getenv("ML_API_HOST", "127.0.0.1")
    base_url = os.getenv("ML_SERVICE_URL", f"http://{host}:{port}").strip()

    # Reuse a healthy server only when it serves from the configured ML root.
    if _wait_for_health(base_url, timeout_sec=2.0):
        if _health_matches_config(base_url):
            print(f"[ml] Inference server already reachable at {base_url}")
            return
        print(f"[ml] Stopping stale inference server at {base_url} (config/weights changed)")
        _shutdown_ml_service()
        _stop_listeners_on_port(int(port))
        time.sleep(1.0)

    env = os.environ.copy()
    env.setdefault("ML_API_PORT", port)
    env.setdefault("ML_API_HOST", "0.0.0.0")
    env.setdefault("ML_ROOT_PATH", str(_ml_root()))
    env.setdefault("ML_KNOWN_FACES_DIR", str(_ml_root() / "known_faces"))
    python_exe = _resolve_python()
    log_path = _log_path()

    try:
        _log_file = open(log_path, "a", encoding="utf-8")
        _log_file.write(f"\n--- ML API start {time.strftime('%Y-%m-%d %H:%M:%S')} ---\n")
        _log_file.flush()
        _process = subprocess.Popen(
            [python_exe, str(api_script)],
            cwd=str(_ml_root()),
            env=env,
            stdout=_log_file,
            stderr=subprocess.STDOUT,
        )
    except OSError as exc:
        print(f"[ml] Could not start inference server: {exc}")
        return

    atexit.register(_shutdown_ml_service)
    print(f"[ml] Starting inference server ({python_exe}) pid {_process.pid} — log: {log_path}")

    if _wait_for_health(base_url, timeout_sec=120.0):
        print(f"[ml] Inference server ready at {base_url}")
        return

    code = _process.poll() if _process else None
    print(
        f"[ml] Inference server not reachable at {base_url} "
        f"(exit={code}). See log: {log_path}"
    )
