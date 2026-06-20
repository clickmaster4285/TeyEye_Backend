from rest_framework import serializers
from django.utils import timezone
from .models import (
    User,
    Staff,
    Attendance,
    LeaveType,
    LeaveRequest,
    PayrollRun,
    PayrollEntry,
)
from django.contrib.auth import authenticate
from .permissions import (
    GLOBAL_ADMIN_ROLE,
    LOCATION_ADMIN_ROLE,
    get_location_scope,
    is_global_admin,
    location_admin_may_assign_role,
)


# -----------------------------
# Login Serializers
# -----------------------------
class LoginSerializer(serializers.Serializer):
    username = serializers.CharField(write_only=True)
    password = serializers.CharField(write_only=True, style={"input_type": "password"})

    def validate(self, data):
        username = data.get("username")
        password = data.get("password")
        if not username or not password:
            raise serializers.ValidationError("Username and password are required.")
        user = authenticate(request=self.context.get("request"), username=username, password=password)
        if not user:
            raise serializers.ValidationError("Invalid username or password.")
        if not user.is_active:
            raise serializers.ValidationError("User account is disabled.")
        if getattr(user, "is_deleted", False):
            raise serializers.ValidationError("User account is disabled.")
        data["user"] = user
        return data


class LoginResponseSerializer(serializers.Serializer):
    token = serializers.CharField(read_only=True)
    user = serializers.SerializerMethodField()

    def get_user(self, obj):
        user = obj["user"]
        return {
            "id": user.id,
            "username": user.username,
            "email": user.email,
            "role": user.role,
            "phone": user.phone,
            "location": user.location or "",
            "full_name": user.full_name or "",
            "cnic": user.cnic or "",
            "office_phone_1": user.office_phone_1 or "",
            "office_phone_2": user.office_phone_2 or "",
            "fax_no": user.fax_no or "",
            "cell_no": user.cell_no or user.phone or "",
            "address": user.address or "",
            "designation": user.designation or "",
            "employee_id": user.employee_id or "",
            "posting_date": user.posting_date.isoformat() if user.posting_date else None,
            "collectorate": user.collectorate or "",
            "effective_date": user.effective_date.isoformat() if user.effective_date else None,
            "we_boc_role": user.we_boc_role or "",
            "is_active": user.is_active,
        }


# -----------------------------
# User Serializer (for creating users)
# -----------------------------
USER_PROFILE_FIELDS = [
    "full_name",
    "cnic",
    "office_phone_1",
    "office_phone_2",
    "fax_no",
    "cell_no",
    "address",
    "designation",
    "employee_id",
    "posting_date",
    "collectorate",
    "effective_date",
    "we_boc_role",
]


