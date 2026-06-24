from django.contrib.auth.models import AbstractUser
from django.db import models
from django.utils import timezone


class User(AbstractUser):
    USERNAME_FIELD = "username"
    REQUIRED_FIELDS = ["email", "role", "phone"]

    ROLE_CHOICES = [
        ("ADMIN", "Admin"),
        ("LOCATION_ADMIN", "Location Administrator"),
        ("OPERATION_MANAGER", "Operation Manager"),
        ("INSPECTOR", "Inspector"),
        ("COLLECTOR", "Collector"),
        ("DEPUTY_COLLECTOR", "Deputy Collector"),
        ("ASSISTANT_COLLECTOR", "Assistant Collector"),
        ("RECEPTIONIST", "Receptionist"),
        ("GUARD", "Guard"),
        ("HR", "Human Resource"),
        ("WAREHOUSE_OFFICER", "Warehouse Officer"),
        ("WAREHOUSE_SUPERINTENDENT", "Warehouse Superintendent"),
        ("WAREHOUSE_IN_CHARGE", "Warehouse In-Charge"),
        ("EXAMINATION_OFFICER", "Examination Officer"),
        ("STOCK_CONTROLLER", "Stock Controller"),
        ("IT_ADMIN", "IT Administrator"),
        ("AUDITOR", "Auditor"),
        ("DETECTION_OFFICER", "Detection Officer"),
        ("FIR_OFFICER", "FIR Officer"),
        ("INVESTIGATION_OFFICER", "Investigation Officer"),
        ("SEIZING_OFFICER", "Seizing Officer"),
    ]

    LOCATION_CHOICES = [
        ("PESHAWAR", "Peshawar (Head Office)"),
        ("KOHAT", "Kohat"),
        ("NOWSHERA", "Nowshera"),
        ("MARDAN", "Mardan"),
        ("DI_KHAN", "DI Khan"),
    ]

    role = models.CharField(max_length=30, choices=ROLE_CHOICES)
    phone = models.CharField(max_length=20)
    location = models.CharField(
        max_length=20,
        choices=LOCATION_CHOICES,
        blank=True,
        default="",
    )
    # Extended profile (user management form)
    full_name = models.CharField(max_length=200, blank=True, default="")
    cnic = models.CharField(max_length=20, blank=True, default="")
    office_phone_1 = models.CharField(max_length=30, blank=True, default="")
    office_phone_2 = models.CharField(max_length=30, blank=True, default="")
    fax_no = models.CharField(max_length=30, blank=True, default="")
    cell_no = models.CharField(max_length=30, blank=True, default="")
    address = models.TextField(blank=True, default="")
    designation = models.CharField(max_length=150, blank=True, default="")
    employee_id = models.CharField(max_length=50, blank=True, default="")
    posting_date = models.DateField(null=True, blank=True)
    collectorate = models.CharField(max_length=150, blank=True, default="")
    effective_date = models.DateField(null=True, blank=True)
    we_boc_role = models.CharField(max_length=150, blank=True, default="")
    is_deleted = models.BooleanField(default=False)

    def __str__(self):
        return f"{self.username} - {self.role}"


