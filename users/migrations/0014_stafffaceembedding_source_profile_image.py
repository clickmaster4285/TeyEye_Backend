from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("users", "0013_staff_record_source"),
    ]

    operations = [
        migrations.AddField(
            model_name="stafffaceembedding",
            name="source_profile_image",
            field=models.CharField(
                blank=True,
                default="",
                help_text="Staff.profile_image path when this embedding was generated.",
                max_length=500,
            ),
        ),
    ]
