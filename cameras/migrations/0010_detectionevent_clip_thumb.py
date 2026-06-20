from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ("cameras", "0009_detectionevent_personal_number"),
    ]

    operations = [
        migrations.AddField(
            model_name="detectionevent",
            name="clip_thumb",
            field=models.FileField(
                blank=True,
                help_text="Small JPEG thumbnail for the detection log table.",
                upload_to="detection_clips/%Y/%m/%d/",
            ),
        ),
    ]
