# Align RecoveryMemo table with current model.
# Live DB still has legacy columns (items_description, summary, reference_number, created_by)
# while the model expects goods_description, quantity, remarks, deposit_account_id.

from django.db import migrations


class Migration(migrations.Migration):

    dependencies = [
        ("seizure_management", "0010_assessment_approval_workflow"),
        ("detentions", "0002_alter_detentionmemo_options_depositaccountentry_and_more"),
    ]

    operations = [
        migrations.RunSQL(
            sql="""
            ALTER TABLE seizure_management_recoverymemo
              ADD COLUMN IF NOT EXISTS goods_description text NOT NULL DEFAULT '';

            ALTER TABLE seizure_management_recoverymemo
              ADD COLUMN IF NOT EXISTS quantity varchar(120) NOT NULL DEFAULT '';

            ALTER TABLE seizure_management_recoverymemo
              ADD COLUMN IF NOT EXISTS remarks text NOT NULL DEFAULT '';

            ALTER TABLE seizure_management_recoverymemo
              ADD COLUMN IF NOT EXISTS deposit_account_id uuid NULL;

            DO $$
            BEGIN
              IF EXISTS (
                SELECT 1 FROM information_schema.columns
                WHERE table_name = 'seizure_management_recoverymemo'
                  AND column_name = 'items_description'
              ) THEN
                UPDATE seizure_management_recoverymemo
                SET goods_description = COALESCE(NULLIF(goods_description, ''), items_description, '')
                WHERE goods_description = '' OR goods_description IS NULL;
              END IF;

              IF EXISTS (
                SELECT 1 FROM information_schema.columns
                WHERE table_name = 'seizure_management_recoverymemo'
                  AND column_name = 'summary'
              ) THEN
                UPDATE seizure_management_recoverymemo
                SET remarks = COALESCE(NULLIF(remarks, ''), summary, '')
                WHERE remarks = '' OR remarks IS NULL;
              END IF;
            END $$;

            DO $$
            BEGIN
              IF EXISTS (
                SELECT 1 FROM information_schema.tables
                WHERE table_name = 'detentions_depositaccountentry'
              ) AND NOT EXISTS (
                SELECT 1 FROM pg_constraint
                WHERE conname = 'seizure_mgmt_recovery_deposit_account_fk'
              ) THEN
                ALTER TABLE seizure_management_recoverymemo
                  ADD CONSTRAINT seizure_mgmt_recovery_deposit_account_fk
                  FOREIGN KEY (deposit_account_id)
                  REFERENCES detentions_depositaccountentry(id)
                  ON DELETE SET NULL;
              END IF;
            EXCEPTION WHEN OTHERS THEN
              NULL;
            END $$;
            """,
            reverse_sql=migrations.RunSQL.noop,
        ),
    ]
