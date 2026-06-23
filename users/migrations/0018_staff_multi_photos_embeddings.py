from django.db import migrations, models


def copy_single_photo_to_gallery(apps, schema_editor):
    Staff = apps.get_model("users", "Staff")
    for staff in Staff.objects.all().iterator():
        paths = list(staff.staff_photos or [])
        if not paths and staff.profile_image:
            key = str(getattr(staff.profile_image, "name", None) or staff.profile_image or "").strip()
            if key:
                paths = [key]
                staff.staff_photos = paths

        embeddings = list(staff.face_embeddings or [])
        if not embeddings and staff.face_embedding:
            emb = staff.face_embedding
            if isinstance(emb, list) and emb:
                image_key = str(staff.face_embedding_profile_key or "").strip()
                if not image_key and paths:
                    image_key = paths[0]
                embeddings = [
                    {
                        "image_key": image_key,
                        "embedding": emb,
                        "dim": staff.face_embedding_dim or len(emb),
                        "model": staff.face_embedding_model or "sface",
                    }
                ]
                staff.face_embeddings = embeddings

        if paths != (staff.staff_photos or []) or embeddings != (staff.face_embeddings or []):
            staff.save(update_fields=["staff_photos", "face_embeddings"])


class Migration(migrations.Migration):

    dependencies = [
        ("users", "0017_staff_face_embedding_on_staff"),
    ]

    operations = [
        migrations.AddField(
            model_name="staff",
            name="staff_photos",
            field=models.JSONField(
                blank=True,
                default=list,
                help_text="Ordered staff photo paths (max 5). First entry mirrors profile_image.",
            ),
        ),
        migrations.AddField(
            model_name="staff",
            name="face_embeddings",
            field=models.JSONField(
                blank=True,
                default=list,
                help_text="SFace vectors per staff photo: [{image_key, embedding, dim, model}, ...].",
            ),
        ),
        migrations.RunPython(copy_single_photo_to_gallery, migrations.RunPython.noop),
    ]
