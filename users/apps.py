import os
from django.apps import AppConfig
from django.db import OperationalError, IntegrityError
from django.db.models.signals import post_migrate


def create_initial_admin(sender, **kwargs):
    """Create a default superuser if no superuser exists (runs after migrate)."""
    from .models import User

    try:
        if User.objects.filter(is_superuser=True).exists():
            return

        username = os.getenv("INITIAL_ADMIN_USERNAME", "admin")
        email = os.getenv("INITIAL_ADMIN_EMAIL", "admin@example.com")
        password = os.getenv("INITIAL_ADMIN_PASSWORD", "Admin@123")
        phone = os.getenv("INITIAL_ADMIN_PHONE", "0000000000")

        User.objects.create_superuser(
            username=username,
            email=email,
            password=password,
            role="ADMIN",
            phone=phone,
            location=os.getenv("INITIAL_ADMIN_LOCATION", ""),
        )
    except (OperationalError, IntegrityError):
        pass


class UsersConfig(AppConfig):
    name = "users"

    def ready(self):
        post_migrate.connect(create_initial_admin, sender=self)
        from . import signals  # noqa: F401
