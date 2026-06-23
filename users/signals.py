import json
import logging

from django.db.models.signals import post_save, pre_save
from django.dispatch import receiver

from .models import Staff
from .staff_photos import staff_photo_paths

logger = logging.getLogger(__name__)

_profile_image_before_save: dict[int, str] = {}
_staff_photos_before_save: dict[int, str] = {}


def _photos_fingerprint(staff: Staff) -> str:
    return json.dumps(staff_photo_paths(staff), sort_keys=False)


@receiver(pre_save, sender=Staff)
def cache_staff_profile_image(sender, instance: Staff, **kwargs):
    cache_key = instance.pk if instance.pk else id(instance)
    if instance.pk:
        try:
            old = Staff.objects.filter(pk=instance.pk).values_list("profile_image", flat=True).first()
            _profile_image_before_save[cache_key] = str(old or "")
            row = Staff.objects.filter(pk=instance.pk).values("staff_photos", "profile_image").first()
            if row:
                prev_staff = Staff(staff_photos=row.get("staff_photos") or [], profile_image=row.get("profile_image"))
                _staff_photos_before_save[cache_key] = _photos_fingerprint(prev_staff)
            else:
                _staff_photos_before_save[cache_key] = "[]"
        except Exception:
            _profile_image_before_save[cache_key] = ""
            _staff_photos_before_save[cache_key] = "[]"
    else:
        _profile_image_before_save[cache_key] = ""
        _staff_photos_before_save[cache_key] = "[]"


@receiver(post_save, sender=Staff)
def enroll_staff_face_on_save(sender, instance: Staff, created: bool, **kwargs):
    cache_key = instance.pk if instance.pk else id(instance)
    previous_image = _profile_image_before_save.pop(cache_key, "")
    previous_photos = _staff_photos_before_save.pop(cache_key, "[]")
    current_image = str(instance.profile_image.name if instance.profile_image else "")
    current_photos = _photos_fingerprint(instance)

    if not staff_photo_paths(instance):
        return

    image_changed = created or (current_image != previous_image)
    photos_changed = created or (current_photos != previous_photos)
    if not image_changed and not photos_changed:
        return

    try:
        from ml.face_sync import sync_staff_faces_after_save

        sync_staff_faces_after_save(instance, force=image_changed or photos_changed)
    except Exception:
        logger.exception("Failed to enroll faces for staff %s", instance.pk)
