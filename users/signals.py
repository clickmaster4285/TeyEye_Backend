import logging

from django.db.models.signals import post_save, pre_save
from django.dispatch import receiver

from .models import Staff

logger = logging.getLogger(__name__)

_profile_image_before_save: dict[int, str] = {}


@receiver(pre_save, sender=Staff)
def cache_staff_profile_image(sender, instance: Staff, **kwargs):
    if instance.pk:
        try:
            old = Staff.objects.filter(pk=instance.pk).values_list("profile_image", flat=True).first()
            _profile_image_before_save[instance.pk] = str(old or "")
        except Exception:
            _profile_image_before_save[instance.pk] = ""
    else:
        _profile_image_before_save[id(instance)] = ""


@receiver(post_save, sender=Staff)
def enroll_staff_face_on_save(sender, instance: Staff, created: bool, **kwargs):
    cache_key = instance.pk if instance.pk else id(instance)
    previous = _profile_image_before_save.pop(cache_key, "")
    current = str(instance.profile_image.name if instance.profile_image else "")
    if not current:
        return

    image_changed = created or (current != previous)
    # Only (re)build face embedding when the profile photo file actually changed.
    if not image_changed:
        return

    try:
        from ml.face_sync import sync_staff_face_after_save

        sync_staff_face_after_save(instance, image_changed=True)
    except Exception:
        logger.exception("Failed to enroll face for staff %s", instance.pk)
