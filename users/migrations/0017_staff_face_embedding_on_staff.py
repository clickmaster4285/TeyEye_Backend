from django.db import migrations, models


def copy_embeddings_to_staff(apps, schema_editor):
    Staff = apps.get_model("users", "Staff")
    StaffFaceEmbedding = apps.get_model("users", "StaffFaceEmbedding")
    for row in (
        StaffFaceEmbedding.objects.filter(is_active=True, is_primary=True)
        .order_by("staff_id", "-updated_at")
        .iterator()
    ):
        staff = Staff.objects.filter(pk=row.staff_id).first()
        if staff is None or not row.embedding:
            continue
        if staff.face_embedding:
            continue
        Staff.objects.filter(pk=staff.pk).update(
            face_embedding=row.embedding,
            face_embedding_dim=row.embedding_dim or len(row.embedding),
            face_embedding_model=row.embedding_model or "sface",
            face_identity_label=row.identity_label or "",
            face_embedding_profile_key=row.source_profile_image or "",
        )


class Migration(migrations.Migration):

    dependencies = [
        ("users", "0016_stafffaceembedding_image_optional"),
    ]

    operations = [
        migrations.AddField(
            model_name="staff",
            name="face_embedding",
            field=models.JSONField(
                blank=True,
                help_text="Face feature vector for ML matching.",
                null=True,
            ),
        ),
        migrations.AddField(
            model_name="staff",
            name="face_embedding_dim",
            field=models.PositiveSmallIntegerField(default=0),
        ),
        migrations.AddField(
            model_name="staff",
            name="face_embedding_model",
            field=models.CharField(blank=True, default="", max_length=32),
        ),
        migrations.AddField(
            model_name="staff",
            name="face_identity_label",
            field=models.CharField(
                blank=True,
                db_index=True,
                default="",
                help_text="Name/username label pushed to ML for recognition.",
                max_length=150,
            ),
        ),
        migrations.AddField(
            model_name="staff",
            name="face_embedding_profile_key",
            field=models.CharField(
                blank=True,
                default="",
                help_text="profile_image path when face_embedding was generated.",
                max_length=500,
            ),
        ),
        migrations.RunPython(copy_embeddings_to_staff, migrations.RunPython.noop),
        migrations.DeleteModel(
            name="StaffFaceEmbedding",
        ),
    ]
