from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("cameras", "0010_detectionevent_journey_columns"),
    ]

    operations = [
        migrations.AlterField(
            model_name="detectionevent",
            name="clip",
            field=models.FileField(
                blank=True,
                help_text="JPEG snapshot captured when this detection was saved.",
                upload_to="detection_clips/%Y/%m/%d/",
            ),
        ),
        migrations.AlterField(
            model_name="nvr",
            name="stream_path_template",
            field=models.CharField(
                blank=True,
                default="",
                help_text="Optional path template with {channel}, e.g. /Streaming/Channels/{channel}",
                max_length=255,
            ),
        ),
    ]
