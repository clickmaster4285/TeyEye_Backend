"""Map frontend VMS payloads to Visitor model fields and extra_data."""

from __future__ import annotations

from datetime import date, datetime
from typing import Any

from django.db import models

from .models import Visitor

# Keys stored on Visitor model (not in extra_data)
VISITOR_DIRECT_FIELDS = {
    "id",
    "created_at",
    "updated_at",
    "visitor_type",
    "full_name",
    "gender",
    "cnic_number",
    "passport_number",
    "nationality",
    "date_of_birth",
    "mobile_number",
    "email_address",
    "residential_address",
    "visit_purpose",
    "visit_description",
    "department_to_visit",
    "host_officer_name",
    "host_officer_designation",
    "preferred_visit_date",
    "preferred_time_slot",
    "expected_duration",
    "preferred_view_visit",
    "document_type",
    "document_no",
    "issuing_authority",
    "expiry_date",
    "front_image",
    "back_image",
    "support_doc_type",
    "application_letter",
    "letter_ref_no",
    "additional_document",
    "upload_procedure",
    "organization_name",
    "organization_type",
    "ntn_registration_no",
    "designation",
    "office_address",
    "capture_date",
    "capture_time",
    "captured_by",
    "camera_location",
    "photo_quality_score",
    "face_match_status",
    "captured_photo",
    "disclaimer_accepted",
    "terms_accepted",
    "previous_visit_reference",
    "registration_type",
    "cnic_passport",
    "visit_purpose_description",
    "visit_type",
    "reference_number",
    "preferred_date",
    "preferred_time_slot_walkin",
    "department_for_slot",
    "slot_duration",
    "host_id",
    "host_full_name",
    "host_designation",
    "host_department",
    "host_email",
    "host_contact_number",
    "watchlist_check_status",
    "approver_required",
    "temporary_access_granted",
    "guard_remarks",
    "qr_code_id",
    "visitor_ref_number",
    "visit_date",
    "time_validity_start",
    "time_validity_end",
    "access_zone",
    "entry_gate",
    "expiry_status",
    "scan_count",
    "generated_on",
    "generated_by",
    "flow_stage",
    "registration_source",
    "registration_status",
    "approval_status",
    "approved_by",
    "denied_by",
    "rejection_reason",
    "location",
    "registered_by_user_id",
    "registered_by_username",
    "profile_image",
    "guard_entry_time",
    "guard_name",
    "host_notified_at",
    "extra_data",
}

CAMEL_TO_SNAKE = {
    "fullName": "full_name",
    "visitorType": "visitor_type",
    "cnicNumber": "cnic_number",
    "cnicPassport": "cnic_passport",
    "passportNumber": "passport_number",
    "dateOfBirth": "date_of_birth",
    "mobileNumber": "mobile_number",
    "emailAddress": "email_address",
    "email": "email_address",
    "phone": "mobile_number",
    "residentialAddress": "residential_address",
    "visitPurpose": "visit_purpose",
    "visitDescription": "visit_description",
    "department": "department_to_visit",
    "hostName": "host_officer_name",
    "hostFullName": "host_full_name",
    "hostDesignation": "host_designation",
    "hostDepartment": "host_department",
    "hostEmail": "host_email",
    "hostContactNumber": "host_contact_number",
    "hostId": "host_id",
    "preferredDate": "preferred_visit_date",
    "preferredTimeSlot": "preferred_time_slot",
    "registrationSource": "registration_source",
    "registrationStatus": "registration_status",
    "profileImage": "profile_image",
    "watchlistCheckStatus": "watchlist_check_status",
    "photoCapture": "captured_photo",
    "photo_capture": "captured_photo",
    "draftFormData": "draft_form_data",
}

# Large binary/text payloads — never truncate for DB column limits
VISITOR_BLOB_TEXT_FIELDS = frozenset(
    {
        "front_image",
        "back_image",
        "captured_photo",
        "profile_image",
        "application_letter",
        "additional_document",
    }
)

