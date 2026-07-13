# Recovery memo approval workflow parity with note sheet:
# approval_remarks, submitted_at, viewed_at, updated_by + RecoveryNotification.

from django.db import migrations, models
import django.db.models.deletion
import uuid


class Migration(migrations.Migration):

    dependencies = [
        ("seizure_management", "0012_recovery_memo_legacy_defaults"),
    ]

    operations = [
        migrations.RunSQL(
            sql="""
            ALTER TABLE seizure_management_recoverymemo
              ADD COLUMN IF NOT EXISTS approval_remarks text NOT NULL DEFAULT '';

            ALTER TABLE seizure_management_recoverymemo
              ADD COLUMN IF NOT EXISTS submitted_at timestamptz NULL;

            ALTER TABLE seizure_management_recoverymemo
              ADD COLUMN IF NOT EXISTS viewed_at timestamptz NULL;

            ALTER TABLE seizure_management_recoverymemo
              ADD COLUMN IF NOT EXISTS updated_by varchar(150) NOT NULL DEFAULT '';

            ALTER TABLE seizure_management_recoverymemo
              ADD COLUMN IF NOT EXISTS created_by varchar(150) NOT NULL DEFAULT '';
            """,
            reverse_sql=migrations.RunSQL.noop,
        ),
        migrations.CreateModel(
            name="RecoveryNotification",
            fields=[
                ("id", models.UUIDField(default=uuid.uuid4, editable=False, primary_key=True, serialize=False)),
                ("recipient_user_id", models.IntegerField(db_index=True)),
                ("title", models.CharField(max_length=255)),
                ("message", models.TextField(blank=True)),
                ("is_read", models.BooleanField(db_index=True, default=False)),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                (
                    "recovery_memo",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="notifications",
                        to="seizure_management.recoverymemo",
                    ),
                ),
            ],
            options={
                "ordering": ["-created_at"],
                "indexes": [
                    models.Index(
                        fields=["recipient_user_id", "is_read", "-created_at"],
                        name="seizure_man_recipie_recov_idx",
                    )
                ],
            },
        ),
    ]