class UserCreateSerializer(serializers.ModelSerializer):
    date_joined = serializers.DateTimeField(read_only=True)
    last_login = serializers.DateTimeField(read_only=True)
    can_delete = serializers.SerializerMethodField()

    class Meta:
        model = User
        fields = [
            "id",
            "username",
            "email",
            "password",
            "role",
            "phone",
            "location",
            "is_active",
            "date_joined",
            "last_login",
            "can_delete",
            *USER_PROFILE_FIELDS,
        ]
        extra_kwargs = {
            "password": {"write_only": True, "required": False},
            "posting_date": {"required": False, "allow_null": True},
            "effective_date": {"required": False, "allow_null": True},
        }

    def get_can_delete(self, obj):
        request = self.context.get("request")
        actor = getattr(request, "user", None) if request else None
        if obj.role == GLOBAL_ADMIN_ROLE:
            return False
        if obj.role == LOCATION_ADMIN_ROLE:
            return bool(actor and is_global_admin(actor))
        return True

    def validate_username(self, value):
        username = (value or "").strip()
        if not username:
            raise serializers.ValidationError("Username is required.")
        qs = User.objects.filter(username__iexact=username, is_deleted=False)
        if self.instance:
            qs = qs.exclude(pk=self.instance.pk)
        if qs.exists():
            raise serializers.ValidationError("This username is already taken.")
        return username

    def validate_password(self, value):
        if not value:
            return value
        if len(value) < 6:
            raise serializers.ValidationError("Password must be at least 6 characters.")
        return value

    def validate(self, attrs):
        if self.instance is None and not attrs.get("password"):
            raise serializers.ValidationError({"password": "Password is required."})
        cell = (attrs.get("cell_no") or "").strip()
        phone = (attrs.get("phone") or "").strip()
        if cell and not phone:
            attrs["phone"] = cell
        elif phone:
            attrs["phone"] = phone
            if cell:
                attrs["cell_no"] = cell
        elif self.instance is None:
            attrs["phone"] = "0000000000"
        else:
            attrs["phone"] = phone or (self.instance.phone if self.instance else "0000000000")
        if not (attrs.get("full_name") or "").strip() and self.instance is None:
            raise serializers.ValidationError({"full_name": "Name is required."})

        role = attrs.get("role") or (self.instance.role if self.instance else None)
        location = attrs.get("location", "")
        if self.instance is not None and "location" not in attrs:
            location = self.instance.location or ""

        if role == GLOBAL_ADMIN_ROLE:
            attrs["location"] = ""
        elif role == LOCATION_ADMIN_ROLE:
            if not (location or "").strip():
                raise serializers.ValidationError(
                    {"location": "Location is required for Location Administrator."}
                )

        request = self.context.get("request")
        actor = getattr(request, "user", None) if request else None
        if actor and getattr(actor, "is_authenticated", False):
            scope = get_location_scope(actor)
            if scope:
                attrs["location"] = scope
            if role and not location_admin_may_assign_role(actor, role):
                raise serializers.ValidationError(
                    {"role": "You cannot assign this role."}
                )

        return attrs

    def create(self, validated_data):
        password = validated_data.pop("password")
        user = User(**validated_data)
        user.set_password(password)
        user.save()
        return user

    def update(self, instance, validated_data):
        password = validated_data.pop("password", None)
        for attr, value in validated_data.items():
            setattr(instance, attr, value)
        if password:
            instance.set_password(password)
        instance.save()
        return instance


# -----------------------------
# Staff Serializer (Full) – all template fields
# -----------------------------
class StaffSerializer(serializers.ModelSerializer):
    user_details = serializers.SerializerMethodField(read_only=True)
    national_id = serializers.SerializerMethodField(read_only=True)

    class Meta:
        model = Staff
        fields = "__all__"
        read_only_fields = ["created_at"]

    def get_national_id(self, obj):
        return getattr(obj, "national_id", None) or obj.cnic

    def get_user_details(self, obj):
        if obj.user:
            return {
                "id": obj.user.id,
                "username": obj.user.username,
                "email": obj.user.email,
                "role": obj.user.role,
                "phone": obj.user.phone,
                "is_active": obj.user.is_active,
            }
        return None


