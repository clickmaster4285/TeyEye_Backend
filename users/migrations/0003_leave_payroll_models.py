# Leave and Payroll models (government-aligned)

from django.conf import settings
from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):

    dependencies = [
        ("users", "0002_staff_extended_fields"),
    ]

    operations = [
        migrations.CreateModel(
            name="LeaveType",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("name", models.CharField(max_length=80)),
                ("code", models.CharField(max_length=20, unique=True)),
                ("max_days_per_year", models.PositiveIntegerField(blank=True, null=True)),
                ("requires_approval", models.BooleanField(default=True)),
                ("is_paid", models.BooleanField(default=True)),
                ("is_active", models.BooleanField(default=True)),
                ("created_at", models.DateTimeField(auto_now_add=True)),
            ],
        ),
        migrations.CreateModel(
            name="LeaveRequest",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("from_date", models.DateField()),
                ("to_date", models.DateField()),
                ("days", models.PositiveIntegerField()),
                ("reason", models.TextField(blank=True, null=True)),
                ("status", models.CharField(choices=[("PENDING", "Pending"), ("APPROVED", "Approved"), ("REJECTED", "Rejected"), ("CANCELLED", "Cancelled")], default="PENDING", max_length=20)),
                ("approved_at", models.DateTimeField(blank=True, null=True)),
                ("rejection_reason", models.TextField(blank=True, null=True)),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("updated_at", models.DateTimeField(auto_now=True)),
                ("approved_by", models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name="leave_approvals", to=settings.AUTH_USER_MODEL)),
                ("leave_type", models.ForeignKey(on_delete=django.db.models.deletion.PROTECT, related_name="requests", to="users.leavetype")),
                ("staff", models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name="leave_requests", to="users.staff")),
            ],
            options={
                "ordering": ["-from_date"],
            },
        ),
        migrations.CreateModel(
            name="PayrollRun",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("period_label", models.CharField(max_length=50)),
                ("period_start", models.DateField()),
                ("period_end", models.DateField()),
                ("status", models.CharField(choices=[("DRAFT", "Draft"), ("PROCESSED", "Processed"), ("LOCKED", "Locked")], default="DRAFT", max_length=20)),
                ("total_gross", models.DecimalField(blank=True, decimal_places=2, max_digits=14, null=True)),
                ("total_net", models.DecimalField(blank=True, decimal_places=2, max_digits=14, null=True)),
                ("employee_count", models.PositiveIntegerField(default=0)),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("processed_at", models.DateTimeField(blank=True, null=True)),
                ("created_by", models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name="payroll_runs_created", to=settings.AUTH_USER_MODEL)),
            ],
            options={
                "ordering": ["-period_start"],
            },
        ),
        migrations.CreateModel(
            name="PayrollEntry",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("basic_salary", models.DecimalField(decimal_places=2, default=0, max_digits=12)),
                ("allowances", models.DecimalField(decimal_places=2, default=0, max_digits=12)),
                ("gross_salary", models.DecimalField(decimal_places=2, default=0, max_digits=12)),
                ("income_tax", models.DecimalField(decimal_places=2, default=0, max_digits=12)),
                ("eobi_or_sss", models.DecimalField(decimal_places=2, default=0, max_digits=12)),
                ("other_deductions", models.DecimalField(decimal_places=2, default=0, max_digits=12)),
                ("net_salary", models.DecimalField(decimal_places=2, default=0, max_digits=12)),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("run", models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name="entries", to="users.payrollrun")),
                ("staff", models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name="payroll_entries", to="users.staff")),
            ],
            options={
                "ordering": ["staff__full_name"],
                "unique_together": {("run", "staff")},
            },
        ),
    ]
