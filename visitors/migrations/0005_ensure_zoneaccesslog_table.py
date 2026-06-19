# Ensures visitors_zoneaccesslog exists (0001 was applied but table may be missing in DB).

from django.db import migrations


def create_zone_access_log_if_missing(apps, schema_editor):
    connection = schema_editor.connection
    tables = set(connection.introspection.table_names())
    if "visitors_zoneaccesslog" in tables:
        return
    ZoneAccessLog = apps.get_model("visitors", "ZoneAccessLog")
    schema_editor.create_model(ZoneAccessLog)


def noop_reverse(apps, schema_editor):
    pass


class Migration(migrations.Migration):

    dependencies = [
        ("visitors", "0004_vms_workflow_and_related_models"),
    ]

    operations = [
        migrations.RunPython(create_zone_access_log_if_missing, noop_reverse),
    ]
