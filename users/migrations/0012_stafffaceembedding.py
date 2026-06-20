from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):

    dependencies = [
        ("users", "0011_add_location_admin_role"),
    ]

    operations = [
        migrations.CreateModel(
            name="StaffFaceEmbedding",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("image", models.ImageField(upload_to="staff_faces/")),
                (
                    "embedding",
                    models.JSONField(
                        help_text="Face feature vector (cosine similarity matching, SFace/ArcFace-style)."
                    ),
                ),
                ("embedding_dim", models.PositiveSmallIntegerField(default=0)),
                ("embedding_model", models.CharField(default="sface", max_length=32)),
                (
                    "identity_label",
                    models.CharField(
                        db_index=True,
                        help_text="Username or full name used when matching detections.",
                        max_length=150,
                    ),
                ),
                ("is_primary", models.BooleanField(default=True)),
                ("is_active", models.BooleanField(default=True)),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("updated_at", models.DateTimeField(auto_now=True)),
                (
                    "staff",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="face_embeddings",
                        to="users.staff",
                    ),
                ),
            ],
            options={
                "ordering": ["-is_primary", "-updated_at"],
                "indexes": [
                    models.Index(fields=["staff", "is_active"], name="users_staff_staff_i_6e2a8c_idx"),
                ],
            },
        ),
    ]
