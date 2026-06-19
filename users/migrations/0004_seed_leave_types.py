from django.db import migrations


def seed_leave_types(apps, schema_editor):
    LeaveType = apps.get_model("users", "LeaveType")
    if LeaveType.objects.exists():
        return
    LeaveType.objects.bulk_create([
        LeaveType(name="Annual", code="ANNUAL", max_days_per_year=20, requires_approval=True, is_paid=True),
        LeaveType(name="Sick", code="SICK", max_days_per_year=12, requires_approval=True, is_paid=True),
        LeaveType(name="Casual", code="CASUAL", max_days_per_year=10, requires_approval=True, is_paid=True),
        LeaveType(name="Maternity", code="MATERNITY", max_days_per_year=90, requires_approval=True, is_paid=True),
        LeaveType(name="Leave without pay", code="LWOP", max_days_per_year=None, requires_approval=True, is_paid=False),
    ])


def noop(apps, schema_editor):
    pass


class Migration(migrations.Migration):

    dependencies = [
        ("users", "0003_leave_payroll_models"),
    ]

    operations = [
        migrations.RunPython(seed_leave_types, noop),
    ]
