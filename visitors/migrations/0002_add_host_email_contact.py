# Generated manually: add host_email and host_contact_number to existing Visitor table

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("visitors", "0001_add_host_email_contact_and_enforcement"),
    ]

    operations = [
        migrations.AddField(
            model_name="visitor",
            name="host_email",
            field=models.CharField(blank=True, max_length=254, default=""),
            preserve_default=True,
        ),
        migrations.AddField(
            model_name="visitor",
            name="host_contact_number",
            field=models.CharField(blank=True, max_length=30, default=""),
            preserve_default=True,
        ),
    ]