# -----------------------------
# Staff Create Serializer
# Accepts full HR template payload; maps first_name+last_name -> full_name, national_id -> cnic, etc.
# -----------------------------
class StaffCreateSerializer(serializers.ModelSerializer):
    first_name = serializers.CharField(required=False, write_only=True)
    last_name = serializers.CharField(required=False, write_only=True)
    national_id = serializers.CharField(required=False, write_only=True)
    street_address = serializers.CharField(required=False, write_only=True)
    emergency_contact_phone = serializers.CharField(required=False, write_only=True)
    emergency_contact_name = serializers.CharField(required=False, write_only=True)
    date_of_joining = serializers.DateField(required=False, write_only=True)

    class Meta:
        model = Staff
        fields = [
            "user", "full_name", "father_name", "first_name", "last_name", "cnic", "national_id",
            "date_of_birth", "gender", "marital_status", "blood_group", "profile_image",
            "email", "phone_primary", "phone_alternate", "address", "street_address",
            "city", "state", "country", "postal_code",
            "employee_id",
            "personal_number",
            "bps",
            "qualification",
            "current_posting",
            "collector_name",
            "transferred_from",
            "transferred_to",
            "designation",
            "department",
            "branch_location",
            "manager",
            "employment_type", "joining_date", "probation_end_date",
            "work_shift_start", "work_shift_end", "job_status",
            "salary", "bank_account", "iban", "salary_type", "tax_id", "allowances",
            "role_access_level", "system_permissions",
            "emergency_contact", "emergency_contact_name", "emergency_contact_relationship",
            "emergency_contact_phone", "emergency_contact_address",
            "resume_file", "joining_letter_file", "contract_file", "id_proof_file",
            "tax_form_file", "certificates_file", "background_check_status",
            "skills_competencies", "languages_known", "performance_rating",
            "last_appraisal_date", "leave_balance", "notes", "created_at",
            "date_of_joining", "record_source",
        ]
        read_only_fields = ["created_at"]
        extra_kwargs = {
            "user": {"read_only": True},
            "full_name": {"required": False},
            "cnic": {"required": False},
            "address": {"required": False},
            "emergency_contact": {"required": False},
            "joining_date": {"required": False},
            "department": {"required": False},
            "designation": {"required": False},
        }

    def to_representation(self, instance):
        data = super().to_representation(instance)
        data["national_id"] = getattr(instance, "national_id", None) or instance.cnic
        for key in ("first_name", "last_name", "street_address", "emergency_contact_phone", "emergency_contact_name", "date_of_joining"):
            data.pop(key, None)
        return data

    def validate(self, data):
        initial = self.initial_data

        full_name = data.get("full_name")
        if not full_name:
            first = (initial.get("first_name") or data.get("first_name") or "").strip()
            last = (initial.get("last_name") or data.get("last_name") or "").strip()
            full_name = f"{first} {last}".strip() or initial.get("full_name")
        if not full_name:
            raise serializers.ValidationError(
                {"first_name": "Either full_name or first_name and last_name are required."}
            )
        data["full_name"] = full_name[:150]
        data["first_name"] = (initial.get("first_name") or data.get("first_name") or "").strip()[:80] or None
        data["last_name"] = (initial.get("last_name") or data.get("last_name") or "").strip()[:80] or None

        address = data.get("address") or initial.get("street_address")
        if not address:
            parts = [initial.get("city"), initial.get("state"), initial.get("country"), initial.get("postal_code")]
            address = ", ".join(str(p).strip() for p in parts if p) or initial.get("address")
        if not address:
            raise serializers.ValidationError(
                {"street_address": "Either address or street_address (or city/state/country) is required."}
            )
        data["address"] = address

        ec = (
            data.get("emergency_contact")
            or initial.get("emergency_contact_phone") or data.get("emergency_contact_phone")
            or initial.get("emergency_contact_name") or data.get("emergency_contact_name")
            or initial.get("emergency_contact")
        )
        if not ec:
            raise serializers.ValidationError(
                {"emergency_contact_phone": "Either emergency_contact or emergency_contact_phone/emergency_contact_name is required."}
            )
        data["emergency_contact"] = str(ec)[:100]

        national_id_val = initial.get("national_id") or data.get("national_id") or data.get("cnic")
        if not national_id_val:
            raise serializers.ValidationError({"national_id": "National ID / CNIC is required."})
        cnic_clean = "".join(c for c in str(national_id_val) if c.isdigit())[:15]
        data["cnic"] = cnic_clean or str(national_id_val)[:15]
        if Staff.objects.filter(cnic=data["cnic"]).exists():
            raise serializers.ValidationError({"national_id": "Staff with this National ID already exists."})
        data["national_id"] = str(national_id_val)[:30]

        doj = initial.get("date_of_joining") or data.get("date_of_joining")
        if doj:
            data["joining_date"] = doj
        if not data.get("joining_date"):
            data["joining_date"] = timezone.now().date()

        if not data.get("department"):
            raise serializers.ValidationError({"department": "Department is required."})
        if not data.get("designation"):
            raise serializers.ValidationError({"designation": "Designation is required."})

        data.setdefault("record_source", Staff.RECORD_SOURCE_DATABASE)

        personal_number = str(initial.get("personal_number") or data.get("personal_number") or "").strip()
        if personal_number:
            data["personal_number"] = personal_number[:50]

        father_name = str(initial.get("father_name") or data.get("father_name") or "").strip()
        data["father_name"] = father_name[:150] or None

        for key in ("street_address", "emergency_contact_phone", "emergency_contact_name", "date_of_joining"):
            data.pop(key, None)

        return data


# -----------------------------
# Staff Update Serializer
# -----------------------------
class StaffUpdateSerializer(serializers.ModelSerializer):
    national_id = serializers.CharField(source="cnic", read_only=True)

    class Meta:
        model = Staff
        fields = "__all__"
        read_only_fields = ["created_at", "cnic"]


