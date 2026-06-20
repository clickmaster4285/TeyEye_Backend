from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("users", "0014_stafffaceembedding_source_profile_image"),
    ]

    operations = [
        migrations.SeparateDatabaseAndState(
            state_operations=[
                migrations.AddField(
                    model_name="staff",
                    name="father_name",
                    field=models.CharField(blank=True, max_length=150, null=True),
                ),
            ],
            database_operations=[
                migrations.RunSQL(
                    sql="""
                    ALTER TABLE users_staff
                    ADD COLUMN IF NOT EXISTS father_name varchar(150) NULL;
                    """,
                    reverse_sql=migrations.RunSQL.noop,
                ),
            ],
        ),
    ]
