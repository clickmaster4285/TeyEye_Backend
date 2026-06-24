from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("users", "0019_attendance_staff_optional_user"),
    ]

    operations = [
        migrations.AddField(
            model_name="attendance",
            name="video",
            field=models.FileField(
                blank=True,
                help_text="Short camera clip captured when attendance was marked.",
                null=True,
                upload_to="attendance/videos/",
            ),
        ),
    ]
