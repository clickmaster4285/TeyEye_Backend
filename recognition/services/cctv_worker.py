from __future__ import annotations

import logging
import threading
import time
from collections import deque
from dataclasses import dataclass, field
from datetime import datetime

import cv2
from django.conf import settings
from django.db import close_old_connections

from recognition.models import FaceEnrollment
from recognition.services.face_engine import get_face_engine
from recognition.services.rtsp_utils import open_rtsp_capture
from recognition.services.snapshot_saver import save_detection_snapshot, snapshot_to_dict

logger = logging.getLogger(__name__)

MIN_FACE_PX = 40
MIN_DET_SCORE = 0.55
UPSCALE_BELOW_PX = 110
UPSCALE_FACTOR = 2.5


def _match_cooldown() -> int:
    return max(30, int(getattr(settings, "ATTENDANCE_CAMERA_MARK_COOLDOWN_SECONDS", 120)))


def _cctv_threshold() -> float:
    return float(getattr(settings, "ATTENDANCE_CCTV_SIMILARITY_THRESHOLD", 0.38))


@dataclass
class CameraRuntimeState:
    camera_id: int
    name: str
    running: bool = False
    connected: bool = False
    last_error: str = ""
    last_frame_at: str | None = None
    frames_processed: int = 0
    gallery_size: int = 0
    last_events: deque = field(default_factory=lambda: deque(maxlen=30))
    last_jpeg: bytes | None = None
    thread: threading.Thread | None = None
    stop_event: threading.Event = field(default_factory=threading.Event)
    match_cooldown: dict = field(default_factory=dict)


