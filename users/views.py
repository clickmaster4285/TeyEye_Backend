import os
from django.utils import timezone
from django.http import FileResponse, Http404
from django.conf import settings
from django.core.files.base import ContentFile
from rest_framework import viewsets, status, filters
from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework.permissions import AllowAny, IsAuthenticated
from rest_framework.authtoken.models import Token
from rest_framework.serializers import ValidationError
from rest_framework.decorators import action
from rest_framework.exceptions import PermissionDenied
from rest_framework.parsers import FormParser, JSONParser, MultiPartParser
from django_filters.rest_framework import DjangoFilterBackend
from ml.client import MLServiceError, ml_recognize_face, ml_service_enabled
from django.db.models import Q
from .models import (
    Staff,
    Attendance,
    User,
    LeaveType,
    LeaveRequest,
    PayrollRun,
    PayrollEntry,
)
from .permissions import IsAdminOrHR
from .permissions import (
    apply_location_filter,
    is_global_admin,
    GLOBAL_ADMIN_ROLE,
    LOCATION_ADMIN_ROLE,
)
from .serializers import (
    StaffCreateSerializer,
    StaffSerializer,
    StaffListSerializer,
    StaffUpdateSerializer,
    LinkUserToStaffSerializer,
    UserCreateSerializer,
    LoginSerializer,
    LoginResponseSerializer,
    AttendanceSerializer,
    LeaveTypeSerializer,
    LeaveRequestSerializer,
    LeaveRequestCreateSerializer,
    PayrollRunSerializer,
    PayrollRunCreateSerializer,
    PayrollEntrySerializer,
)
from logs.middleware import create_activity_log
from decimal import Decimal


class LoginView(APIView):
    """POST /api/auth/login/ with username & password. Returns token and user info. No auth required."""
    permission_classes = [AllowAny]
    authentication_classes = []  # No token/session needed for login

    def post(self, request):
        try:
            serializer = LoginSerializer(data=request.data, context={"request": request})
            serializer.is_valid(raise_exception=True)
            user = serializer.validated_data["user"]
            token, _ = Token.objects.get_or_create(user=user)
            create_activity_log(user, request, "POST /api/auth/login (success)")
            return Response(
                LoginResponseSerializer({"token": token.key, "user": user}).data,
                status=status.HTTP_200_OK,
            )
        except ValidationError:
            create_activity_log(None, request, "POST /api/auth/login (failed)")
            raise


# -----------------------------
# User Views
# -----------------------------
class UserViewSet(viewsets.ModelViewSet):
    """ViewSet for managing users separately from staff"""
    queryset = User.objects.filter(is_deleted=False)
    permission_classes = [IsAdminOrHR]
    serializer_class = UserCreateSerializer
    filter_backends = [filters.SearchFilter, DjangoFilterBackend]
    search_fields = ["username", "email", "role", "full_name", "cnic", "employee_id"]
    filterset_fields = ["role", "is_active", "location"]

    def get_queryset(self):
        qs = User.objects.filter(is_deleted=False)
        return apply_location_filter(qs, self.request.user, field="location")

    def perform_create(self, serializer):
        user = serializer.save()
        create_activity_log(
            self.request.user,
            self.request,
            f"Created user: {user.username} (ID: {user.id})",
        )

    def perform_update(self, serializer):
        user = serializer.save()
        create_activity_log(
            self.request.user,
            self.request,
            f"Updated user: {user.username} (ID: {user.id})",
        )

    def destroy(self, request, *args, **kwargs):
        instance = self.get_object()
        if instance.role == GLOBAL_ADMIN_ROLE:
            raise PermissionDenied("Admin accounts cannot be deleted.")
        if instance.role == LOCATION_ADMIN_ROLE and not is_global_admin(request.user):
            raise PermissionDenied("Only the global administrator can delete location administrators.")
        if instance.pk == request.user.pk:
            raise PermissionDenied("You cannot delete your own account.")
        instance.is_deleted = True
        instance.is_active = False
        instance.save(update_fields=["is_deleted", "is_active"])
        create_activity_log(
            request.user,
            request,
            f"Deleted user: {instance.username} (ID: {instance.id})",
        )
        return Response(status=status.HTTP_204_NO_CONTENT)

    @action(detail=False, methods=["get"])
    def unlinked(self, request):
        """Get users that are not linked to any staff"""
        users = apply_location_filter(
            User.objects.filter(staff_profile__isnull=True, is_deleted=False),
            request.user,
            field="location",
        )
        serializer = self.get_serializer(users, many=True)
        return Response(serializer.data)


