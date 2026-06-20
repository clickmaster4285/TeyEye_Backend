# Drop legacy Camera columns left behind when 0005 exited early on existing DBs.

from django.db import migrations


def _column_exists(cursor, table_name: str, column_name: str) -> bool:
    cursor.execute(
        """
        SELECT 1 FROM information_schema.columns
        WHERE table_schema = current_schema()
          AND table_name = %s AND column_name = %s
        """,
        [table_name, column_name],
    )
    return cursor.fetchone() is not None


def drop_legacy_columns(apps, schema_editor):
    connection = schema_editor.connection
    with connection.cursor() as cursor:
        for column in ("ip_address", "stream_url", "site_label"):
            if _column_exists(cursor, "cameras_camera", column):
                cursor.execute(f'ALTER TABLE cameras_camera DROP COLUMN "{column}";')


def noop_reverse(apps, schema_editor):
    pass


class Migration(migrations.Migration):

    dependencies = [
        ("cameras", "0005_site_nvr_hierarchy"),
    ]

    operations = [
        migrations.RunPython(drop_legacy_columns, noop_reverse),
    ]
