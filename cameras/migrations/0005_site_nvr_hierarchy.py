# Sync Django model state with existing Site/NVR/Camera hierarchy tables.

import django.db.models.deletion
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("cameras", "0004_alter_camera_frame_rate"),
    ]

    state_operations = [
        migrations.CreateModel(
            name="Site",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("code", models.CharField(help_text="Short code e.g. PESHAWAR", max_length=64, unique=True)),
                ("name", models.CharField(max_length=150)),
                ("description", models.TextField(blank=True, default="")),
                ("is_active", models.BooleanField(default=True)),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("updated_at", models.DateTimeField(auto_now=True)),
            ],
            options={
                "db_table": "cameras_site",
                "ordering": ["name"],
            },
        ),
        migrations.CreateModel(
            name="Nvr",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("name", models.CharField(max_length=150)),
                ("ip_address", models.CharField(max_length=45)),
                ("port", models.PositiveIntegerField(default=554)),
                ("username", models.CharField(default="admin", max_length=64)),
                ("password", models.CharField(blank=True, default="", max_length=128)),
                (
                    "brand",
                    models.CharField(
                        choices=[
                            ("hikvision", "Hikvision"),
                            ("dahua", "Dahua"),
                            ("uniview", "Uniview"),
                            ("generic", "Generic RTSP"),
                        ],
                        default="hikvision",
                        max_length=32,
                    ),
                ),
                (
                    "stream_path_template",
                    models.CharField(
                        blank=True,
                        default="",
                        help_text="Optional path template with {channel}",
                        max_length=255,
                    ),
                ),
                ("is_active", models.BooleanField(default=True)),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("updated_at", models.DateTimeField(auto_now=True)),
                (
                    "site",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="nvrs",
                        to="cameras.site",
                    ),
                ),
            ],
            options={
                "db_table": "cameras_nvrdevice",
                "verbose_name": "NVR",
                "verbose_name_plural": "NVRs",
                "ordering": ["site__name", "name"],
            },
        ),
        migrations.RemoveField(model_name="camera", name="ip_address"),
        migrations.RemoveField(model_name="camera", name="stream_url"),
        migrations.RemoveField(model_name="camera", name="site_label"),
        migrations.AddField(
            model_name="camera",
            name="nvr",
            field=models.ForeignKey(
                on_delete=django.db.models.deletion.CASCADE,
                related_name="cameras",
                to="cameras.nvr",
            ),
            preserve_default=False,
        ),
        migrations.AddField(
            model_name="camera",
            name="channel",
            field=models.PositiveSmallIntegerField(
                db_column="rtsp_channel",
                help_text="NVR channel number (1–32+, or Hikvision stream ID e.g. 101)",
            ),
            preserve_default=False,
        ),
        migrations.AlterField(
            model_name="camera",
            name="location",
            field=models.CharField(help_text="Denormalized site code", max_length=64),
        ),
        migrations.AlterField(
            model_name="camera",
            name="name",
            field=models.CharField(help_text="User-defined label e.g. Main Gate", max_length=150),
        ),
        migrations.AlterUniqueTogether(
            name="camera",
            unique_together={("nvr", "channel")},
        ),
        migrations.AlterModelOptions(
            name="camera",
            options={"ordering": ["nvr__site__name", "nvr__name", "channel"]},
        ),
        migrations.DeleteModel(name="CameraRtspSettings"),
    ]

    database_operations = [
        migrations.RunSQL(
            sql="ALTER TABLE cameras_site ADD COLUMN IF NOT EXISTS description TEXT NOT NULL DEFAULT '';",
            reverse_sql=migrations.RunSQL.noop,
        ),
        migrations.RunSQL(
            sql="DROP TABLE IF EXISTS cameras_camerartspsettings CASCADE;",
            reverse_sql=migrations.RunSQL.noop,
        ),
    ]

    operations = [
        migrations.SeparateDatabaseAndState(
            database_operations=database_operations,
            state_operations=state_operations,
        ),
    ]
