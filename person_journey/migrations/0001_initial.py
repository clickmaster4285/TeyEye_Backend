# Generated manually for person_journey initial schema

import uuid

import django.db.models.deletion
from django.db import migrations, models


class Migration(migrations.Migration):

    initial = True

    dependencies = [
        ("cameras", "0009_detectionevent_personal_number"),
        ("users", "0020_attendance_video"),
        ("visitors", "0006_alter_visitor_access_zone"),
    ]

    operations = [
        migrations.CreateModel(
            name="JourneyPerson",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("uuid", models.UUIDField(db_index=True, default=uuid.uuid4, editable=False, unique=True)),
                ("code", models.CharField(db_index=True, max_length=32, unique=True)),
                (
                    "person_type",
                    models.CharField(
                        choices=[("staff", "Staff"), ("visitor", "Visitor"), ("unknown", "Unknown")],
                        db_index=True,
                        default="unknown",
                        max_length=16,
                    ),
                ),
                ("display_name", models.CharField(blank=True, default="", max_length=200)),
                ("face_embedding", models.JSONField(blank=True, default=list)),
                ("reid_embedding", models.JSONField(blank=True, default=list)),
                ("latest_zone", models.CharField(blank=True, default="", max_length=64)),
                ("latest_seen_at", models.DateTimeField(blank=True, db_index=True, null=True)),
                (
                    "status",
                    models.CharField(
                        choices=[("active", "Active"), ("finished", "Finished"), ("merged", "Merged")],
                        db_index=True,
                        default="active",
                        max_length=16,
                    ),
                ),
                ("metadata", models.JSONField(blank=True, default=dict)),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("updated_at", models.DateTimeField(auto_now=True)),
                (
                    "latest_camera",
                    models.ForeignKey(
                        blank=True,
                        null=True,
                        on_delete=django.db.models.deletion.SET_NULL,
                        related_name="journey_persons_latest",
                        to="cameras.camera",
                    ),
                ),
                (
                    "merged_into",
                    models.ForeignKey(
                        blank=True,
                        null=True,
                        on_delete=django.db.models.deletion.SET_NULL,
                        related_name="merged_from",
                        to="person_journey.journeyperson",
                    ),
                ),
                (
                    "staff",
                    models.ForeignKey(
                        blank=True,
                        null=True,
                        on_delete=django.db.models.deletion.SET_NULL,
                        related_name="journey_persons",
                        to="users.staff",
                    ),
                ),
                (
                    "visitor",
                    models.ForeignKey(
                        blank=True,
                        null=True,
                        on_delete=django.db.models.deletion.SET_NULL,
                        related_name="journey_persons",
                        to="visitors.visitor",
                    ),
                ),
            ],
            options={
                "ordering": ["-latest_seen_at", "-created_at"],
            },
        ),
        migrations.CreateModel(
            name="CameraTrack",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("track_id", models.PositiveIntegerField()),
                (
                    "status",
                    models.CharField(
                        choices=[("active", "Active"), ("finished", "Finished")],
                        db_index=True,
                        default="active",
                        max_length=16,
                    ),
                ),
                ("started_at", models.DateTimeField(db_index=True)),
                ("ended_at", models.DateTimeField(blank=True, null=True)),
                ("last_bbox", models.JSONField(blank=True, default=list)),
                ("metadata", models.JSONField(blank=True, default=dict)),
                (
                    "camera",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="journey_tracks",
                        to="cameras.camera",
                    ),
                ),
                (
                    "journey_person",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="tracks",
                        to="person_journey.journeyperson",
                    ),
                ),
            ],
            options={
                "ordering": ["-started_at"],
            },
        ),
        migrations.CreateModel(
            name="JourneyEvent",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                (
                    "event_type",
                    models.CharField(
                        choices=[
                            ("camera_detection", "Camera Detection"),
                            ("staff_recognized", "Staff Recognized"),
                            ("attendance_check_in", "Attendance Check-In"),
                            ("attendance_check_out", "Attendance Check-Out"),
                            ("zone_entry", "Zone Entry"),
                            ("zone_exit", "Zone Exit"),
                            ("weapon_detected", "Weapon Detected"),
                            ("watchlist", "Watchlist"),
                            ("panic", "Panic"),
                            ("unknown_created", "Unknown Person Created"),
                            ("person_merged", "Person Merged"),
                            ("face_matched", "Face Matched"),
                            ("alert", "Alert"),
                        ],
                        db_index=True,
                        max_length=32,
                    ),
                ),
                ("title", models.CharField(blank=True, default="", max_length=255)),
                ("description", models.TextField(blank=True, default="")),
                ("zone", models.CharField(blank=True, default="", max_length=64)),
                ("gate", models.CharField(blank=True, default="", max_length=64)),
                ("detection_event_id", models.PositiveIntegerField(blank=True, db_index=True, null=True)),
                ("zone_access_log_id", models.PositiveIntegerField(blank=True, db_index=True, null=True)),
                ("attendance_id", models.PositiveIntegerField(blank=True, db_index=True, null=True)),
                ("confidence", models.FloatField(blank=True, null=True)),
                ("match_score", models.FloatField(blank=True, null=True)),
                ("bbox", models.JSONField(blank=True, default=list)),
                ("snapshot_path", models.CharField(blank=True, default="", max_length=512)),
                ("metadata", models.JSONField(blank=True, default=dict)),
                ("created_at", models.DateTimeField(auto_now_add=True, db_index=True)),
                (
                    "camera",
                    models.ForeignKey(
                        blank=True,
                        null=True,
                        on_delete=django.db.models.deletion.SET_NULL,
                        related_name="journey_events",
                        to="cameras.camera",
                    ),
                ),
                (
                    "journey_person",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="events",
                        to="person_journey.journeyperson",
                    ),
                ),
                (
                    "track",
                    models.ForeignKey(
                        blank=True,
                        null=True,
                        on_delete=django.db.models.deletion.SET_NULL,
                        related_name="events",
                        to="person_journey.cameratrack",
                    ),
                ),
            ],
            options={
                "ordering": ["-created_at"],
            },
        ),
        migrations.AddIndex(
            model_name="journeyperson",
            index=models.Index(fields=["person_type", "status", "-latest_seen_at"], name="person_jour_person__a8f2c0_idx"),
        ),
        migrations.AddIndex(
            model_name="cameratrack",
            index=models.Index(fields=["camera", "track_id", "status"], name="person_jour_camera__4b2f11_idx"),
        ),
        migrations.AddConstraint(
            model_name="cameratrack",
            constraint=models.UniqueConstraint(
                fields=("camera", "track_id", "started_at"),
                name="person_journey_unique_camera_track_start",
            ),
        ),
        migrations.AddIndex(
            model_name="journeyevent",
            index=models.Index(fields=["journey_person", "-created_at"], name="person_jour_journey_91c4e2_idx"),
        ),
        migrations.AddIndex(
            model_name="journeyevent",
            index=models.Index(fields=["event_type", "-created_at"], name="person_jour_event_t_6d31a8_idx"),
        ),
    ]