# Keys commonly holding base64 in API responses (stripped for list views)
VISITOR_RESPONSE_BLOB_KEYS = frozenset(
    VISITOR_BLOB_TEXT_FIELDS
    | {
        "photo_capture",
        "visitor_photos",
        "visitorPhotos",
        "vehicle_images",
        "vehicleImages",
        "vehicle_image",
        "authorization_letter",
        "noc_document",
        "draft_form_data",
    }
)

VISITOR_TYPE_MAP = {
    "individual": "general",
    "walk-in": "general",
    "pre-registration": "general",
}

NATIONALITY_MAP = {
    "pakistani": "pakistan",
}

VISIT_PURPOSE_MAP = {
    "official": "meeting",
    "business": "meeting",
}


def _normalize_key(key: str) -> str:
    if key in CAMEL_TO_SNAKE:
        return CAMEL_TO_SNAKE[key]
    return key


def _coerce_choice(value: Any, valid: list[str], default: str, mapping: dict[str, str] | None = None) -> str:
    if value is None or value == "":
        return default
    v = str(value).lower().strip().replace(" ", "-")
    if mapping and v in mapping:
        v = mapping[v]
    if v in valid:
        return v
    return default


VISITOR_DATE_FIELDS = frozenset(
    {
        "date_of_birth",
        "expiry_date",
        "visit_date",
        "generated_on",
        "preferred_visit_date",
    }
)


def _parse_date(value: Any) -> date | None:
    if value is None:
        return None
    if isinstance(value, date) and not isinstance(value, datetime):
        return value
    s = str(value).strip()[:10]
    if not s:
        return None
    try:
        return date.fromisoformat(s)
    except ValueError:
        return None


def _sanitize_date_fields(target: dict[str, Any], *, keys: set[str] | None = None) -> None:
    """Convert empty/invalid date strings to None for Django DateField columns."""
    field_names = keys if keys is not None else set(VISITOR_DATE_FIELDS)
    for field in field_names:
        if field not in target:
            continue
        target[field] = _parse_date(target[field])


VISITOR_INT_DEFAULTS: dict[str, int | None] = {
    "scan_count": 0,
    "registered_by_user_id": None,
}

VISITOR_BOOL_FIELDS = frozenset({"disclaimer_accepted", "terms_accepted"})


def _parse_int(value: Any, *, default: int | None = None) -> int | None:
    if value is None or value == "":
        return default
    if isinstance(value, bool):
        return int(value)
    try:
        return int(str(value).strip())
    except (ValueError, TypeError):
        return default


def _parse_bool(value: Any, *, default: bool = False) -> bool:
    if value is None or value == "":
        return default
    if isinstance(value, bool):
        return value
    lowered = str(value).strip().lower()
    if lowered in ("true", "1", "yes", "on"):
        return True
    if lowered in ("false", "0", "no", "off"):
        return False
    return default


def _sanitize_int_fields(target: dict[str, Any], *, keys: set[str] | None = None) -> None:
    field_names = keys if keys is not None else set(VISITOR_INT_DEFAULTS.keys())
    for field in field_names:
        if field not in target:
            continue
        default = VISITOR_INT_DEFAULTS.get(field)
        target[field] = _parse_int(target[field], default=default)


def _sanitize_bool_fields(target: dict[str, Any], *, keys: set[str] | None = None) -> None:
    field_names = keys if keys is not None else set(VISITOR_BOOL_FIELDS)
    for field in field_names:
        if field not in target:
            continue
        target[field] = _parse_bool(target[field])


def _sanitize_model_scalar_fields(target: dict[str, Any]) -> None:
    """Coerce dates, integers, and booleans before ORM create/update."""
    _sanitize_date_fields(target, keys=set(target.keys()) & VISITOR_DATE_FIELDS)
    _sanitize_int_fields(target, keys=set(target.keys()) & set(VISITOR_INT_DEFAULTS.keys()))
    _sanitize_bool_fields(target, keys=set(target.keys()) & VISITOR_BOOL_FIELDS)


