# Align SeizureReport table with current model.
# Live DB still has legacy columns (executive_summary, assessment_summary,
# recovery_summary, reference_number, created_by) while the model expects
# summary and recovery_assessment_notes. report_date was a date; model uses varchar.

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("seizure_management", "0013_recovery_approval_workflow"),
    ]

    operations = [
        migrations.RunSQL(
            sql="""
            ALTER TABLE seizure_management_seizurereport
              ADD COLUMN IF NOT EXISTS summary text NOT NULL DEFAULT '';

            ALTER TABLE seizure_management_seizurereport
              ADD COLUMN IF NOT EXISTS recovery_assessment_notes text NOT NULL DEFAULT '';

            DO $$
            BEGIN
              IF EXISTS (
                SELECT 1 FROM information_schema.columns
                WHERE table_name = 'seizure_management_seizurereport'
                  AND column_name = 'executive_summary'
              ) THEN
                UPDATE seizure_management_seizurereport
                SET summary = COALESCE(NULLIF(summary, ''), executive_summary, '')
                WHERE summary = '' OR summary IS NULL;
              END IF;

              IF EXISTS (
                SELECT 1 FROM information_schema.columns
                WHERE table_name = 'seizure_management_seizurereport'
                  AND column_name = 'assessment_summary'
              ) THEN
                UPDATE seizure_management_seizurereport
                SET recovery_assessment_notes = COALESCE(
                  NULLIF(recovery_assessment_notes, ''), assessment_summary, ''
                )
                WHERE recovery_assessment_notes = '' OR recovery_assessment_notes IS NULL;
              END IF;

              IF EXISTS (
                SELECT 1 FROM information_schema.columns
                WHERE table_name = 'seizure_management_seizurereport'
                  AND column_name = 'recovery_summary'
              ) THEN
                UPDATE seizure_management_seizurereport
                SET recovery_assessment_notes = CASE
                  WHEN recovery_assessment_notes IS NULL OR recovery_assessment_notes = ''
                    THEN COALESCE(recovery_summary, '')
                  WHEN recovery_summary IS NOT NULL AND recovery_summary <> ''
                    THEN recovery_assessment_notes || E'\\n' || recovery_summary
                  ELSE recovery_assessment_notes
                END;
              END IF;
            END $$;

            -- Model stores report_date as varchar(40); legacy column was date.
            DO $$
            BEGIN
              IF EXISTS (
                SELECT 1 FROM information_schema.columns
                WHERE table_name = 'seizure_management_seizurereport'
                  AND column_name = 'report_date'
                  AND data_type = 'date'
              ) THEN
                ALTER TABLE seizure_management_seizurereport
                  ALTER COLUMN report_date TYPE varchar(40)
                  USING COALESCE(report_date::text, '');
                ALTER TABLE seizure_management_seizurereport
                  ALTER COLUMN report_date SET DEFAULT '';
                UPDATE seizure_management_seizurereport
                SET report_date = ''
                WHERE report_date IS NULL;
                ALTER TABLE seizure_management_seizurereport
                  ALTER COLUMN report_date SET NOT NULL;
              END IF;
            END $$;
            """,
            reverse_sql=migrations.RunSQL.noop,
        ),
        # 0013 added these via RunSQL only — sync Django state without re-altering DB.
        migrations.SeparateDatabaseAndState(
            state_operations=[
                migrations.AddField(
                    model_name="recoverymemo",
                    name="approval_remarks",
                    field=models.TextField(blank=True),
                ),
                migrations.AddField(
                    model_name="recoverymemo",
                    name="created_by",
                    field=models.CharField(blank=True, max_length=150),
                ),
                migrations.AddField(
                    model_name="recoverymemo",
                    name="submitted_at",
                    field=models.DateTimeField(blank=True, null=True),
                ),
                migrations.AddField(
                    model_name="recoverymemo",
                    name="updated_by",
                    field=models.CharField(blank=True, max_length=150),
                ),
                migrations.AddField(
                    model_name="recoverymemo",
                    name="viewed_at",
                    field=models.DateTimeField(blank=True, null=True),
                ),
            ],
            database_operations=[],
        ),
    ]
