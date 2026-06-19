from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("users", "0007_staff_disposition_fields"),
    ]

    operations = [
        migrations.AddField(
            model_name="user",
            name="location",
            field=models.CharField(
                blank=True,
                choices=[
                    ("PESHAWAR", "Peshawar (Head Office)"),
                    ("KOHAT", "Kohat"),
                    ("NOWSHERA", "Nowshera"),
                    ("MARDAN", "Mardan"),
                    ("DI_KHAN", "DI Khan"),
                ],
                default="",
                max_length=20,
            ),
        ),
    ]
