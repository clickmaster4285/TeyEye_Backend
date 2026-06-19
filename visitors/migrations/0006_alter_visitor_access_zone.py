from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("visitors", "0005_ensure_zoneaccesslog_table"),
    ]

    operations = [
        migrations.AlterField(
            model_name="visitor",
            name="access_zone",
            field=models.CharField(blank=True, max_length=64),
        ),
    ]