def _is_blob_string(value: Any) -> bool:
    if not isinstance(value, str):
        return False
    return value.startswith("data:") or len(value) > 500


def _first_photo_blob(*sources: Any) -> str | None:
    """Return the first data-URL / large image string from candidates."""
    for source in sources:
        if isinstance(source, str) and _is_blob_string(source):
            return source
        if isinstance(source, list):
            for item in source:
                if isinstance(item, str) and _is_blob_string(item):
                    return item
        if isinstance(source, dict):
            for key in ("visitor_photos", "visitorPhotos", "photo_capture", "photoCapture"):
                found = _first_photo_blob(source.get(key))
                if found:
                    return found
    return None


def visitor_has_profile_photo(visitor: Visitor) -> bool:
    """True when the visitor record stores at least one photograph."""
    if _is_blob_string(visitor.captured_photo) or _is_blob_string(visitor.profile_image):
        return True
    extra = visitor.extra_data if isinstance(visitor.extra_data, dict) else {}
    return _first_photo_blob(
        extra.get("visitor_photos"),
        extra.get("visitorPhotos"),
        extra.get("draft_form_data"),
    ) is not None


def parse_data_url_image(data_url: str) -> tuple[str, bytes] | None:
    """Decode a data:image/...;base64,... string to (content_type, raw bytes)."""
    if not isinstance(data_url, str) or not data_url.startswith("data:"):
        return None
    try:
        import base64

        header, encoded = data_url.split(",", 1)
        mime = header.split(";")[0].replace("data:", "").strip() or "image/jpeg"
        return mime, base64.b64decode(encoded)
    except (ValueError, TypeError):
        return None


def get_visitor_profile_photo_bytes(visitor: Visitor) -> tuple[str, bytes] | None:
    """Load the best available visitor photo from stored fields."""
    extra = visitor.extra_data if isinstance(visitor.extra_data, dict) else {}
    draft = extra.get("draft_form_data") if isinstance(extra.get("draft_form_data"), dict) else {}
    blob = _first_photo_blob(
        visitor.captured_photo,
        visitor.profile_image,
        extra.get("visitor_photos"),
        extra.get("visitorPhotos"),
        draft.get("visitorPhotos"),
        draft.get("visitor_photos"),
    )
    if not blob:
        return None
    return parse_data_url_image(blob)


def _sync_visitor_photo_fields(out: dict[str, Any]) -> None:
    """Ensure first gallery photo is copied to captured_photo / profile_image columns."""
    extra = out.get("extra_data") if isinstance(out.get("extra_data"), dict) else {}
    first = _first_photo_blob(
        out.get("visitor_photos"),
        out.get("visitorPhotos"),
        out.get("captured_photo"),
        out.get("photo_capture"),
        out.get("photoCapture"),
        out.get("profile_image"),
        extra.get("visitor_photos") if isinstance(extra, dict) else None,
    )
    if not first:
        return
    if not out.get("captured_photo"):
        out["captured_photo"] = first
    if not out.get("profile_image"):
        out["profile_image"] = first


def _store_blob_on_visitor(model_fields: dict[str, Any], blob: str) -> None:
    """Place image/document data on a TextField column."""
    if not model_fields.get("captured_photo"):
        model_fields["captured_photo"] = blob
    elif not model_fields.get("profile_image"):
        model_fields["profile_image"] = blob
    elif not model_fields.get("front_image"):
        model_fields["front_image"] = blob
    else:
        model_fields["additional_document"] = blob


def _sanitize_char_fields(model_fields: dict[str, Any]) -> None:
    """Truncate CharField values and relocate misplaced base64 blobs."""
    for field in Visitor._meta.fields:
        if not isinstance(field, (models.CharField, models.EmailField)):
            continue
        name = field.name
        if name not in model_fields:
            continue
        val = model_fields[name]
        if val is None or val == "":
            continue
        s = str(val)
        max_len = field.max_length
        if len(s) <= max_len:
            continue
        if _is_blob_string(s):
            _store_blob_on_visitor(model_fields, s)
            if name == "full_name":
                # Do not overwrite with a generic label; keep empty for resolve_visitor_display_name
                model_fields[name] = ""
            else:
                model_fields[name] = ""
        else:
            model_fields[name] = s[:max_len]


