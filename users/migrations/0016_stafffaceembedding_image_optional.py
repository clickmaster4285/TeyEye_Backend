from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("users", "0015_staff_father_name"),
    ]

    operations = [
        migrations.AlterField(
            model_name="stafffaceembedding",
            name="image",
            field=models.ImageField(blank=True, null=True, upload_to="staff_faces/"),
        ),
    ]
