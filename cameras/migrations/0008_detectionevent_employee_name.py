from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ("cameras", "0007_detectionevent_clip"),
    ]

    operations = [
        migrations.SeparateDatabaseAndState(
            state_operations=[
                migrations.AddField(
                    model_name="detectionevent",
                    name="employee_name",
                    field=models.CharField(
                        blank=True,
                        default="",
                        help_text="Recognized staff name when a person/face is identified; empty for other objects.",
                        max_length=150,
                    ),
                ),
            ],
            database_operations=[
                migrations.RunSQL(
                    sql="""
                        ALTER TABLE cameras_detectionevent
                        ADD COLUMN IF NOT EXISTS employee_name varchar(150) NOT NULL DEFAULT '';
                    """,
                    reverse_sql=migrations.RunSQL.noop,
                ),
                migrations.RunSQL(
                    sql="""
                        ALTER TABLE cameras_detectionevent
                        ALTER COLUMN employee_name SET DEFAULT '';
                    """,
                    reverse_sql=migrations.RunSQL.noop,
                ),
                migrations.RunSQL(
                    sql="""
                        UPDATE cameras_detectionevent
                        SET employee_name = ''
                        WHERE employee_name IS NULL;
                    """,
                    reverse_sql=migrations.RunSQL.noop,
                ),
            ],
        ),
    ]
