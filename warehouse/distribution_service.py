"""Memo distribution: multi-camera recording, item-level inventory deduction, destruction alerts."""

from __future__ import annotations

import json
import os
import re
import shutil
import signal
import subprocess
import threading
import time
from decimal import Decimal, InvalidOperation
from typing import Any

from django.conf import settings
from django.db import transaction
from django.db.models import Q
from django.utils import timezone

from cameras.models import Camera
from cameras.stream_utils import ffmpeg_path
from detentions.models import DepositAccountEntry, DetentionMemo, DetentionMemoGoodsLine

from .models import DestructionAlert, FireSmokeDetectionLog, MemoDistribution, WarehouseStockItem

_recorders: dict[str, list[tuple[subprocess.Popen, str, int]]] = {}
_recorders_lock = threading.Lock()
_alert_cooldown: dict[str, float] = {}
_alert_cooldown_lock = threading.Lock()
ALERT_COOLDOWN_SECONDS = 30

DESTRUCTION_ALERT_ROLES = frozenset(
    {
        "ADMIN",
        "LOCATION_ADMIN",
        "WAREHOUSE_OFFICER",
        "WAREHOUSE_IN_CHARGE",
        "WAREHOUSE_SUPERINTENDENT",
    }
)

FIRE_SMOKE_KEYWORDS = ("fire", "smoke", "flame", "burning")


def _parse_qty(value: str | Decimal | float | int | None) -> Decimal:
    if value is None:
        return Decimal("0")
    if isinstance(value, Decimal):
        return value
    text = str(value).strip().replace(",", "")
    if not text:
        return Decimal("0")
    try:
        return Decimal(text)
    except InvalidOperation:
        return Decimal("0")


def sync_stock_items(rows: list[dict[str, Any]]) -> int:
    """Upsert stock rows from frontend localStorage."""
    count = 0
    for row in rows:
        client_id = str(row.get("id") or row.get("client_row_id") or "").strip()
        if not client_id:
            continue
        qty = _parse_qty(row.get("quantity"))
        defaults = {
            "case_ref": str(row.get("seizureCaseRef") or row.get("case_ref") or "").strip(),
            "qr_code": str(row.get("qrCodeNumber") or row.get("qr_code") or "").strip(),
            "description": str(row.get("descriptionOfGoods") or row.get("description") or "").strip(),
            "pct_code": str(row.get("pctCode") or row.get("pct_code") or "").strip(),
            "quantity": qty,
            "unit": str(row.get("unitOfMeasure") or row.get("unit") or "PCS").strip(),
            "godown_warehouse": str(row.get("godownWarehouse") or row.get("godown_warehouse") or "").strip(),
            "status": str(row.get("status") or "In Custody").strip(),
            "detention_memo_id": row.get("detentionMemoId") or row.get("detention_memo_id") or None,
        }
        _, created = WarehouseStockItem.objects.update_or_create(
            client_row_id=client_id,
            defaults=defaults,
        )
        count += 1 if created else 0
    return count


def _normalize_selected_items(
    memo: DetentionMemo,
    selected_items: list[dict[str, Any]] | None,
) -> list[dict[str, Any]]:
    if not selected_items:
        return [
            {
                "goods_line_id": str(gl.pk),
                "description": gl.description or "",
                "qr_code": (gl.qr_code_number or "").strip(),
                "quantity": str(gl.quantity or "0"),
                "unit": gl.unit or "PCS",
            }
            for gl in memo.goods_lines.all()
        ]

    goods_by_key: dict[str, DetentionMemoGoodsLine] = {}
    goods_by_qr: dict[str, DetentionMemoGoodsLine] = {}
    for gl in memo.goods_lines.all():
        goods_by_key[str(gl.pk)] = gl
        if (gl.client_line_id or "").strip():
            goods_by_key[gl.client_line_id.strip()] = gl
        qr = (gl.qr_code_number or "").strip().lower()
        if qr:
            goods_by_qr[qr] = gl

    normalized: list[dict[str, Any]] = []
    for raw in selected_items:
        gl_id = str(raw.get("goods_line_id") or raw.get("goodsLineId") or "").strip()
        qr_key = str(raw.get("qr_code") or raw.get("qrCode") or "").strip().lower()
        gl = goods_by_key.get(gl_id) or (goods_by_qr.get(qr_key) if qr_key else None)
        if not gl:
            continue
        gl_id = str(gl.pk)
        qty = _parse_qty(raw.get("quantity"))
        if qty <= 0:
            continue
        max_qty = _parse_qty(gl.quantity)
        if max_qty > 0 and qty > max_qty:
            qty = max_qty
        normalized.append(
            {
                "goods_line_id": gl_id,
                "description": gl.description or "",
                "qr_code": (gl.qr_code_number or "").strip(),
                "quantity": str(qty),
                "unit": gl.unit or str(raw.get("unit") or "PCS"),
            }
        )
    return normalized


