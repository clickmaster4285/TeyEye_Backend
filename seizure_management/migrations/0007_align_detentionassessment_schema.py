# Generated manually to align DetentionAssessment table with current model.
# The live table was created from an older schema while 0001 was marked applied.

from django.db import migrations


class Migration(migrations.Migration):

    dependencies = [
        ("seizure_management", "0006_notesheet_filefield_max_length"),
    ]

    operations = [
        migrations.RunSQL(
            sql="""
            -- goods_condition (was condition_summary in older schema)
            ALTER TABLE seizure_management_detentionassessment
              ADD COLUMN IF NOT EXISTS goods_condition varchar(400) NOT NULL DEFAULT '';

            DO $$
            BEGIN
              IF EXISTS (
                SELECT 1 FROM information_schema.columns
                WHERE table_name = 'seizure_management_detentionassessment'
                  AND column_name = 'condition_summary'
              ) THEN
                UPDATE seizure_management_detentionassessment
                SET goods_condition = COALESCE(NULLIF(goods_condition, ''), LEFT(condition_summary, 400), '')
                WHERE goods_condition = '' OR goods_condition IS NULL;
              END IF;
            END $$;

            -- document_relevance
            ALTER TABLE seizure_management_detentionassessment
              ADD COLUMN IF NOT EXISTS document_relevance varchar(40) NOT NULL DEFAULT 'Pending';

            CREATE INDEX IF NOT EXISTS seizure_mgmt_assess_doc_rel_idx
              ON seizure_management_detentionassessment (document_relevance);

            -- assessment_date: model uses CharField; older schema used date
            ALTER TABLE seizure_management_detentionassessment
              ALTER COLUMN assessment_date TYPE varchar(40)
              USING COALESCE(assessment_date::text, '');

            ALTER TABLE seizure_management_detentionassessment
              ALTER COLUMN assessment_date SET DEFAULT '';

            ALTER TABLE seizure_management_detentionassessment
              ALTER COLUMN assessment_date SET NOT NULL;

            -- ensure status default matches model
            ALTER TABLE seizure_management_detentionassessment
              ALTER COLUMN status TYPE varchar(40);

            UPDATE seizure_management_detentionassessment
            SET status = 'In Progress'
            WHERE status IS NULL OR status = '';

            ALTER TABLE seizure_management_detentionassessment
              ALTER COLUMN status SET DEFAULT 'In Progress';
            """,
            reverse_sql=migrations.RunSQL.noop,
        ),
    ]
