# Generated manually - add OPERATION_MANAGER role choice

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("users", "0004_seed_leave_types"),
    ]

    operations = [
        migrations.AlterField(
            model_name="user",
            name="role",
            field=models.CharField(
                choices=[
                    ("ADMIN", "Admin"),
                    ("OPERATION_MANAGER", "Operation Manager"),
                    ("INSPECTOR", "Inspector"),
                    ("COLLECTOR", "Collector"),
                    ("DEPUTY_COLLECTOR", "Deputy Collector"),
                    ("ASSISTANT_COLLECTOR", "Assistant Collector"),
                    ("RECEPTIONIST", "Receptionist"),
                    ("HR", "Human Resource Manager"),
                    ("WAREHOUSE_OFFICER", "Warehouse Officer"),
                    ("DETECTION_OFFICER", "Detection Officer"),
                ],
                max_length=30,
            ),
        ),
    ]