def _resolve_goods_line(memo: DetentionMemo, item: dict[str, Any]) -> DetentionMemoGoodsLine | None:
    gl_id = str(item.get("goods_line_id") or "").strip()
    qr_key = (item.get("qr_code") or "").strip().lower()
    for gl in memo.goods_lines.all():
        if gl_id and (str(gl.pk) == gl_id or gl.client_line_id == gl_id):
            return gl
        if qr_key and (gl.qr_code_number or "").strip().lower() == qr_key:
            return gl
    return None


def _find_stock_for_item(memo: DetentionMemo, item: dict[str, Any]) -> WarehouseStockItem | None:
    qr = (item.get("qr_code") or "").strip()
    if qr:
        stock = (
            WarehouseStockItem.objects.filter(qr_code__iexact=qr)
            .exclude(quantity__lte=0)
            .order_by("-updated_at")
            .first()
        )
        if stock:
            return stock

    gl = _resolve_goods_line(memo, item)
    if gl and (gl.qr_code_number or "").strip():
        stock = (
            WarehouseStockItem.objects.filter(qr_code__iexact=gl.qr_code_number.strip())
            .exclude(quantity__lte=0)
            .order_by("-updated_at")
            .first()
        )
        if stock:
            return stock

    case_no = (memo.case_no or "").strip()
    desc = (item.get("description") or "").strip()
    qs = WarehouseStockItem.objects.filter(detention_memo_id=memo.pk).exclude(quantity__lte=0)
    if case_no:
        qs = qs.filter(Q(case_ref__iexact=case_no) | Q(case_ref__icontains=case_no))
    if desc:
        qs = qs.filter(description__icontains=desc[:60])
    return qs.order_by("-updated_at").first()


