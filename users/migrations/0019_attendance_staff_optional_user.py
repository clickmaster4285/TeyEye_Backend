from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):

    dependencies = [
        ("users", "0018_staff_multi_photos_embeddings"),
    ]

    operations = [
        migrations.AddField(
            model_name="attendance",
            name="staff",
            field=models.ForeignKey(
                blank=True,
                null=True,
                on_delete=django.db.models.deletion.CASCADE,
                related_name="staff_attendance_records",
                to="users.staff",
            ),
        ),
        migrations.AlterField(
            model_name="attendance",
            name="user",
            field=models.ForeignKey(
                blank=True,
                null=True,
                on_delete=django.db.models.deletion.CASCADE,
                related_name="attendance_records",
                to="users.user",
            ),
        ),
        migrations.AddConstraint(
            model_name="attendance",
            constraint=models.UniqueConstraint(
                condition=models.Q(("user__isnull", False)),
                fields=("user", "date"),
                name="users_attendance_unique_user_date",
            ),
        ),
        migrations.AddConstraint(
            model_name="attendance",
            constraint=models.UniqueConstraint(
                condition=models.Q(("staff__isnull", False)),
                fields=("staff", "date"),
                name="users_attendance_unique_staff_date",
            ),
        ),
    ]