class Staff(models.Model):
    """Full HR staff template. Required: full_name, cnic, address, department, designation, joining_date, emergency_contact."""
    user = models.OneToOneField(
        User,
        on_delete=models.CASCADE,
        related_name="staff_profile",
        null=True,
        blank=True,
    )
    # Personal
    full_name = models.CharField(max_length=150)
    father_name = models.CharField(max_length=150, null=True, blank=True)
    first_name = models.CharField(max_length=80, null=True, blank=True)
    last_name = models.CharField(max_length=80, null=True, blank=True)
    date_of_birth = models.DateField(null=True, blank=True)
    gender = models.CharField(max_length=20, null=True, blank=True)
    cnic = models.CharField(max_length=15, unique=True)
    national_id = models.CharField(max_length=30, null=True, blank=True)  # passport etc.
    marital_status = models.CharField(max_length=30, null=True, blank=True)
    blood_group = models.CharField(max_length=10, null=True, blank=True)
    profile_image = models.ImageField(upload_to="staff/", null=True, blank=True)
    # Contact
    email = models.EmailField(null=True, blank=True)
    phone_primary = models.CharField(max_length=20, null=True, blank=True)
    phone_alternate = models.CharField(max_length=20, null=True, blank=True)
    address = models.TextField(null=True, blank=True)
    street_address = models.CharField(max_length=255, null=True, blank=True)
    city = models.CharField(max_length=100, null=True, blank=True)
    state = models.CharField(max_length=100, null=True, blank=True)
    country = models.CharField(max_length=100, null=True, blank=True)
    postal_code = models.CharField(max_length=20, null=True, blank=True)
    # Job
    employee_id = models.CharField(max_length=50, null=True, blank=True, unique=True)
    personal_number = models.CharField(max_length=50, null=True, blank=True)
    bps = models.CharField(max_length=10, null=True, blank=True)
    qualification = models.CharField(max_length=200, null=True, blank=True)
    current_posting = models.CharField(max_length=300, null=True, blank=True)
    collector_name = models.CharField(max_length=200, null=True, blank=True)
    transferred_from = models.CharField(max_length=300, null=True, blank=True)
    transferred_to = models.CharField(max_length=300, null=True, blank=True)
    designation = models.CharField(max_length=100)
    department = models.CharField(max_length=100)
    branch_location = models.CharField(max_length=200, null=True, blank=True)
    manager = models.CharField(max_length=150, null=True, blank=True)
    employment_type = models.CharField(max_length=50, null=True, blank=True)
    joining_date = models.DateField(default=timezone.now)
    probation_end_date = models.DateField(null=True, blank=True)
    work_shift_start = models.TimeField(null=True, blank=True)
    work_shift_end = models.TimeField(null=True, blank=True)
    job_status = models.CharField(max_length=50, null=True, blank=True)
    # Salary
    salary = models.DecimalField(max_digits=12, decimal_places=2, null=True, blank=True)
    bank_account = models.CharField(max_length=100, null=True, blank=True)
    iban = models.CharField(max_length=50, null=True, blank=True)
    salary_type = models.CharField(max_length=30, null=True, blank=True)
    tax_id = models.CharField(max_length=50, null=True, blank=True)
    allowances = models.TextField(null=True, blank=True)
    # Access (summary; actual auth is on User)
    role_access_level = models.CharField(max_length=50, null=True, blank=True)
    system_permissions = models.TextField(null=True, blank=True)
    # Emergency
    emergency_contact = models.CharField(max_length=100, null=True, blank=True)
    emergency_contact_name = models.CharField(max_length=100, null=True, blank=True)
    emergency_contact_relationship = models.CharField(max_length=50, null=True, blank=True)
    emergency_contact_phone = models.CharField(max_length=20, null=True, blank=True)
    emergency_contact_address = models.TextField(null=True, blank=True)
    # Documents
    resume_file = models.FileField(upload_to="staff_docs/", null=True, blank=True)
    joining_letter_file = models.FileField(upload_to="staff_docs/", null=True, blank=True)
    contract_file = models.FileField(upload_to="staff_docs/", null=True, blank=True)
    id_proof_file = models.FileField(upload_to="staff_docs/", null=True, blank=True)
    tax_form_file = models.FileField(upload_to="staff_docs/", null=True, blank=True)
    certificates_file = models.FileField(upload_to="staff_docs/", null=True, blank=True)
    background_check_status = models.CharField(max_length=50, null=True, blank=True)
    # HR Analytics / Optional
    skills_competencies = models.TextField(null=True, blank=True)
    languages_known = models.TextField(null=True, blank=True)
    performance_rating = models.CharField(max_length=20, null=True, blank=True)
    last_appraisal_date = models.DateField(null=True, blank=True)
    leave_balance = models.PositiveIntegerField(null=True, blank=True)
    notes = models.TextField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    RECORD_SOURCE_DATABASE = "database"
    RECORD_SOURCE_DISPOSITION = "disposition"
    RECORD_SOURCE_CHOICES = [
        (RECORD_SOURCE_DATABASE, "Database"),
        (RECORD_SOURCE_DISPOSITION, "Disposition"),
    ]
    record_source = models.CharField(
        max_length=20,
        choices=RECORD_SOURCE_CHOICES,
        default=RECORD_SOURCE_DATABASE,
    )
    # Face recognition (SFace vector from profile_image — stored on staff row, not a separate table)
    FACE_EMBEDDING_MODEL_SFACE = "sface"
    face_embedding = models.JSONField(
        null=True,
        blank=True,
        help_text="Face feature vector for ML matching.",
    )
    face_embedding_dim = models.PositiveSmallIntegerField(default=0)
    face_embedding_model = models.CharField(max_length=32, blank=True, default="")
    face_identity_label = models.CharField(
        max_length=150,
        blank=True,
        default="",
        db_index=True,
        help_text="Name/username label pushed to ML for recognition.",
    )
    face_embedding_profile_key = models.CharField(
        max_length=500,
        blank=True,
        default="",
        help_text="profile_image path when face_embedding was generated.",
    )
    # Additional recognition photos (paths under MEDIA_ROOT) — same Staff row, no extra table.
    staff_photos = models.JSONField(
        default=list,
        blank=True,
        help_text="Ordered staff photo paths (max 5). First entry mirrors profile_image.",
    )
    face_embeddings = models.JSONField(
        default=list,
        blank=True,
        help_text="SFace vectors per staff photo: [{image_key, embedding, dim, model}, ...].",
    )

    def __str__(self):
        return f"{self.full_name} ({self.designation})"


