# Add Guard role choice

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("users", "0008_add_user_location"),
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
                    ("GUARD", "Guard"),
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