# -----------------------------
# Staff List Serializer (Lightweight – only fields that exist in original schema so list works before/after migration)
# -----------------------------
class StaffListSerializer(serializers.ModelSerializer):
    national_id = serializers.SerializerMethodField(read_only=True)
    face_enrolled = serializers.SerializerMethodField(read_only=True)

    class Meta:
        model = Staff
        fields = [
            "id",
            "full_name",
            "father_name",
            "cnic",
            "national_id",
            "designation",
            "department",
            "emergency_contact",
            "profile_image",
            "face_enrolled",
            "user",
            "employee_id",
            "personal_number",
            "phone_primary",
            "joining_date",
            "branch_location",
            "bps",
            "qualification",
            "current_posting",
            "collector_name",
            "transferred_from",
            "transferred_to",
            "employment_type",
            "job_status",
            "record_source",
        ]

    def get_national_id(self, obj):
        # Prefer model field if present (after migration), else cnic
        try:
            return getattr(obj, "national_id", None) or obj.cnic
        except Exception:
            return obj.cnic

    def get_face_enrolled(self, obj):
        if not obj.profile_image:
            return False
        try:
            from ml.face_sync import staff_needs_face_enrollment

            return not staff_needs_face_enrollment(obj)
        except Exception:
            return obj.face_embeddings.filter(is_active=True).exists()


# -----------------------------
# Link User to Staff Serializer
# -----------------------------
class LinkUserToStaffSerializer(serializers.Serializer):
    user_id = serializers.IntegerField()
    
    def validate_user_id(self, value):
        try:
            user = User.objects.get(id=value)
            if hasattr(user, 'staff_profile'):
                raise serializers.ValidationError("This user is already linked to a staff member.")
            return value
        except User.DoesNotExist:
            raise serializers.ValidationError("User not found.")


# -----------------------------
# Attendance Serializers
# -----------------------------
class AttendanceSerializer(serializers.ModelSerializer):
    username = serializers.CharField(source="user.username", read_only=True)
    staff_name = serializers.SerializerMethodField(read_only=True)

    class Meta:
        model = Attendance
        fields = ["id", "user", "username", "staff_name", "date", "check_in", "check_out", "image"]
    
    def get_staff_name(self, obj):
        if hasattr(obj.user, "staff_profile"):
            return obj.user.staff_profile.full_name
        return None


# -----------------------------
# Leave Serializers (government-aligned)
# -----------------------------
class LeaveTypeSerializer(serializers.ModelSerializer):
    class Meta:
        model = LeaveType
        fields = ["id", "name", "code", "max_days_per_year", "requires_approval", "is_paid", "is_active", "created_at"]


class LeaveRequestSerializer(serializers.ModelSerializer):
    staff_name = serializers.CharField(source="staff.full_name", read_only=True)
    leave_type_name = serializers.CharField(source="leave_type.name", read_only=True)
    leave_type_code = serializers.CharField(source="leave_type.code", read_only=True)

    class Meta:
        model = LeaveRequest
        fields = [
            "id", "staff", "staff_name", "leave_type", "leave_type_name", "leave_type_code",
            "from_date", "to_date", "days", "reason", "status",
            "approved_by", "approved_at", "rejection_reason",
            "created_at", "updated_at",
        ]
        read_only_fields = ["approved_by", "approved_at"]


class LeaveRequestCreateSerializer(serializers.ModelSerializer):
    class Meta:
        model = LeaveRequest
        fields = ["staff", "leave_type", "from_date", "to_date", "days", "reason"]


# -----------------------------
# Payroll Serializers (government-aligned)
# -----------------------------
class PayrollEntrySerializer(serializers.ModelSerializer):
    staff_name = serializers.CharField(source="staff.full_name", read_only=True)
    employee_id = serializers.CharField(source="staff.employee_id", read_only=True)

    class Meta:
        model = PayrollEntry
        fields = [
            "id", "run", "staff", "staff_name", "employee_id",
            "basic_salary", "allowances", "gross_salary",
            "income_tax", "eobi_or_sss", "other_deductions", "net_salary",
            "created_at",
        ]


class PayrollRunSerializer(serializers.ModelSerializer):
    entries = PayrollEntrySerializer(many=True, read_only=True)
    entries_count = serializers.SerializerMethodField()

    class Meta:
        model = PayrollRun
        fields = [
            "id", "period_label", "period_start", "period_end", "status",
            "total_gross", "total_net", "employee_count",
            "created_by", "created_at", "processed_at",
            "entries", "entries_count",
        ]

    def get_entries_count(self, obj):
        return obj.entries.count()


class PayrollRunCreateSerializer(serializers.ModelSerializer):
    class Meta:
        model = PayrollRun
        fields = ["period_label", "period_start", "period_end"]