# -----------------------------
# Staff Views
# -----------------------------
class StaffViewSet(viewsets.ModelViewSet):
    """ViewSet for managing staff members"""
    permission_classes = [IsAdminOrHR]
    parser_classes = [MultiPartParser, FormParser, JSONParser]
    filter_backends = [filters.SearchFilter, DjangoFilterBackend, filters.OrderingFilter]
    search_fields = ["full_name", "cnic", "designation", "department"]
    filterset_fields = ["department", "designation"]
    ordering_fields = ["full_name", "created_at"]

    def get_queryset(self):
        return apply_location_filter(Staff.objects.all(), self.request.user, field="user__location")

    def get_serializer_class(self):
        if self.action == "create":
            return StaffCreateSerializer
        elif self.action in ["update", "partial_update"]:
            return StaffUpdateSerializer
        elif self.action == "list":
            return StaffListSerializer
        return StaffSerializer

    @staticmethod
    def _strip_multipart_photo_fields(request):
        """Uploaded files must not bind to the staff_photos JSON column."""
        data = request.data
        if not hasattr(data, "pop"):
            return
        if hasattr(data, "_mutable"):
            data._mutable = True
        try:
            data.pop("staff_photos", None)
        except TypeError:
            pass

    def create(self, request, *args, **kwargs):
        self._strip_multipart_photo_fields(request)
        return super().create(request, *args, **kwargs)

    def update(self, request, *args, **kwargs):
        self._strip_multipart_photo_fields(request)
        return super().update(request, *args, **kwargs)

    def partial_update(self, request, *args, **kwargs):
        self._strip_multipart_photo_fields(request)
        return super().partial_update(request, *args, **kwargs)

    def perform_create(self, serializer):
        """Create staff member without user account"""
        staff = serializer.save()
        from .staff_photos import apply_staff_photo_uploads

        photos_changed = apply_staff_photo_uploads(staff, self.request)
        if photos_changed:
            staff.refresh_from_db()
            try:
                from ml.face_sync import sync_staff_faces_after_save

                sync_staff_faces_after_save(staff, force=True)
            except Exception:
                pass
        create_activity_log(
            self.request.user,
            self.request,
            f"Created staff: {staff.full_name} (ID: {staff.id})"
        )

    def perform_update(self, serializer):
        """Update staff member"""
        staff = serializer.save()
        from .staff_photos import apply_staff_photo_uploads

        photos_changed = apply_staff_photo_uploads(staff, self.request)
        if photos_changed:
            staff.refresh_from_db()
            try:
                from ml.face_sync import sync_staff_faces_after_save

                sync_staff_faces_after_save(staff, force=True)
            except Exception:
                pass
        create_activity_log(
            self.request.user,
            self.request,
            f"Updated staff: {staff.full_name}"
        )

    def perform_destroy(self, instance):
        """Soft delete or hard delete? Let's do soft delete by unlinking user"""
        if instance.user:
            # Option 1: Deactivate user
            instance.user.is_active = False
            instance.user.save()
        # Option 2: Hard delete instance
        instance.delete()
        create_activity_log(
            self.request.user, 
            self.request, 
            f"Deleted staff: {instance.full_name}"
        )

    @action(detail=True, methods=["post"])
    def link_user(self, request, pk=None):
        """Link an existing user to a staff member"""
        staff = self.get_object()
        
        if staff.user:
            return Response(
                {"error": "Staff member already has a linked user account."},
                status=status.HTTP_400_BAD_REQUEST
            )
        
        serializer = LinkUserToStaffSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        
        try:
            user = User.objects.get(id=serializer.validated_data["user_id"])
            staff.user = user
            staff.save()

            try:
                from ml.face_sync import sync_staff_identity_after_user_link

                sync_staff_identity_after_user_link(staff)
            except Exception:
                pass

            create_activity_log(
                request.user,
                request,
                f"Linked user {user.username} to staff {staff.full_name}"
            )
            
            return Response(
                {"message": "User linked successfully", "staff": StaffSerializer(staff).data},
                status=status.HTTP_200_OK
            )
        except User.DoesNotExist:
            return Response(
                {"error": "User not found."},
                status=status.HTTP_404_NOT_FOUND
            )

    DOCUMENT_FIELDS = (
        "resume_file", "joining_letter_file", "contract_file",
        "id_proof_file", "tax_form_file", "certificates_file",
    )

    @action(detail=True, methods=["get"], url_path="document/(?P<field>[a-z_]+)")
    def document(self, request, pk=None, field=None):
        """Stream a staff document with Content-Disposition: attachment so it downloads."""
        if field not in self.DOCUMENT_FIELDS:
            raise Http404("Unknown document field.")
        staff = self.get_object()
        file_field = getattr(staff, field, None)
        if not file_field or not getattr(file_field, "name", None):
            raise Http404("No file.")
        path = file_field.path
        if not path or not os.path.isfile(path):
            raise Http404("File not found.")
        filename = os.path.basename(path)
        fh = open(path, "rb")
        response = FileResponse(fh, as_attachment=True, filename=filename)
        response["Content-Length"] = os.path.getsize(path)
        return response

    @action(detail=True, methods=["post"])
    def unlink_user(self, request, pk=None):
        """Unlink user from staff member"""
        staff = self.get_object()
        
        if not staff.user:
            return Response(
                {"error": "Staff member has no linked user account."},
                status=status.HTTP_400_BAD_REQUEST
            )
        
        user = staff.user
        staff.user = None
        staff.save()
        
        # Optionally deactivate user
        if request.data.get("deactivate_user", False):
            user.is_active = False
            user.save()
        
        create_activity_log(
            request.user,
            request,
            f"Unlinked user {user.username} from staff {staff.full_name}"
        )
        
        return Response(
            {"message": "User unlinked successfully"},
            status=status.HTTP_200_OK
        )

    @action(detail=True, methods=["post"])
    def create_user(self, request, pk=None):
        """Create a new user account for this staff member. Requires username, email, password, role, phone in body."""
        staff = self.get_object()
        
        if staff.user:
            return Response(
                {"error": "Staff member already has a linked user account."},
                status=status.HTTP_400_BAD_REQUEST
            )
        
        username = request.data.get("username") or (request.data.get("email") or "").split("@")[0] or f"staff_{staff.id}"
        user_data = {
            "username": request.data.get("username", username),
            "email": request.data.get("email", ""),
            "password": request.data.get("password"),
            "role": request.data.get("role", "RECEPTIONIST"),
            "phone": request.data.get("phone", staff.emergency_contact or ""),
            "location": request.data.get("location", ""),
        }
        
        if not user_data["email"]:
            return Response({"error": "Email is required."}, status=status.HTTP_400_BAD_REQUEST)
        if not user_data["password"]:
            return Response(
                {"error": "Password is required."},
                status=status.HTTP_400_BAD_REQUEST
            )
        
        serializer = UserCreateSerializer(data=user_data)
        serializer.is_valid(raise_exception=True)
        user = serializer.save()
        
        # Link user to staff
        staff.user = user
        staff.save()

        try:
            from ml.face_sync import sync_staff_identity_after_user_link

            sync_staff_identity_after_user_link(staff)
        except Exception:
            pass

        create_activity_log(
            request.user,
            request,
            f"Created and linked user {user.username} for staff {staff.full_name}"
        )
        
        return Response(
            {
                "message": "User created and linked successfully",
                "user": UserCreateSerializer(user).data,
                "staff": StaffSerializer(staff).data
            },
            status=status.HTTP_201_CREATED
        )


