from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("cameras", "0006_drop_legacy_camera_columns"),
    ]

    operations = [
        migrations.AddField(
            model_name="detectionevent",
            name="clip",
            field=models.FileField(
                blank=True,
                help_text="Short MP4 captured when this detection was saved (5–10 s).",
                upload_to="detection_clips/%Y/%m/%d/",
            ),
        ),
        migrations.AddField(
            model_name="detectionevent",
            name="clip_status",
            field=models.CharField(
                choices=[
                    ("pending", "Pending"),
                    ("recording", "Recording"),
                    ("ready", "Ready"),
                    ("failed", "Failed"),
                    ("skipped", "Skipped"),
                ],
                default="pending",
                max_length=16,
            ),
        ),
    ]
