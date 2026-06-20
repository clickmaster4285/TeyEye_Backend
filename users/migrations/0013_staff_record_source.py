from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("users", "0012_stafffaceembedding"),
    ]

    operations = [
        migrations.SeparateDatabaseAndState(
            state_operations=[
                migrations.AddField(
                    model_name="staff",
                    name="record_source",
                    field=models.CharField(
                        choices=[
                            ("database", "Database"),
                            ("disposition", "Disposition"),
                        ],
                        default="database",
                        max_length=20,
                    ),
                ),
            ],
            database_operations=[
                migrations.RunSQL(
                    sql="""
                    ALTER TABLE users_staff
                    ADD COLUMN IF NOT EXISTS record_source varchar(20) NOT NULL DEFAULT 'database';
                    """,
                    reverse_sql=migrations.RunSQL.noop,
                ),
                migrations.RunSQL(
                    sql="""
                    UPDATE users_staff SET record_source = 'database' WHERE record_source IS NULL OR record_source = '';
                    """,
                    reverse_sql=migrations.RunSQL.noop,
                ),
            ],
        ),
    ]
