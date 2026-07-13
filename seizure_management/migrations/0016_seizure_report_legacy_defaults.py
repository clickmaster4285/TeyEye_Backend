# Soften legacy SeizureReport columns so Django model inserts succeed.
# Live table still has reference_number / executive_summary / assessment_summary /
# recovery_summary / created_by (NOT NULL, no default) which the model does not write.

from django.db import migrations


class Migration(migrations.Migration):

    dependencies = [
        ("seizure_management", "0015_rename_recovery_notification_index"),
    ]

    operations = [
        migrations.RunSQL(
            sql="""
            DO $$
            BEGIN
              IF EXISTS (
                SELECT 1 FROM information_schema.columns
                WHERE table_name = 'seizure_management_seizurereport'
                  AND column_name = 'reference_number'
              ) THEN
                ALTER TABLE seizure_management_seizurereport
                  ALTER COLUMN reference_number SET DEFAULT '';
                UPDATE seizure_management_seizurereport
                SET reference_number = COALESCE(reference_number, '');
              END IF;

              IF EXISTS (
                SELECT 1 FROM information_schema.columns
                WHERE table_name = 'seizure_management_seizurereport'
                  AND column_name = 'executive_summary'
              ) THEN
                ALTER TABLE seizure_management_seizurereport
                  ALTER COLUMN executive_summary SET DEFAULT '';
                UPDATE seizure_management_seizurereport
                SET executive_summary = COALESCE(executive_summary, '');
              END IF;

              IF EXISTS (
                SELECT 1 FROM information_schema.columns
                WHERE table_name = 'seizure_management_seizurereport'
                  AND column_name = 'assessment_summary'
              ) THEN
                ALTER TABLE seizure_management_seizurereport
                  ALTER COLUMN assessment_summary SET DEFAULT '';
                UPDATE seizure_management_seizurereport
                SET assessment_summary = COALESCE(assessment_summary, '');
              END IF;

              IF EXISTS (
                SELECT 1 FROM information_schema.columns
                WHERE table_name = 'seizure_management_seizurereport'
                  AND column_name = 'recovery_summary'
              ) THEN
                ALTER TABLE seizure_management_seizurereport
                  ALTER COLUMN recovery_summary SET DEFAULT '';
                UPDATE seizure_management_seizurereport
                SET recovery_summary = COALESCE(recovery_summary, '');
              END IF;

              IF EXISTS (
                SELECT 1 FROM information_schema.columns
                WHERE table_name = 'seizure_management_seizurereport'
                  AND column_name = 'created_by'
              ) THEN
                ALTER TABLE seizure_management_seizurereport
                  ALTER COLUMN created_by SET DEFAULT '';
                UPDATE seizure_management_seizurereport
                SET created_by = COALESCE(created_by, '');
              END IF;

              IF EXISTS (
                SELECT 1 FROM information_schema.columns
                WHERE table_name = 'seizure_management_seizurereport'
                  AND column_name = 'prepared_by'
              ) THEN
                ALTER TABLE seizure_management_seizurereport
                  ALTER COLUMN prepared_by SET DEFAULT '';
              END IF;

              IF EXISTS (
                SELECT 1 FROM information_schema.columns
                WHERE table_name = 'seizure_management_seizurereport'
                  AND column_name = 'status'
              ) THEN
                ALTER TABLE seizure_management_seizurereport
                  ALTER COLUMN status SET DEFAULT 'Draft';
              END IF;
            END $$;
            """,
            reverse_sql=migrations.RunSQL.noop,
        ),
    ]