# -----------------------------
# Attendance Views
# -----------------------------
class AttendanceViewSet(viewsets.ModelViewSet):
    queryset = Attendance.objects.all().order_by("-date", "-check_in")
    permission_classes = [IsAdminOrHR]
    serializer_class = AttendanceSerializer
    filter_backends = [DjangoFilterBackend, filters.SearchFilter, filters.OrderingFilter]
    filterset_fields = ["user", "staff", "date", "user__role"]
    search_fields = ["user__username", "user__staff_profile__full_name", "staff__full_name"]
    ordering_fields = ["date", "check_in", "check_out"]

    def perform_create(self, serializer):
        # Default check_in to now when marking attendance
        extra = {}
        if not serializer.validated_data.get("check_in"):
            extra["check_in"] = timezone.now()
        attendance = serializer.save(**extra)
        
        create_activity_log(
            self.request.user,
            self.request,
            f"Marked attendance for {attendance.staff.full_name if attendance.staff_id else attendance.user.username}"
        )

    def perform_update(self, serializer):
        attendance = serializer.save()
        label = (
            attendance.staff.full_name
            if attendance.staff_id
            else (attendance.user.username if attendance.user_id else f"record {attendance.pk}")
        )
        create_activity_log(
            self.request.user,
            self.request,
            f"Updated attendance for {label} (ID: {attendance.id})",
        )

    def perform_destroy(self, instance):
        label = (
            instance.staff.full_name
            if instance.staff_id
            else (instance.user.username if instance.user_id else f"record {instance.pk}")
        )
        record_id = instance.id
        instance.delete()
        create_activity_log(
            self.request.user,
            self.request,
            f"Deleted attendance for {label} (ID: {record_id})",
        )

    @action(
        detail=False,
        methods=["post"],
        url_path="recognize",
        parser_classes=[MultiPartParser, FormParser],
    )
    def recognize(self, request):
        if not ml_service_enabled():
            return Response(
                {
                    "error": (
                        "ML service is not configured. Set ML_SERVICE_URL in backend/.env "
                        "and run the inference server: cd ml_services && python api_server.py"
                    )
                },
                status=status.HTTP_503_SERVICE_UNAVAILABLE,
            )

        image = request.FILES.get("image")
        if not image:
            return Response({"error": "image file is required."}, status=status.HTTP_400_BAD_REQUEST)

        auto_mark = str(request.data.get("auto_mark", "true")).lower() in ("true", "1", "yes")
        threshold_raw = request.data.get("threshold")
        image_bytes = image.read()

        try:
            result = ml_recognize_face(image_bytes, filename=image.name or "face.jpg")
        except MLServiceError as exc:
            return Response({"error": str(exc)}, status=exc.status_code or status.HTTP_503_SERVICE_UNAVAILABLE)

        identity = str(result.get("identity", "unknown"))
        similarity = float(result.get("similarity", 0))
        recognized = bool(result.get("recognized"))

        if threshold_raw is not None:
            try:
                recognized = identity != "unknown" and similarity >= float(threshold_raw)
            except (TypeError, ValueError):
                return Response({"error": "threshold must be a number."}, status=status.HTTP_400_BAD_REQUEST)

        if not recognized:
            return Response(
                {
                    "recognized": False,
                    "message": "No matching staff face found.",
                    "identity": identity,
                    "similarity": similarity,
                }
            )

        from users.attendance_service import (
            mark_attendance_for_staff,
            resolve_staff_for_face_identity,
            staff_is_enrolled_for_attendance,
        )

        staff_profile = resolve_staff_for_face_identity(identity)
        if not staff_profile:
            return Response(
                {
                    "recognized": False,
                    "message": "No matching staff face found in HR records.",
                    "identity": identity,
                    "similarity": similarity,
                }
            )

        if not staff_is_enrolled_for_attendance(staff_profile):
            return Response(
                {
                    "recognized": False,
                    "message": "Staff member has no enrolled face photos. Upload photos and sync embeddings.",
                    "identity": identity,
                    "similarity": similarity,
                }
            )

        user = staff_profile.user if staff_profile.user_id and not staff_profile.user.is_deleted else None
        payload = {
            "recognized": True,
            "user_id": user.id if user else None,
            "staff_id": staff_profile.id,
            "username": user.username if user else None,
            "staff_name": staff_profile.full_name,
            "similarity": similarity,
        }

        if not auto_mark:
            return Response(payload)

        action, attendance = mark_attendance_for_staff(staff_profile, source="kiosk", allow_checkout=True)
        payload["attendance"] = action
        if attendance:
            payload["record_id"] = attendance.id

        if action in ("check_in", "check_out") and attendance and image_bytes:
            attendance.image.save(image.name or "face.jpg", ContentFile(image_bytes), save=True)

        if action == "check_in":
            create_activity_log(
                request.user,
                request,
                f"Face check-in: {staff_profile.full_name} (similarity {similarity:.2f})",
            )
        elif action == "check_out":
            create_activity_log(
                request.user,
                request,
                f"Face check-out: {staff_profile.full_name} (similarity {similarity:.2f})",
            )

        return Response(payload)


