# Generated manually for full Staff template fields

from django.conf import settings
from django.db import migrations, models
from django.db.models.deletion import CASCADE


class Migration(migrations.Migration):

    dependencies = [
        ("users", "0001_initial"),
    ]

    operations = [
        migrations.AlterField(
            model_name="staff",
            name="user",
            field=models.OneToOneField(
                blank=True,
                null=True,
                on_delete=CASCADE,
                related_name="staff_profile",
                to=settings.AUTH_USER_MODEL,
            ),
        ),
        migrations.AlterField(
            model_name="staff",
            name="address",
            field=models.TextField(blank=True, null=True),
        ),
        migrations.AlterField(
            model_name="staff",
            name="emergency_contact",
            field=models.CharField(blank=True, max_length=100, null=True),
        ),
        migrations.AddField(model_name="staff", name="first_name", field=models.CharField(blank=True, max_length=80, null=True)),
        migrations.AddField(model_name="staff", name="last_name", field=models.CharField(blank=True, max_length=80, null=True)),
        migrations.AddField(model_name="staff", name="gender", field=models.CharField(blank=True, max_length=20, null=True)),
        migrations.AddField(model_name="staff", name="national_id", field=models.CharField(blank=True, max_length=30, null=True)),
        migrations.AddField(model_name="staff", name="marital_status", field=models.CharField(blank=True, max_length=30, null=True)),
        migrations.AddField(model_name="staff", name="blood_group", field=models.CharField(blank=True, max_length=10, null=True)),
        migrations.AddField(model_name="staff", name="email", field=models.EmailField(blank=True, max_length=254, null=True)),
        migrations.AddField(model_name="staff", name="phone_primary", field=models.CharField(blank=True, max_length=20, null=True)),
        migrations.AddField(model_name="staff", name="phone_alternate", field=models.CharField(blank=True, max_length=20, null=True)),
        migrations.AddField(model_name="staff", name="street_address", field=models.CharField(blank=True, max_length=255, null=True)),
        migrations.AddField(model_name="staff", name="city", field=models.CharField(blank=True, max_length=100, null=True)),
        migrations.AddField(model_name="staff", name="state", field=models.CharField(blank=True, max_length=100, null=True)),
        migrations.AddField(model_name="staff", name="country", field=models.CharField(blank=True, max_length=100, null=True)),
        migrations.AddField(model_name="staff", name="postal_code", field=models.CharField(blank=True, max_length=20, null=True)),
        migrations.AddField(model_name="staff", name="employee_id", field=models.CharField(blank=True, max_length=50, null=True, unique=True)),
        migrations.AddField(model_name="staff", name="branch_location", field=models.CharField(blank=True, max_length=200, null=True)),
        migrations.AddField(model_name="staff", name="manager", field=models.CharField(blank=True, max_length=150, null=True)),
        migrations.AddField(model_name="staff", name="employment_type", field=models.CharField(blank=True, max_length=50, null=True)),
        migrations.AddField(model_name="staff", name="probation_end_date", field=models.DateField(blank=True, null=True)),
        migrations.AddField(model_name="staff", name="work_shift_start", field=models.TimeField(blank=True, null=True)),
        migrations.AddField(model_name="staff", name="work_shift_end", field=models.TimeField(blank=True, null=True)),
        migrations.AddField(model_name="staff", name="job_status", field=models.CharField(blank=True, max_length=50, null=True)),
        migrations.AddField(model_name="staff", name="salary", field=models.DecimalField(blank=True, decimal_places=2, max_digits=12, null=True)),
        migrations.AddField(model_name="staff", name="bank_account", field=models.CharField(blank=True, max_length=100, null=True)),
        migrations.AddField(model_name="staff", name="iban", field=models.CharField(blank=True, max_length=50, null=True)),
        migrations.AddField(model_name="staff", name="salary_type", field=models.CharField(blank=True, max_length=30, null=True)),
        migrations.AddField(model_name="staff", name="tax_id", field=models.CharField(blank=True, max_length=50, null=True)),
        migrations.AddField(model_name="staff", name="allowances", field=models.TextField(blank=True, null=True)),
        migrations.AddField(model_name="staff", name="role_access_level", field=models.CharField(blank=True, max_length=50, null=True)),
        migrations.AddField(model_name="staff", name="system_permissions", field=models.TextField(blank=True, null=True)),
        migrations.AddField(model_name="staff", name="emergency_contact_name", field=models.CharField(blank=True, max_length=100, null=True)),
        migrations.AddField(model_name="staff", name="emergency_contact_relationship", field=models.CharField(blank=True, max_length=50, null=True)),
        migrations.AddField(model_name="staff", name="emergency_contact_phone", field=models.CharField(blank=True, max_length=20, null=True)),
        migrations.AddField(model_name="staff", name="emergency_contact_address", field=models.TextField(blank=True, null=True)),
        migrations.AddField(model_name="staff", name="resume_file", field=models.FileField(blank=True, null=True, upload_to="staff_docs/")),
        migrations.AddField(model_name="staff", name="joining_letter_file", field=models.FileField(blank=True, null=True, upload_to="staff_docs/")),
        migrations.AddField(model_name="staff", name="contract_file", field=models.FileField(blank=True, null=True, upload_to="staff_docs/")),
        migrations.AddField(model_name="staff", name="id_proof_file", field=models.FileField(blank=True, null=True, upload_to="staff_docs/")),
        migrations.AddField(model_name="staff", name="tax_form_file", field=models.FileField(blank=True, null=True, upload_to="staff_docs/")),
        migrations.AddField(model_name="staff", name="certificates_file", field=models.FileField(blank=True, null=True, upload_to="staff_docs/")),
        migrations.AddField(model_name="staff", name="background_check_status", field=models.CharField(blank=True, max_length=50, null=True)),
        migrations.AddField(model_name="staff", name="skills_competencies", field=models.TextField(blank=True, null=True)),
        migrations.AddField(model_name="staff", name="languages_known", field=models.TextField(blank=True, null=True)),
        migrations.AddField(model_name="staff", name="performance_rating", field=models.CharField(blank=True, max_length=20, null=True)),
        migrations.AddField(model_name="staff", name="last_appraisal_date", field=models.DateField(blank=True, null=True)),
        migrations.AddField(model_name="staff", name="leave_balance", field=models.PositiveIntegerField(blank=True, null=True)),
        migrations.AddField(model_name="staff", name="notes", field=models.TextField(blank=True, null=True)),
    ]
