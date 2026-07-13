"""Sync DetectionEvent model with journey columns already present in PostgreSQL."""

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("cameras", "0009_detectionevent_personal_number"),
    ]

    operations = [
        migrations.SeparateDatabaseAndState(
            state_operations=[
                migrations.AddField(
                    model_name="detectionevent",
                    name="local_track_id",
                    field=models.PositiveIntegerField(
                        blank=True,
                        help_text="ByteTrack ID on this camera frame.",
                        null=True,
                    ),
                ),
                migrations.AddField(
                    model_name="detectionevent",
                    name="person_qr",
                    field=models.CharField(
                        blank=True,
                        default="",
                        help_text="Linked journey person code (P100, U300, V55) when identified.",
                        max_length=32,
                    ),
                ),
                migrations.AddField(
                    model_name="detectionevent",
                    name="track_event",
                    field=models.CharField(
                        blank=True,
                        default="detection",
                        help_text="Track lifecycle: detection, enter, exit, etc.",
                        max_length=16,
                    ),
                ),
                migrations.AddField(
                    model_name="detectionevent",
                    name="person_identity_id",
                    field=models.BigIntegerField(
                        blank=True,
                        help_text="Optional FK to person_journey.JourneyPerson pk when linked.",
                        null=True,
                    ),
                ),
            ],
            database_operations=[
                migrations.RunSQL(
                    sql=[
                        (
                            "ALTER TABLE cameras_detectionevent "
                            "ALTER COLUMN person_qr SET DEFAULT '';"
                        ),
                        (
                            "ALTER TABLE cameras_detectionevent "
                            "ALTER COLUMN track_event SET DEFAULT 'detection';"
                        ),
                    ],
                    reverse_sql=migrations.RunSQL.noop,
                ),
            ],
        ),
    ]