# -----------------------------
# Leave Views
# -----------------------------
class LeaveTypeViewSet(viewsets.ModelViewSet):
    queryset = LeaveType.objects.filter(is_active=True).order_by("name")
    permission_classes = [IsAdminOrHR]
    serializer_class = LeaveTypeSerializer
    filterset_fields = ["code", "is_paid"]


class LeaveRequestViewSet(viewsets.ModelViewSet):
    queryset = LeaveRequest.objects.all().order_by("-from_date")
    permission_classes = [IsAdminOrHR]
    filter_backends = [DjangoFilterBackend, filters.SearchFilter]
    filterset_fields = ["staff", "leave_type", "status"]
    search_fields = ["staff__full_name", "reason"]

    def get_serializer_class(self):
        if self.action == "create":
            return LeaveRequestCreateSerializer
        return LeaveRequestSerializer

    def perform_create(self, serializer):
        req = serializer.save()
        create_activity_log(
            self.request.user,
            self.request,
            f"Leave request created: {req.staff.full_name} - {req.leave_type.code}"
        )

    @action(detail=True, methods=["post"], url_path="approve")
    def approve(self, request, pk=None):
        req = self.get_object()
        if req.status != "PENDING":
            return Response(
                {"error": "Only pending requests can be approved."},
                status=status.HTTP_400_BAD_REQUEST,
            )
        req.status = "APPROVED"
        req.approved_by = request.user
        req.approved_at = timezone.now()
        req.rejection_reason = None
        req.save()
        create_activity_log(request.user, request, f"Approved leave request {req.id}")
        return Response(LeaveRequestSerializer(req).data)

    @action(detail=True, methods=["post"], url_path="reject")
    def reject(self, request, pk=None):
        req = self.get_object()
        if req.status != "PENDING":
            return Response(
                {"error": "Only pending requests can be rejected."},
                status=status.HTTP_400_BAD_REQUEST,
            )
        reason = request.data.get("rejection_reason", "")
        req.status = "REJECTED"
        req.approved_by = request.user
        req.approved_at = timezone.now()
        req.rejection_reason = reason or None
        req.save()
        create_activity_log(request.user, request, f"Rejected leave request {req.id}")
        return Response(LeaveRequestSerializer(req).data)