class Attendance(models.Model):
    user = models.ForeignKey(
        User,
        on_delete=models.CASCADE,
        related_name="attendance_records",
        null=True,
        blank=True,
    )
    staff = models.ForeignKey(
        Staff,
        on_delete=models.CASCADE,
        related_name="staff_attendance_records",
        null=True,
        blank=True,
    )
    date = models.DateField(auto_now_add=True)
    check_in = models.DateTimeField(null=True, blank=True)
    check_out = models.DateTimeField(null=True, blank=True)
    image = models.ImageField(upload_to="attendance/", null=True, blank=True)
    video = models.FileField(
        upload_to="attendance/videos/",
        null=True,
        blank=True,
        help_text="Short camera clip captured when attendance was marked.",
    )

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=["user", "date"],
                condition=models.Q(user__isnull=False),
                name="users_attendance_unique_user_date",
            ),
            models.UniqueConstraint(
                fields=["staff", "date"],
                condition=models.Q(staff__isnull=False),
                name="users_attendance_unique_staff_date",
            ),
        ]

    def __str__(self):
        if self.user_id:
            return f"{self.user.username} - {self.date}"
        if self.staff_id:
            return f"{self.staff.full_name} - {self.date}"
        return f"Attendance {self.pk} - {self.date}"


# -----------------------------
# Leave (government-aligned: labour law leave types, audit trail)
# -----------------------------
class LeaveType(models.Model):
    """Leave types as per government / labour policy (e.g. annual, sick, casual, maternity)."""
    name = models.CharField(max_length=80)  # e.g. Annual, Sick, Casual, Maternity, Leave without pay
    code = models.CharField(max_length=20, unique=True)  # e.g. ANNUAL, SICK
    max_days_per_year = models.PositiveIntegerField(null=True, blank=True)  # policy cap
    requires_approval = models.BooleanField(default=True)
    is_paid = models.BooleanField(default=True)
    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return f"{self.name} ({self.code})"


class LeaveRequest(models.Model):
    """Employee leave request with approval workflow and audit (government compliance)."""
    STATUS_CHOICES = [
        ("PENDING", "Pending"),
        ("APPROVED", "Approved"),
        ("REJECTED", "Rejected"),
        ("CANCELLED", "Cancelled"),
    ]
    staff = models.ForeignKey(Staff, on_delete=models.CASCADE, related_name="leave_requests")
    leave_type = models.ForeignKey(LeaveType, on_delete=models.PROTECT, related_name="requests")
    from_date = models.DateField()
    to_date = models.DateField()
    days = models.PositiveIntegerField()  # working days
    reason = models.TextField(null=True, blank=True)
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default="PENDING")
    approved_by = models.ForeignKey(
        User, on_delete=models.SET_NULL, null=True, blank=True, related_name="leave_approvals"
    )
    approved_at = models.DateTimeField(null=True, blank=True)
    rejection_reason = models.TextField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["-from_date"]

    def __str__(self):
        return f"{self.staff.full_name} - {self.leave_type.code} ({self.from_date})"


# -----------------------------
# Payroll (government-aligned: tax, EOBI/SSS, deductions, audit)
# -----------------------------
class PayrollRun(models.Model):
    """Pay period run for salary processing (government audit trail)."""
    STATUS_CHOICES = [
        ("DRAFT", "Draft"),
        ("PROCESSED", "Processed"),
        ("LOCKED", "Locked"),
    ]
    period_label = models.CharField(max_length=50)  # e.g. "Jan 2024"
    period_start = models.DateField()
    period_end = models.DateField()
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default="DRAFT")
    total_gross = models.DecimalField(max_digits=14, decimal_places=2, null=True, blank=True)
    total_net = models.DecimalField(max_digits=14, decimal_places=2, null=True, blank=True)
    employee_count = models.PositiveIntegerField(default=0)
    created_by = models.ForeignKey(
        User, on_delete=models.SET_NULL, null=True, blank=True, related_name="payroll_runs_created"
    )
    created_at = models.DateTimeField(auto_now_add=True)
    processed_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering = ["-period_start"]

    def __str__(self):
        return f"{self.period_label} ({self.status})"


class PayrollEntry(models.Model):
    """Per-employee payroll entry (basic, allowances, deductions, tax, net) for government compliance."""
    run = models.ForeignKey(PayrollRun, on_delete=models.CASCADE, related_name="entries")
    staff = models.ForeignKey(Staff, on_delete=models.CASCADE, related_name="payroll_entries")
    basic_salary = models.DecimalField(max_digits=12, decimal_places=2, default=0)
    allowances = models.DecimalField(max_digits=12, decimal_places=2, default=0)
    gross_salary = models.DecimalField(max_digits=12, decimal_places=2, default=0)
    income_tax = models.DecimalField(max_digits=12, decimal_places=2, default=0)
    eobi_or_sss = models.DecimalField(max_digits=12, decimal_places=2, default=0)  # EOBI/SSS as per government
    other_deductions = models.DecimalField(max_digits=12, decimal_places=2, default=0)
    net_salary = models.DecimalField(max_digits=12, decimal_places=2, default=0)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        unique_together = [["run", "staff"]]
        ordering = ["staff__full_name"]

    def __str__(self):
        return f"{self.run.period_label} - {self.staff.full_name}"