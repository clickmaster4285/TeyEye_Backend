from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ("cameras", "0008_detectionevent_employee_name"),
    ]

    operations = [
        migrations.SeparateDatabaseAndState(
            state_operations=[
                migrations.AddField(
                    model_name="detectionevent",
                    name="personal_number",
                    field=models.CharField(
                        blank=True,
                        default="",
                        help_text="Recognized staff personal number when a person/face is identified.",
                        max_length=50,
                    ),
                ),
            ],
            database_operations=[
                migrations.RunSQL(
                    sql="""
                        ALTER TABLE cameras_detectionevent
                        ADD COLUMN IF NOT EXISTS personal_number varchar(50) NOT NULL DEFAULT '';
                    """,
                    reverse_sql=migrations.RunSQL.noop,
                ),
                migrations.RunSQL(
                    sql="""
                        ALTER TABLE cameras_detectionevent
                        ALTER COLUMN personal_number SET DEFAULT '';
                    """,
                    reverse_sql=migrations.RunSQL.noop,
                ),
                migrations.RunSQL(
                    sql="""
                        UPDATE cameras_detectionevent
                        SET personal_number = ''
                        WHERE personal_number IS NULL;
                    """,
                    reverse_sql=migrations.RunSQL.noop,
                ),
            ],
        ),
    ]
