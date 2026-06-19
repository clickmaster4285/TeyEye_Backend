# Generated migration for LOCATION_ADMIN role choice

from django.db import migrations, models


def clear_admin_locations(apps, schema_editor):
    User = apps.get_model("users", "User")
    User.objects.filter(role="ADMIN").update(location="")


class Migration(migrations.Migration):

    dependencies = [
        ("users", "0010_user_profile_fields"),
    ]

    operations = [
        migrations.AlterField(
            model_name="user",
            name="role",
            field=models.CharField(
                choices=[
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
                ],
                max_length=30,
            ),
        ),
        migrations.RunPython(clear_admin_locations, migrations.RunPython.noop),
    ]