class CCTVWorkerManager:
    def __init__(self):
        self._lock = threading.Lock()
        self._cameras: dict[int, CameraRuntimeState] = {}
        self._scan_interval = 1.5
        self._frame_skip = 8

    def list_status(self) -> list[dict]:
        with self._lock:
            return [self._status_dict(state) for state in self._cameras.values()]

    def get_status(self, camera_id: int) -> dict | None:
        with self._lock:
            state = self._cameras.get(camera_id)
            return self._status_dict(state) if state else None

    def get_snapshot_jpeg(self, camera_id: int) -> bytes | None:
        with self._lock:
            state = self._cameras.get(camera_id)
            return state.last_jpeg if state else None

    def get_events(self, camera_id: int | None = None, limit: int = 40) -> list[dict]:
        with self._lock:
            if camera_id is not None:
                state = self._cameras.get(camera_id)
                if not state:
                    return []
                return list(state.last_events)[:limit]

            events = []
            for state in self._cameras.values():
                events.extend(state.last_events)
            events.sort(key=lambda e: e.get("time", ""), reverse=True)
            return events[:limit]

    def start_camera(
        self,
        camera_id: int,
        name: str,
        rtsp_url: str,
        start_delay: float = 0.0,
    ) -> dict:
        with self._lock:
            existing = self._cameras.get(camera_id)
            if existing and existing.running:
                return self._status_dict(existing)

            stop_event = threading.Event()
            state = CameraRuntimeState(
                camera_id=camera_id,
                name=name,
                stop_event=stop_event,
            )
            thread = threading.Thread(
                target=self._run_camera,
                args=(state, rtsp_url, start_delay),
                name=f"cctv-attendance-{camera_id}",
                daemon=True,
            )
            state.thread = thread
            state.running = True
            self._cameras[camera_id] = state
            thread.start()
            return self._status_dict(state)

    def stop_camera(self, camera_id: int) -> dict | None:
        with self._lock:
            state = self._cameras.get(camera_id)
            if not state:
                return None
            state.stop_event.set()
            state.running = False
            thread = state.thread

        if thread and thread.is_alive():
            thread.join(timeout=5)

        with self._lock:
            state.connected = False
            return self._status_dict(state)

    def start_all(self, cameras: list[dict]) -> list[dict]:
        return [
            self.start_camera(
                c["id"],
                c["name"],
                c["rtsp_url"],
                start_delay=i * 2.5,
            )
            for i, c in enumerate(cameras)
        ]

    def stop_all(self) -> list[dict]:
        with self._lock:
            ids = list(self._cameras.keys())
        results = []
        for cid in ids:
            status = self.stop_camera(cid)
            if status:
                results.append(status)
        return results

    def _status_dict(self, state: CameraRuntimeState) -> dict:
        return {
            "camera_id": state.camera_id,
            "name": state.name,
            "running": state.running,
            "connected": state.connected,
            "last_error": state.last_error,
            "last_frame_at": state.last_frame_at,
            "frames_processed": state.frames_processed,
            "gallery_size": state.gallery_size,
            "recent_events": list(state.last_events)[:8],
            "has_snapshot": state.last_jpeg is not None,
        }

    def _build_gallery(self) -> dict[str, list[float]]:
        close_old_connections()
        gallery = {}
        enrollments = FaceEnrollment.objects.filter(
            is_trained=True,
            embedding__isnull=False,
        ).select_related("staff")
        for enrollment in enrollments:
            gallery[enrollment.gallery_key] = enrollment.embedding
        return gallery

    def _face_bbox_size(self, face) -> tuple[int, int]:
        bbox = getattr(face, "bbox", None)
        if bbox is None:
            return 0, 0
        x1, y1, x2, y2 = [int(v) for v in bbox]
        return max(x2 - x1, 0), max(y2 - y1, 0)

    def _refine_embedding(self, engine, frame, face):
        bbox = getattr(face, "bbox", None)
        if bbox is None:
            return face.embedding, self._face_bbox_size(face)

        x1, y1, x2, y2 = [int(v) for v in bbox]
        face_w, face_h = max(x2 - x1, 0), max(y2 - y1, 0)
        if face_w >= UPSCALE_BELOW_PX and face_h >= UPSCALE_BELOW_PX:
            return face.embedding, (face_w, face_h)

        h, w = frame.shape[:2]
        pad = int(max(face_w, face_h) * 0.45)
        cx1 = max(0, x1 - pad)
        cy1 = max(0, y1 - pad)
        cx2 = min(w, x2 + pad)
        cy2 = min(h, y2 + pad)
        crop = frame[cy1:cy2, cx1:cx2]
        if crop.size == 0:
            return face.embedding, (face_w, face_h)

        up = cv2.resize(
            crop,
            None,
            fx=UPSCALE_FACTOR,
            fy=UPSCALE_FACTOR,
            interpolation=cv2.INTER_CUBIC,
        )
        refined = engine.detect_faces(up)
        if not refined:
            return face.embedding, (face_w, face_h)

        best = max(refined, key=lambda f: float(getattr(f, "det_score", 0.0)))
        if float(getattr(best, "det_score", 0.0)) < MIN_DET_SCORE:
            return face.embedding, (face_w, face_h)
        return best.embedding, (face_w, face_h)

    def _run_camera(self, state: CameraRuntimeState, rtsp_url: str, start_delay: float = 0.0):
        from users.attendance_service import AttendanceDecisionEngine
        from users.models import Attendance, Staff

        if start_delay > 0:
            state.last_error = f"Waiting {start_delay:.0f}s before connect…"
            if state.stop_event.wait(start_delay):
                state.running = False
                return

        engine = get_face_engine()
        gallery_refresh_at = 0.0
        gallery: dict[str, list[float]] = {}
        gallery_warned = False
        cap = None
        frame_index = 0
        reconnect_delay = 5
        cooldown = _match_cooldown()
        last_infer_at = 0.0

        logger.info("Starting CCTV attendance worker for camera %s (%s)", state.camera_id, state.name)

        while not state.stop_event.is_set():
            try:
                if cap is None or not cap.isOpened():
                    if cap is not None:
                        cap.release()
                        cap = None
                    state.connected = False
                    state.last_error = "Connecting to RTSP…"
                    cap, info = open_rtsp_capture(rtsp_url)
                    if cap is None:
                        state.last_error = info or "Cannot open RTSP stream"
                        logger.warning("Camera %s RTSP failed: %s", state.camera_id, state.last_error)
                        time.sleep(reconnect_delay)
                        continue
                    state.connected = True
                    state.last_error = ""
                    logger.info("Camera %s connected (%s)", state.camera_id, info)

                ok, frame = cap.read()
                if not ok or frame is None:
                    state.connected = False
                    state.last_error = "Frame read failed — reconnecting"
                    cap.release()
                    cap = None
                    time.sleep(reconnect_delay)
                    continue

                state.connected = True
                state.last_frame_at = datetime.now().isoformat(timespec="seconds")
                frame_index += 1

                if frame_index % 3 == 0:
                    small = cv2.resize(frame, (640, 360))
                    ok_jpg, buf = cv2.imencode(".jpg", small, [int(cv2.IMWRITE_JPEG_QUALITY), 70])
                    if ok_jpg:
                        state.last_jpeg = buf.tobytes()

                # Keep draining the stream at native FPS (no sleeps!) so the
                # RTSP buffer never overflows; only pace the expensive
                # inference by time.
                now = time.time()
                if now - last_infer_at < self._scan_interval:
                    continue
                last_infer_at = now
                if now - gallery_refresh_at > 30:
                    gallery = self._build_gallery()
                    gallery_refresh_at = now
                    state.gallery_size = len(gallery)

                if not gallery:
                    state.gallery_size = 0
                    if not gallery_warned:
                        state.last_events.appendleft({
                            "time": datetime.now().strftime("%H:%M:%S"),
                            "camera_id": state.camera_id,
                            "camera_name": state.name,
                            "matched": False,
                            "staff_id": None,
                            "confidence": 0.0,
                            "message": "No trained face gallery — enroll & train staff first",
                        })
                        gallery_warned = True
                    continue

                gallery_warned = False

                h, w = frame.shape[:2]
                max_w = 1920
                if w > max_w:
                    scale = max_w / w
                    frame_infer = cv2.resize(frame, (max_w, int(h * scale)))
                else:
                    frame_infer = frame

                faces = engine.detect_faces(frame_infer)
                state.frames_processed += 1

                for face in faces:
                    det_score = float(getattr(face, "det_score", 0.0))
                    if det_score < MIN_DET_SCORE:
                        continue

                    face_w, face_h = self._face_bbox_size(face)
                    if face_w < MIN_FACE_PX or face_h < MIN_FACE_PX:
                        continue

                    embedding, (face_w, face_h) = self._refine_embedding(
                        engine, frame_infer, face
                    )
                    gallery_key, confidence = engine.match_embedding(
                        embedding,
                        gallery,
                        threshold=_cctv_threshold(),
                    )
                    staff_id = None
                    if gallery_key and gallery_key.startswith("staff-"):
                        try:
                            staff_id = int(gallery_key.replace("staff-", ""))
                        except ValueError:
                            staff_id = None

                    event = {
                        "time": datetime.now().strftime("%H:%M:%S"),
                        "camera_id": state.camera_id,
                        "camera_name": state.name,
                        "matched": gallery_key is not None,
                        "staff_id": staff_id,
                        "gallery_key": gallery_key,
                        "confidence": round(confidence, 4),
                        "message": "Face recognized" if gallery_key else "Unknown face",
                        "face_size": f"{face_w}x{face_h}",
                    }

                    if gallery_key and staff_id:
                        last_match = state.match_cooldown.get(gallery_key, 0.0)
                        if now - last_match < cooldown:
                            event["message"] = "Recognized (cooldown)"
                            event["attendance"] = {
                                "action": "ignored",
                                "message": "Duplicate recognition within cooldown",
                                "status": "",
                            }
                            state.last_events.appendleft(event)
                            continue

                        state.match_cooldown[gallery_key] = now
                        close_old_connections()
                        staff = Staff.objects.filter(pk=staff_id).select_related("user").first()
                        if staff:
                            decision = AttendanceDecisionEngine.process_recognition(
                                staff=staff,
                                confidence=confidence,
                                source=Attendance.SOURCE_CCTV,
                            )
                            event["attendance"] = {
                                "action": decision["action"],
                                "message": decision["message"],
                                "status": decision["record"].status if decision["record"] else "",
                            }
                            bbox = getattr(face, "bbox", None)
                            snapshot = save_detection_snapshot(
                                staff=staff,
                                camera_id=state.camera_id,
                                camera_name=state.name,
                                frame=frame_infer,
                                confidence=confidence,
                                attendance_action=decision["action"],
                                attendance_record=(
                                    decision["record"]
                                    if decision["action"] in ("check_in", "check_out")
                                    else None
                                ),
                                bbox=bbox.tolist() if bbox is not None else None,
                            )
                            if snapshot:
                                event["snapshot"] = snapshot_to_dict(snapshot)
                                event["message"] = (
                                    f"Detected on Camera #{state.camera_id} ({state.name})"
                                )
                            logger.info(
                                "Camera %s: staff-%s -> %s (%.2f)",
                                state.camera_id,
                                staff_id,
                                decision["action"],
                                confidence,
                            )

                    if gallery_key or confidence >= 0.28:
                        state.last_events.appendleft(event)

            except Exception as exc:
                logger.exception("Camera %s error: %s", state.camera_id, exc)
                state.last_error = str(exc)
                state.connected = False
                if cap is not None:
                    cap.release()
                    cap = None
                time.sleep(reconnect_delay)

        if cap is not None:
            cap.release()
        state.running = False
        state.connected = False
        logger.info("Stopped CCTV attendance worker for camera %s", state.camera_id)


_manager: CCTVWorkerManager | None = None
_manager_lock = threading.Lock()


def get_cctv_manager() -> CCTVWorkerManager:
    global _manager
    if _manager is None:
        with _manager_lock:
            if _manager is None:
                _manager = CCTVWorkerManager()
    return _manager
