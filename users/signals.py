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
    image_changed = created or (current and current != previous)

    if not current:
        return

    image_changed = created or (current != previous)
    try:
        from ml.face_sync import staff_needs_face_enrollment, sync_staff_face_after_save

        if not image_changed and not staff_needs_face_enrollment(instance):
            return
        sync_staff_face_after_save(instance, image_changed=image_changed)
    except Exception:
        logger.exception("Failed to enroll face for staff %s", instance.pk)