def _deduct_selected_inventory(
    memo: DetentionMemo,
    selected_items: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    deductions: list[dict[str, Any]] = []
    for item in selected_items:
        stock = _find_stock_for_item(memo, item)
        if not stock:
            continue
        before = stock.quantity
        deduct = min(before, _parse_qty(item.get("quantity")))
        if deduct <= 0:
            continue
        after = max(Decimal("0"), before - deduct)
        stock.quantity = after
        if after <= 0:
            stock.status = "Destructed"
        stock.save(update_fields=["quantity", "status", "updated_at"])
        deductions.append(
            {
                "stock_id": str(stock.pk),
                "client_row_id": stock.client_row_id,
                "detention_memo_id": str(memo.pk),
                "detention_case_no": memo.case_no or "",
                "goods_line_id": item.get("goods_line_id"),
                "case_ref": stock.case_ref,
                "qr_code": stock.qr_code,
                "description": item.get("description") or stock.description,
                "quantity_before": str(before),
                "quantity_deducted": str(deduct),
                "quantity_after": str(after),
                "status": stock.status,
            }
        )
    return deductions


def _deduct_memo_goods_lines(memo: DetentionMemo, selected_items: list[dict[str, Any]]) -> None:
    """Reduce detained goods line quantities for destroyed amounts."""
    for item in selected_items:
        gl = _resolve_goods_line(memo, item)
        if not gl:
            continue
        deduct = _parse_qty(item.get("quantity"))
        if deduct <= 0:
            continue
        before = _parse_qty(gl.quantity)
        after = max(Decimal("0"), before - deduct)
        gl.quantity = str(after)
        if after <= 0:
            gl.condition = "Destructed"
        gl.save(update_fields=["quantity", "condition"])


def _sync_deposit_accounts_on_destruction(memo: DetentionMemo) -> list[str]:
    """Mark linked deposit account entries as Destructed."""
    updated: list[str] = []
    qs = DepositAccountEntry.objects.filter(detention_memo=memo)
    case_no = (memo.case_no or "").strip()
    if case_no:
        qs = qs | DepositAccountEntry.objects.filter(case_seizure_ref__iexact=case_no)
    for entry in qs.distinct():
        entry.status = "Destructed"
        entry.remarks = (entry.remarks or "").strip()
        if "destruction" not in entry.remarks.lower():
            entry.remarks = f"{entry.remarks} | Marked Destructed after warehouse destruction.".strip(" |")
        entry.save(update_fields=["status", "remarks", "updated_at"])
        updated.append(str(entry.pk))
    return updated


def _goods_lines_sync_payload(memo: DetentionMemo) -> list[dict[str, Any]]:
    return [
        {
            "id": gl.client_line_id or str(gl.pk),
            "goods_line_id": str(gl.pk),
            "qr_code": gl.qr_code_number,
            "description": gl.description,
            "quantity": gl.quantity,
            "condition": gl.condition,
        }
        for gl in memo.goods_lines.all()
    ]


def _mark_items_destructed(memo: DetentionMemo, selected_items: list[dict[str, Any]]) -> None:
    for item in selected_items:
        gl = _resolve_goods_line(memo, item)
        if not gl:
            continue
        gl.condition = "Destructed"
        gl.save(update_fields=["condition"])


def _resolve_location_code(memo: DetentionMemo, cameras: list[Camera]) -> str:
    for cam in cameras:
        loc = (cam.location or "").strip()
        if loc:
            return loc
    for field in (memo.location_of_detention, memo.where_deposited, memo.place_of_detention):
        text = (field or "").strip().upper().replace(" ", "_")
        for choice in ("PESHAWAR", "KOHAT", "NOWSHERA", "MARDAN", "DI_KHAN"):
            if choice in text or choice.replace("_", " ") in (field or "").upper():
                return choice
    return ""


def get_destruction_alert_recipients(location_code: str):
    from users.models import User

    qs = User.objects.filter(is_active=True, is_deleted=False, role__in=DESTRUCTION_ALERT_ROLES)
    admins = qs.filter(role="ADMIN")
    if location_code:
        location_users = qs.filter(role__in=DESTRUCTION_ALERT_ROLES - {"ADMIN"}, location=location_code)
    else:
        location_users = qs.exclude(role="ADMIN")
    return list({u.pk: u for u in list(admins) + list(location_users)}.values())


def is_fire_or_smoke_detection(detection: dict[str, Any]) -> bool:
    class_name = str(detection.get("class_name", "")).lower()
    label = str(detection.get("label", "")).lower()
    keyword_hit = any(k in class_name or k in label for k in FIRE_SMOKE_KEYWORDS)
    return keyword_hit or bool(detection.get("alert"))


def _max_recording_seconds() -> int | None:
    raw = os.getenv("DESTRUCTION_MAX_RECORDING_SECONDS", "").strip()
    if not raw:
        return None
    try:
        return max(60, int(raw))
    except ValueError:
        return None


def _manifest_path(session_id: str) -> str:
    return os.path.join(settings.MEDIA_ROOT, "distribution", str(session_id), "recording_manifest.json")


def _save_recording_manifest(session_id: str, rows: list[dict[str, Any]]) -> None:
    path = _manifest_path(session_id)
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8") as fh:
        json.dump(rows, fh, indent=2)


def _load_recording_manifest(session_id: str) -> list[dict[str, Any]]:
    path = _manifest_path(session_id)
    if not os.path.isfile(path):
        return []
    try:
        with open(path, encoding="utf-8") as fh:
            data = json.load(fh)
        return data if isinstance(data, list) else []
    except (OSError, json.JSONDecodeError):
        return []


def _recording_input_for_camera(camera: Camera) -> tuple[str, str, list[str]]:
    """Return stream URL, source label, and extra ffmpeg input args."""
    from ml.client import ml_live_mjpeg_url, ml_service_enabled

    if camera.nvr_id and ml_service_enabled():
        stream_url = camera.effective_stream_url()
        return (
            ml_live_mjpeg_url(camera.stream_key, rtsp_url=stream_url),
            "ml_annotated",
            ["-f", "mpjpeg", "-fflags", "nobuffer", "-flags", "low_delay"],
        )
    url = camera.effective_stream_url()
    if not url:
        raise ValueError(f"Camera {camera.name} has no stream URL.")
    extra = ["-rtsp_transport", "tcp"] if camera.is_rtsp else []
    return url, "rtsp" if camera.is_rtsp else "http", extra


def _wait_for_recording_file(output_path: str, timeout: float = 20.0) -> bool:
    deadline = time.time() + timeout
    while time.time() < deadline:
        if os.path.isfile(output_path) and os.path.getsize(output_path) > 0:
            return True
        time.sleep(0.35)
    return os.path.isfile(output_path) and os.path.getsize(output_path) > 0


def _terminate_pid(pid: int) -> None:
    if pid <= 0:
        return
    try:
        if os.name == "nt":
            subprocess.run(
                ["taskkill", "/PID", str(pid), "/T"],
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
                timeout=12,
            )
        else:
            os.kill(pid, signal.SIGINT)
    except (ProcessLookupError, subprocess.TimeoutExpired, OSError):
        try:
            if os.name == "nt":
                subprocess.run(
                    ["taskkill", "/PID", str(pid), "/F", "/T"],
                    stdout=subprocess.DEVNULL,
                    stderr=subprocess.DEVNULL,
                    timeout=8,
                )
            else:
                os.kill(pid, signal.SIGTERM)
        except (ProcessLookupError, OSError):
            pass


def _graceful_stop_recorder(proc: subprocess.Popen, output_path: str) -> bool:
    """Stop ffmpeg cleanly so recording files are finalized."""
    if proc.poll() is None:
        try:
            if os.name == "nt":
                proc.send_signal(signal.CTRL_BREAK_EVENT)
            else:
                proc.send_signal(signal.SIGINT)
            proc.wait(timeout=20)
        except (ProcessLookupError, subprocess.TimeoutExpired):
            proc.terminate()
            try:
                proc.wait(timeout=8)
            except subprocess.TimeoutExpired:
                proc.kill()
                proc.wait(timeout=5)
    return _wait_for_recording_file(output_path)


def _stop_recorder_entries(entries: list[tuple[subprocess.Popen, str, int]]) -> list[tuple[str, int]]:
    """Stop ffmpeg processes and return non-empty recording files."""
    output_entries: list[tuple[str, int]] = []
    for proc, output_path, camera_id in entries:
        if _graceful_stop_recorder(proc, output_path):
            output_entries.append((output_path, camera_id))
    return output_entries


def _stop_manifest_recorders(session_id: str) -> list[tuple[str, int]]:
    """Stop recorders tracked on disk when in-memory handles are unavailable."""
    stopped: list[tuple[str, int]] = []
    for row in _load_recording_manifest(session_id):
        pid = int(row.get("pid") or 0)
        output_path = str(row.get("path") or "").strip()
        camera_id = int(row.get("camera_id") or 0)
        if not output_path:
            continue
        if pid > 0:
            _terminate_pid(pid)
        if _wait_for_recording_file(output_path):
            stopped.append((output_path, camera_id))
    return stopped


def _scan_disk_recordings(session_id: str) -> list[tuple[str, int]]:
    """Recover recordings written under the session media folder."""
    abs_dir = os.path.join(settings.MEDIA_ROOT, "distribution", str(session_id))
    if not os.path.isdir(abs_dir):
        return []
    found: list[tuple[str, int]] = []
    for fname in sorted(os.listdir(abs_dir)):
        if not fname.startswith("recording_"):
            continue
        if not (fname.endswith(".mp4") or fname.endswith(".mkv")):
            continue
        path = os.path.join(abs_dir, fname)
        if not os.path.isfile(path) or os.path.getsize(path) <= 0:
            continue
        match = re.search(r"recording_(\d+)\.(mp4|mkv)$", fname)
        camera_id = int(match.group(1)) if match else 0
        found.append((path, camera_id))
    return found


def _finalize_recording_file(src_path: str, dest_mp4: str) -> bool:
    """Remux MKV/intermediate capture into a browser-friendly MP4."""
    if not os.path.isfile(src_path) or os.path.getsize(src_path) <= 0:
        return False
    os.makedirs(os.path.dirname(dest_mp4), exist_ok=True)
    if src_path.lower().endswith(".mp4") and os.path.abspath(src_path) == os.path.abspath(dest_mp4):
        return True
    if src_path.lower().endswith(".mp4"):
        shutil.copy2(src_path, dest_mp4)
        return os.path.getsize(dest_mp4) > 0
    cmd = [
        ffmpeg_path(),
        "-nostdin",
        "-hide_banner",
        "-loglevel",
        "error",
        "-y",
        "-i",
        src_path,
        "-c",
        "copy",
        dest_mp4,
    ]
    try:
        proc = subprocess.run(cmd, capture_output=True, timeout=180)
    except (FileNotFoundError, subprocess.TimeoutExpired):
        return False
    if proc.returncode != 0 or not os.path.isfile(dest_mp4) or os.path.getsize(dest_mp4) <= 0:
        cmd_reencode = [
            ffmpeg_path(),
            "-nostdin",
            "-hide_banner",
            "-loglevel",
            "error",
            "-y",
            "-i",
            src_path,
            "-c:v",
            "libx264",
            "-preset",
            "fast",
            "-crf",
            "23",
            "-an",
            "-movflags",
            "+faststart",
            dest_mp4,
        ]
        try:
            reencode = subprocess.run(cmd_reencode, capture_output=True, timeout=600)
        except (FileNotFoundError, subprocess.TimeoutExpired):
            return False
        return reencode.returncode == 0 and os.path.isfile(dest_mp4) and os.path.getsize(dest_mp4) > 0
    return proc.returncode == 0 and os.path.isfile(dest_mp4) and os.path.getsize(dest_mp4) > 0


def _merge_recording_entries(*groups: list[tuple[str, int]]) -> list[tuple[str, int]]:
    merged: list[tuple[str, int]] = []
    seen: set[str] = set()
    for group in groups:
        for path, camera_id in group:
            key = os.path.abspath(path)
            if key in seen:
                continue
            seen.add(key)
            merged.append((path, camera_id))
    return merged


def collect_session_recording_entries(
    session: MemoDistribution,
    *,
    repair: bool = False,
) -> list[dict[str, Any]]:
    """Merge DB metadata with on-disk recordings; optionally backfill the session row."""
    disk_entries = _scan_disk_recordings(str(session.pk))
    merged_paths = _merge_recording_entries(disk_entries)
    entries: list[dict[str, Any]] = list(session.camera_videos or [])

    known_camera_ids = {int(item.get("camera_id") or 0) for item in entries}
    for _path, camera_id in merged_paths:
        if camera_id not in known_camera_ids:
            entries.append(
                {
                    "camera_id": camera_id,
                    "filename": f"recording_{camera_id}.mp4",
                    "path": f"distribution/{session.pk}/recording_{camera_id}.mp4",
                }
            )

    if repair and merged_paths and not session.camera_videos:
        entries = _persist_session_recordings(session, merged_paths)
        session.save(update_fields=["camera_videos", "video", "updated_at"])

    return entries


def _persist_session_recordings(session: MemoDistribution, output_entries: list[tuple[str, int]]) -> list[dict[str, Any]]:
    """Attach all camera recordings to the session and return camera_videos metadata."""
    from django.core.files import File

    camera_videos: list[dict[str, Any]] = []
    rel_dir = f"distribution/{session.pk}"
    abs_dir = os.path.join(settings.MEDIA_ROOT, rel_dir)
    os.makedirs(abs_dir, exist_ok=True)
    started = session.created_at.timestamp() if session.created_at else time.time()
    completed = session.completed_at.timestamp() if session.completed_at else time.time()
    session_duration = max(0, int(completed - started))

    manifest_by_camera = {
        int(row.get("camera_id") or 0): row for row in _load_recording_manifest(str(session.pk))
    }
    for idx, (output_path, camera_id) in enumerate(output_entries):
        filename = f"recording_{camera_id}.mp4"
        dest_path = os.path.join(abs_dir, filename)
        if not _finalize_recording_file(output_path, dest_path):
            continue
        size_bytes = os.path.getsize(dest_path)
        manifest_row = manifest_by_camera.get(camera_id, {})
        if idx == 0:
            with open(dest_path, "rb") as fh:
                session.video.save("recording.mp4", File(fh), save=False)
        camera_videos.append(
            {
                "camera_id": camera_id,
                "filename": filename,
                "path": f"{rel_dir}/{filename}",
                "size_bytes": size_bytes,
                "duration_seconds": session_duration,
                "includes_ml_overlay": manifest_row.get("source") == "ml_annotated",
                "recording_source": manifest_row.get("source") or "rtsp",
            }
        )
    return camera_videos


def _start_camera_recording(
    session_id: str,
    camera: Camera,
    media_root: str,
) -> tuple[subprocess.Popen, str, int, dict[str, Any]]:
    stream_url, source, input_extra = _recording_input_for_camera(camera)
    output_path = os.path.abspath(os.path.join(media_root, f"recording_{camera.pk}.mkv"))
    record_fps = max(1, int(float(os.getenv("ML_LIVE_STREAM_FPS", "25"))))
    max_seconds = _max_recording_seconds()
    cmd = [
        ffmpeg_path(),
        "-nostdin",
        "-hide_banner",
        "-loglevel",
        "error",
        *input_extra,
        "-i",
        stream_url,
        "-map",
        "0:v:0?",
        "-an",
        "-r",
        str(record_fps),
        "-c:v",
        "libx264",
        "-preset",
        "ultrafast",
        "-crf",
        "23",
        "-g",
        str(record_fps * 2),
    ]
    if max_seconds:
        cmd.extend(["-t", str(max_seconds)])
    cmd.extend(["-f", "matroska", "-y", output_path])
    creationflags = subprocess.CREATE_NEW_PROCESS_GROUP if os.name == "nt" else 0
    proc = subprocess.Popen(
        cmd,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
        creationflags=creationflags,
    )
    manifest_row = {
        "camera_id": camera.pk,
        "pid": proc.pid,
        "path": output_path,
        "source": source,
        "stream_url": stream_url[:200],
        "started_at": timezone.now().isoformat(),
    }
    return proc, output_path, camera.pk, manifest_row


def start_distribution_recording(
    *,
    detention_memo_id: str,
    cameras: list[Camera],
    selected_items: list[dict[str, Any]] | None = None,
    performed_by: str = "",
) -> MemoDistribution:
    if not cameras:
        raise ValueError("At least one camera is required.")

    try:
        memo = DetentionMemo.objects.get(pk=detention_memo_id)
    except DetentionMemo.DoesNotExist as exc:
        raise ValueError("Detention memo not found.") from exc

    normalized_items = _normalize_selected_items(memo, selected_items)
    if not normalized_items:
        raise ValueError("Select at least one goods item with a quantity greater than zero.")

    location_code = _resolve_location_code(memo, cameras)
    session = MemoDistribution.objects.create(
        detention_memo_id=memo.pk,
        detention_case_no=memo.case_no or "",
        camera=cameras[0],
        camera_ids=[cam.pk for cam in cameras],
        selected_items=normalized_items,
        location_code=location_code,
        performed_by=performed_by,
        status=MemoDistribution.STATUS_RECORDING,
    )

    media_root = os.path.join(settings.MEDIA_ROOT, "distribution", str(session.pk))
    os.makedirs(media_root, exist_ok=True)

    recorder_entries: list[tuple[subprocess.Popen, str, int]] = []
    manifest_rows: list[dict[str, Any]] = []
    for camera in cameras:
        proc, output_path, camera_id, manifest_row = _start_camera_recording(
            str(session.pk), camera, media_root
        )
        recorder_entries.append((proc, output_path, camera_id))
        manifest_rows.append(manifest_row)
    _save_recording_manifest(str(session.pk), manifest_rows)

    with _recorders_lock:
        _recorders[str(session.pk)] = recorder_entries
    return session


def _create_fire_smoke_log(
    session: MemoDistribution,
    memo: DetentionMemo,
    camera: Camera | None,
    alert_detections: list[dict[str, Any]],
    *,
    alert_triggered: bool = False,
    destruction_alert: DestructionAlert | None = None,
    notified_user_ids: list[int] | None = None,
) -> FireSmokeDetectionLog:
    top = max(alert_detections, key=lambda d: float(d.get("confidence", 0)))
    location_code = session.location_code or _resolve_location_code(
        memo,
        [camera] if camera else [],
    )
    return FireSmokeDetectionLog.objects.create(
        distribution=session,
        destruction_alert=destruction_alert,
        detention_memo_id=session.detention_memo_id,
        detention_case_no=session.detention_case_no or "",
        detention_fir_number=memo.fir_number or "",
        warehouse_name=memo.where_deposited or "",
        location_code=location_code,
        place_of_detention=memo.place_of_detention or memo.location_of_detention or "",
        place_of_occurrence=memo.place_of_occurrence or "",
        camera=camera,
        camera_code=(camera.code if camera else "") or "",
        camera_name=(camera.name if camera else "") or "",
        camera_ip=(f"{camera.nvr.ip_address}:ch{camera.channel}" if camera and camera.nvr_id else "") or "",
        camera_zone=(camera.zone if camera else "") or "",
        camera_site_label=(camera.site_label if camera else "") or "",
        detection_class=str(top.get("class_name") or top.get("label") or "fire_smoke"),
        detection_label=str(top.get("label") or top.get("class_name") or "fire_smoke"),
        confidence=float(top.get("confidence", 0)),
        bbox=top.get("bbox") or [],
        detection_count=len(alert_detections),
        detections=alert_detections,
        alert_triggered=alert_triggered,
        notified_user_ids=notified_user_ids or [],
        performed_by=session.performed_by or "",
        session_status=session.status,
    )


def report_destruction_detection(
    session_id: str,
    *,
    camera_id: int,
    detections: list[dict[str, Any]],
) -> tuple[FireSmokeDetectionLog | None, DestructionAlert | None]:
    alert_detections = [d for d in detections if is_fire_or_smoke_detection(d)]
    if not alert_detections:
        return None, None

    try:
        session = MemoDistribution.objects.select_related("camera").get(pk=session_id)
    except MemoDistribution.DoesNotExist as exc:
        raise ValueError("Distribution session not found.") from exc

    if session.status != MemoDistribution.STATUS_RECORDING:
        return None, None

    try:
        camera = Camera.objects.get(pk=camera_id)
    except Camera.DoesNotExist:
        camera = session.camera

    memo = DetentionMemo.objects.get(pk=session.detention_memo_id)
    location_code = session.location_code or _resolve_location_code(memo, [camera] if camera else [])

    cooldown_key = f"{session_id}:{camera_id}"
    now = timezone.now().timestamp()
    should_notify = False
    with _alert_cooldown_lock:
        last = _alert_cooldown.get(cooldown_key, 0)
        if now - last >= ALERT_COOLDOWN_SECONDS:
            should_notify = True
            _alert_cooldown[cooldown_key] = now

    alert: DestructionAlert | None = None
    notified_ids: list[int] = []
    if should_notify:
        recipients = get_destruction_alert_recipients(location_code)
        notified_ids = [u.pk for u in recipients]
        top = max(alert_detections, key=lambda d: float(d.get("confidence", 0)))
        case_no = session.detention_case_no or str(session.detention_memo_id)[:8]
        cam_name = camera.name if camera else "Unknown camera"
        detection_class = str(top.get("class_name") or top.get("label") or "fire_smoke")
        confidence = float(top.get("confidence", 0))
        warehouse = memo.where_deposited or location_code or "warehouse"
        message = (
            f"Smoke/fire detected during destruction of case {case_no} at {warehouse} "
            f"({memo.place_of_detention or location_code}) on camera {cam_name} "
            f"(confidence {confidence:.0%})."
        )
        alert = DestructionAlert.objects.create(
            distribution=session,
            detention_memo_id=session.detention_memo_id,
            detention_case_no=session.detention_case_no,
            camera=camera,
            location_code=location_code,
            alert_type="fire_smoke",
            severity=DestructionAlert.SEVERITY_CRITICAL,
            message=message,
            detection_class=detection_class,
            confidence=confidence,
            detection_data={
                "detections": alert_detections,
                "warehouse_name": memo.where_deposited,
                "place_of_detention": memo.place_of_detention,
                "place_of_occurrence": memo.place_of_occurrence,
                "camera_code": camera.code if camera else "",
                "camera_ip": (
                    f"{camera.nvr.ip_address}:ch{camera.channel}" if camera and camera.nvr_id else ""
                ),
                "camera_zone": camera.zone if camera else "",
                "camera_site_label": camera.site_label if camera else "",
            },
            notified_user_ids=notified_ids,
        )
        session.smoke_fire_detected = True
        session.save(update_fields=["smoke_fire_detected"])

    log = _create_fire_smoke_log(
        session,
        memo,
        camera,
        alert_detections,
        alert_triggered=should_notify,
        destruction_alert=alert,
        notified_user_ids=notified_ids,
    )
    return log, alert


def complete_distribution(session_id: str) -> MemoDistribution:
    with _recorders_lock:
        entries = _recorders.pop(str(session_id), [])

    try:
        session = MemoDistribution.objects.select_related("camera").get(pk=session_id)
    except MemoDistribution.DoesNotExist as exc:
        raise ValueError("Distribution session not found.") from exc

    memory_entries = _stop_recorder_entries(entries) if entries else []
    manifest_entries = _stop_manifest_recorders(session_id) if not memory_entries else []
    disk_entries = _scan_disk_recordings(session_id)
    output_entries = _merge_recording_entries(memory_entries, manifest_entries, disk_entries)

    try:
        with transaction.atomic():
            memo = DetentionMemo.objects.get(pk=session.detention_memo_id)
            if session.selected_items:
                selected_items = session.selected_items
            else:
                selected_items = _normalize_selected_items(memo, None)
            if not selected_items:
                raise ValueError("No goods items recorded for this destruction session.")

            deductions = _deduct_selected_inventory(memo, selected_items)
            _deduct_memo_goods_lines(memo, selected_items)
            _sync_deposit_accounts_on_destruction(memo)

            all_lines_destructed = all(
                _parse_qty(gl.quantity) <= 0 or gl.condition == "Destructed"
                for gl in memo.goods_lines.all()
            )
            memo.disposition_status = "Destructed" if all_lines_destructed else "Partially Destructed"
            memo.save(update_fields=["disposition_status", "updated_at"])

            if deductions:
                session.outcome = MemoDistribution.OUTCOME_INVENTORY
                session.inventory_deductions = deductions
            else:
                _mark_items_destructed(memo, selected_items)
                session.outcome = MemoDistribution.OUTCOME_DESTRUCTED
                session.inventory_deductions = []

            if output_entries:
                session.camera_videos = _persist_session_recordings(session, output_entries)
            else:
                session.camera_videos = collect_session_recording_entries(session, repair=True)
            session.status = MemoDistribution.STATUS_COMPLETED
            session.completed_at = timezone.now()
            session.save()
    except Exception as exc:
        session.status = MemoDistribution.STATUS_FAILED
        session.error_message = str(exc)
        session.completed_at = timezone.now()
        session.save(update_fields=["status", "error_message", "completed_at"])
        raise

    return session
