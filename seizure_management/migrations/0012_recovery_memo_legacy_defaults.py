# Soften legacy RecoveryMemo columns so Django model inserts succeed.
# Live table still has reference_number / summary / items_description / created_by
# (NOT NULL, no default) and recovery_date as date — model uses CharField.

from django.db import migrations


class Migration(migrations.Migration):

    dependencies = [
        ("seizure_management", "0011_align_recovery_memo_schema"),
    ]

    operations = [
        migrations.RunSQL(
            sql="""
            DO $$
            BEGIN
              IF EXISTS (
                SELECT 1 FROM information_schema.columns
                WHERE table_name = 'seizure_management_recoverymemo'
                  AND column_name = 'reference_number'
              ) THEN
                ALTER TABLE seizure_management_recoverymemo
                  ALTER COLUMN reference_number SET DEFAULT '';
              END IF;

              IF EXISTS (
                SELECT 1 FROM information_schema.columns
                WHERE table_name = 'seizure_management_recoverymemo'
                  AND column_name = 'summary'
              ) THEN
                ALTER TABLE seizure_management_recoverymemo
                  ALTER COLUMN summary SET DEFAULT '';
              END IF;

              IF EXISTS (
                SELECT 1 FROM information_schema.columns
                WHERE table_name = 'seizure_management_recoverymemo'
                  AND column_name = 'items_description'
              ) THEN
                ALTER TABLE seizure_management_recoverymemo
                  ALTER COLUMN items_description SET DEFAULT '';
              END IF;

              IF EXISTS (
                SELECT 1 FROM information_schema.columns
                WHERE table_name = 'seizure_management_recoverymemo'
                  AND column_name = 'created_by'
              ) THEN
                ALTER TABLE seizure_management_recoverymemo
                  ALTER COLUMN created_by SET DEFAULT '';
              END IF;

              IF EXISTS (
                SELECT 1 FROM information_schema.columns
                WHERE table_name = 'seizure_management_recoverymemo'
                  AND column_name = 'approved_by'
              ) THEN
                ALTER TABLE seizure_management_recoverymemo
                  ALTER COLUMN approved_by SET DEFAULT '';
              END IF;

              IF EXISTS (
                SELECT 1 FROM information_schema.columns
                WHERE table_name = 'seizure_management_recoverymemo'
                  AND column_name = 'rejection_reason'
              ) THEN
                ALTER TABLE seizure_management_recoverymemo
                  ALTER COLUMN rejection_reason SET DEFAULT '';
              END IF;
            END $$;

            DO $$
            BEGIN
              IF EXISTS (
                SELECT 1 FROM information_schema.columns
                WHERE table_name = 'seizure_management_recoverymemo'
                  AND column_name = 'reference_number'
              ) THEN
                UPDATE seizure_management_recoverymemo
                SET reference_number = COALESCE(reference_number, '');
              END IF;

              IF EXISTS (
                SELECT 1 FROM information_schema.columns
                WHERE table_name = 'seizure_management_recoverymemo'
                  AND column_name = 'summary'
              ) THEN
                UPDATE seizure_management_recoverymemo
                SET summary = COALESCE(summary, '');
              END IF;

              IF EXISTS (
                SELECT 1 FROM information_schema.columns
                WHERE table_name = 'seizure_management_recoverymemo'
                  AND column_name = 'items_description'
              ) THEN
                UPDATE seizure_management_recoverymemo
                SET items_description = COALESCE(items_description, '');
              END IF;

              IF EXISTS (
                SELECT 1 FROM information_schema.columns
                WHERE table_name = 'seizure_management_recoverymemo'
                  AND column_name = 'created_by'
              ) THEN
                UPDATE seizure_management_recoverymemo
                SET created_by = COALESCE(created_by, '');
              END IF;

              IF EXISTS (
                SELECT 1 FROM information_schema.columns
                WHERE table_name = 'seizure_management_recoverymemo'
                  AND column_name = 'approved_by'
              ) THEN
                UPDATE seizure_management_recoverymemo
                SET approved_by = COALESCE(approved_by, '');
              END IF;

              IF EXISTS (
                SELECT 1 FROM information_schema.columns
                WHERE table_name = 'seizure_management_recoverymemo'
                  AND column_name = 'rejection_reason'
              ) THEN
                UPDATE seizure_management_recoverymemo
                SET rejection_reason = COALESCE(rejection_reason, '');
              END IF;
            END $$;

            DO $$
            BEGIN
              IF EXISTS (
                SELECT 1 FROM information_schema.columns
                WHERE table_name = 'seizure_management_recoverymemo'
                  AND column_name = 'recovery_date'
              ) THEN
                ALTER TABLE seizure_management_recoverymemo
                  ALTER COLUMN recovery_date TYPE varchar(40)
                  USING COALESCE(recovery_date::text, '');

                ALTER TABLE seizure_management_recoverymemo
                  ALTER COLUMN recovery_date SET DEFAULT '';

                ALTER TABLE seizure_management_recoverymemo
                  ALTER COLUMN recovery_date SET NOT NULL;
              END IF;
            END $$;
            """,
            reverse_sql=migrations.RunSQL.noop,
        ),
    ]