# -----------------------------
# Payroll Views
# -----------------------------
class PayrollRunViewSet(viewsets.ModelViewSet):
    queryset = PayrollRun.objects.all().order_by("-period_start")
    permission_classes = [IsAdminOrHR]
    filter_backends = [DjangoFilterBackend]
    filterset_fields = ["status"]

    def get_serializer_class(self):
        if self.action == "create":
            return PayrollRunCreateSerializer
        return PayrollRunSerializer

    def perform_create(self, serializer):
        run = serializer.save(created_by=self.request.user)
        create_activity_log(
            self.request.user,
            self.request,
            f"Payroll run created: {run.period_label}",
        )

    @action(detail=True, methods=["post"], url_path="process")
    def process_run(self, request, pk=None):
        """Create payroll entries from all staff with salary and set run to PROCESSED."""
        run = self.get_object()
        if run.status not in ("DRAFT", None):
            return Response(
                {"error": "Run already processed or locked."},
                status=status.HTTP_400_BAD_REQUEST,
            )
        staff_with_salary = Staff.objects.exclude(salary__isnull=True).exclude(salary=0)
        total_gross = Decimal("0")
        total_net = Decimal("0")
        for staff in staff_with_salary:
            basic = staff.salary or Decimal("0")
            allowances = Decimal("0")
            gross = basic + allowances
            tax = Decimal("0")
            eobi = Decimal("0")
            other = Decimal("0")
            net = gross - tax - eobi - other
            PayrollEntry.objects.update_or_create(
                run=run,
                staff=staff,
                defaults={
                    "basic_salary": basic,
                    "allowances": allowances,
                    "gross_salary": gross,
                    "income_tax": tax,
                    "eobi_or_sss": eobi,
                    "other_deductions": other,
                    "net_salary": net,
                },
            )
            total_gross += gross
            total_net += net
        run.employee_count = staff_with_salary.count()
        run.total_gross = total_gross
        run.total_net = total_net
        run.status = "PROCESSED"
        run.processed_at = timezone.now()
        run.save()
        create_activity_log(request.user, request, f"Processed payroll run {run.period_label}")
        return Response(PayrollRunSerializer(run).data)