def strip_large_fields_for_list(data: dict[str, Any]) -> dict[str, Any]:
    """Remove heavy base64 payloads from list API responses."""
    out: dict[str, Any] = {}
    for key, value in data.items():
        if key in VISITOR_RESPONSE_BLOB_KEYS:
            if isinstance(value, str) and _is_blob_string(value):
                out[f"has_{key}"] = True
            elif isinstance(value, list) and value and isinstance(value[0], str) and _is_blob_string(value[0]):
                out[f"has_{key}"] = True
            elif isinstance(value, dict) and key == "draft_form_data":
                out[key] = strip_large_fields_for_list(value)
            else:
                out[key] = value
            continue
        if isinstance(value, str) and _is_blob_string(value):
            out[f"has_{key}"] = True
            continue
        if isinstance(value, dict):
            out[key] = strip_large_fields_for_list(value)
        elif isinstance(value, list):
            out[key] = [
                strip_large_fields_for_list(item) if isinstance(item, dict) else item
                for item in value
            ]
        else:
            out[key] = value
    return out


def _payload_has_key(out: dict[str, Any], *keys: str) -> bool:
    return any(k in out for k in keys)


def resolve_visitor_display_name(visitor: Visitor) -> str:
    """Best label for UI when full_name is missing or was reset to Unknown Visitor."""
    stored = (visitor.full_name or "").strip()
    if stored and stored != "Unknown Visitor":
        return stored

    extra = visitor.extra_data if isinstance(visitor.extra_data, dict) else {}
    draft = extra.get("draft_form_data") if isinstance(extra.get("draft_form_data"), dict) else {}

    for src in (extra, draft):
        for key in ("fullName", "full_name", "name"):
            val = src.get(key)
            if isinstance(val, str):
                label = val.strip()
                if label and label != "Unknown Visitor":
                    return label

    cnic = (visitor.cnic_number or visitor.cnic_passport or "").strip()
    if cnic:
        return cnic

    qr = (visitor.qr_code_id or "").strip()
    if qr:
        return qr

    return stored or f"Visitor #{visitor.pk}"


def normalize_payload(data: dict[str, Any], *, partial: bool = False) -> dict[str, Any]:
    """Flatten camelCase keys and coerce values for Visitor model."""
    out: dict[str, Any] = {}
    for key, value in data.items():
        nk = _normalize_key(key)
        out[nk] = value

    if not partial and out.get("full_name") in (None, ""):
        out["full_name"] = "Unknown Visitor"

    if not partial or _payload_has_key(out, "visitor_type", "registration_type"):
        vt_choices = [c[0] for c in Visitor.VISITOR_TYPE_CHOICES]
        out["visitor_type"] = _coerce_choice(
            out.get("visitor_type") or out.get("registration_type"),
            vt_choices,
            "general",
            VISITOR_TYPE_MAP,
        )

    if not partial or "nationality" in out:
        nat_choices = [c[0] for c in Visitor.NATIONALITY_CHOICES]
        out["nationality"] = _coerce_choice(out.get("nationality"), nat_choices, "pakistan", NATIONALITY_MAP)

    if not partial or "visit_purpose" in out:
        vp_choices = [c[0] for c in Visitor.VISIT_PURPOSE_CHOICES]
        out["visit_purpose"] = _coerce_choice(out.get("visit_purpose"), vp_choices, "other", VISIT_PURPOSE_MAP)

    if not partial or _payload_has_key(out, "department_to_visit", "department"):
        dept_choices = [c[0] for c in Visitor.DEPARTMENT_CHOICES]
        out["department_to_visit"] = _coerce_choice(out.get("department_to_visit"), dept_choices, "admin")

    if out.get("cnic_number") in (None, "") and out.get("cnic_passport"):
        out["cnic_number"] = out["cnic_passport"]

    if out.get("host_officer_name") in (None, "") and out.get("host_full_name"):
        out["host_officer_name"] = out["host_full_name"]

    if out.get("captured_photo") in (None, "") and out.get("photo_capture"):
        out["captured_photo"] = out["photo_capture"]

    if not partial or _payload_has_key(out, "preferred_visit_date", "preferred_date", "visit_date"):
        if out.get("preferred_visit_date") in (None, ""):
            pd = _parse_date(out.get("preferred_date") or out.get("visit_date"))
            if pd:
                out["preferred_visit_date"] = pd

    _sanitize_date_fields(out)

    if out.get("email") and not out.get("email_address"):
        out["email_address"] = out["email"]
    if out.get("phone") and not out.get("mobile_number"):
        out["mobile_number"] = out["phone"]

    _sanitize_int_fields(out)
    _sanitize_bool_fields(out)
    _sync_visitor_photo_fields(out)

    return out


