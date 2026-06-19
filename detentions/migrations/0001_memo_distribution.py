from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = []

    operations = [
        migrations.SeparateDatabaseAndState(
            state_operations=[
                migrations.CreateModel(
                    name="DetentionMemo",
                    fields=[
                        ("id", models.UUIDField(primary_key=True, serialize=False)),
                        ("disposition_status", models.CharField(blank=True, default="", max_length=80)),
                    ],
                    options={"managed": False},
                ),
            ],
            database_operations=[
                migrations.RunSQL(
                    sql=(
                        "ALTER TABLE detentions_detentionmemo "
                        "ADD COLUMN IF NOT EXISTS disposition_status varchar(80) NOT NULL DEFAULT ''"
                    ),
                    reverse_sql=migrations.RunSQL.noop,
                ),
            ],
        ),
    ]
