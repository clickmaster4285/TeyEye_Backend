# Drop leftover columns from the old DetentionAssessment schema.

from django.db import migrations


class Migration(migrations.Migration):

    dependencies = [
        ("seizure_management", "0007_align_detentionassessment_schema"),
    ]

    operations = [
        migrations.RunSQL(
            sql="""
            ALTER TABLE seizure_management_detentionassessment
              DROP COLUMN IF EXISTS reference_number;

            ALTER TABLE seizure_management_detentionassessment
              DROP COLUMN IF EXISTS condition_summary;

            ALTER TABLE seizure_management_detentionassessment
              DROP COLUMN IF EXISTS created_by;
            """,
            reverse_sql=migrations.RunSQL.noop,
        ),
    ]
