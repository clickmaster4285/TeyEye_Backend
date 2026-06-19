# Optional disposition / posting fields for employee directory

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("users", "0006_add_fir_investigation_seizing_officer_roles"),
    ]

    operations = [
        migrations.AddField(
            model_name="staff",
            name="personal_number",
            field=models.CharField(blank=True, max_length=50, null=True),
        ),
        migrations.AddField(
            model_name="staff",
            name="bps",
            field=models.CharField(blank=True, max_length=10, null=True),
        ),
        migrations.AddField(
            model_name="staff",
            name="qualification",
            field=models.CharField(blank=True, max_length=200, null=True),
        ),
        migrations.AddField(
            model_name="staff",
            name="current_posting",
            field=models.CharField(blank=True, max_length=300, null=True),
        ),
        migrations.AddField(
            model_name="staff",
            name="collector_name",
            field=models.CharField(blank=True, max_length=200, null=True),
        ),
        migrations.AddField(
            model_name="staff",
            name="transferred_from",
            field=models.CharField(blank=True, max_length=300, null=True),
        ),
        migrations.AddField(
            model_name="staff",
            name="transferred_to",
            field=models.CharField(blank=True, max_length=300, null=True),
        ),
    ]