def split_visitor_payload(
    data: dict[str, Any],
    *,
    registration_source: str = "",
    partial: bool = False,
) -> tuple[dict[str, Any], dict[str, Any]]:
    """Return (model_fields, extra_data) from a normalized payload."""
    normalized = normalize_payload(data, partial=partial)
    if registration_source:
        normalized["registration_source"] = registration_source

    model_fields: dict[str, Any] = {}
    extra: dict[str, Any] = dict(normalized.get("extra_data") or {})

    for key, value in normalized.items():
        if key == "extra_data":
            if isinstance(value, dict):
                extra.update(value)
            continue
        if key in VISITOR_DIRECT_FIELDS:
            model_fields[key] = value
        else:
            extra[key] = value

    if not partial:
        if not model_fields.get("mobile_number"):
            model_fields["mobile_number"] = "0000000000"
        if not model_fields.get("registration_status"):
            model_fields["registration_status"] = "approved"
        if not model_fields.get("approval_status"):
            needs_approval = str(model_fields.get("approver_required", "")).lower() in (
                "yes",
                "true",
                "1",
                "required",
            )
            model_fields["approval_status"] = "pending" if needs_approval else "approved"

    _sanitize_model_scalar_fields(model_fields)
    _sanitize_char_fields(model_fields)

    return model_fields, extra


def apply_registered_by_from_request(
    model_fields: dict[str, Any],
    request: Any | None,
) -> None:
    """Set registered_by_* from the authenticated user when not already provided."""
    if request is None:
        return
    user = getattr(request, "user", None)
    if not user or not getattr(user, "is_authenticated", False):
        return
    if not model_fields.get("registered_by_user_id"):
        model_fields["registered_by_user_id"] = user.id
    username = (getattr(user, "username", None) or "").strip()
    if username and not (model_fields.get("registered_by_username") or "").strip():
        model_fields["registered_by_username"] = username


def visitor_created_by_label(visitor: Visitor) -> str:
    username = (visitor.registered_by_username or "").strip()
    if username:
        return username
    if visitor.registered_by_user_id:
        return f"User #{visitor.registered_by_user_id}"
    return ""


def merge_extra_into_response(base: dict[str, Any], visitor: Visitor) -> dict[str, Any]:
    """Merge extra_data and aliases into API response dict."""
    extra = visitor.extra_data or {}
    if isinstance(extra, dict):
        for k, v in extra.items():
            if k not in base or base.get(k) in (None, "", [], {}):
                base[k] = v
    base["registration_source"] = visitor.registration_source or base.get("registration_source")
    base["registration_status"] = visitor.registration_status or "approved"
    base["approval_status"] = visitor.approval_status or "pending"
    base["email"] = base.get("email_address") or extra.get("email")
    base["phone"] = base.get("mobile_number") or extra.get("phone")
    if visitor.created_at:
        base["created_at"] = visitor.created_at.isoformat()
    base["created_by"] = visitor_created_by_label(visitor)
    base["full_name"] = resolve_visitor_display_name(visitor)
    return base
