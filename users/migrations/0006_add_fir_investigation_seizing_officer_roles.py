# Add FIR Officer, Investigation Officer, Seizing Officer role choices

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("users", "0005_add_operation_manager_role"),
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
                    ("HR", "Human Resource"),
                    ("WAREHOUSE_OFFICER", "Warehouse Officer"),
                    ("DETECTION_OFFICER", "Detection Officer"),
                    ("FIR_OFFICER", "FIR Officer"),
                    ("INVESTIGATION_OFFICER", "Investigation Officer"),
                    ("SEIZING_OFFICER", "Seizing Officer"),
                ],
                max_length=30,
            ),
        ),
    ]
