from rest_framework import permissions

GLOBAL_ADMIN_ROLE = "ADMIN"
LOCATION_ADMIN_ROLE = "LOCATION_ADMIN"

PRIVILEGED_ROLES = frozenset({GLOBAL_ADMIN_ROLE, LOCATION_ADMIN_ROLE})


def is_global_admin(user) -> bool:
    return bool(
        user
        and getattr(user, "is_authenticated", False)
        and getattr(user, "role", None) == GLOBAL_ADMIN_ROLE
    )


def is_location_admin(user) -> bool:
    return bool(
        user
        and getattr(user, "is_authenticated", False)
        and getattr(user, "role", None) == LOCATION_ADMIN_ROLE
    )


def is_admin_user(user) -> bool:
    return is_global_admin(user) or is_location_admin(user)


def get_location_scope(user) -> str | None:
    """
    Return the location code the user is restricted to, or None if they may see all sites.
    Global admins are never scoped; everyone else uses their assigned location when set.
    """
    if not user or not getattr(user, "is_authenticated", False):
        return None
    if is_global_admin(user):
        return None
    loc = (getattr(user, "location", None) or "").strip()
    return loc or None


def get_effective_location(user, query_param: str | None = None) -> str | None:
    """Location used for list filtering. Scoped users ignore query_param overrides."""
    scope = get_location_scope(user)
    if scope:
        return scope
    qp = (query_param or "").strip()
    return qp or None


def apply_location_filter(queryset, user, field: str = "location", query_param: str | None = None):
    loc = get_effective_location(user, query_param)
    if loc:
        return queryset.filter(**{field: loc})
    return queryset


def resolve_location_for_write(user, requested_location: str = "") -> str:
    """On create/update: location-scoped users always write to their own site."""
    scope = get_location_scope(user)
    if scope:
        return scope
    return (requested_location or "").strip()


def location_admin_may_assign_role(actor, role: str) -> bool:
    if is_global_admin(actor):
        return True
    if is_location_admin(actor):
        return role not in PRIVILEGED_ROLES
    return True


class IsAdminOrHR(permissions.BasePermission):
    """Allow access to global admin, location admin, HR, and IT admin."""

    allowed_roles = ("ADMIN", "LOCATION_ADMIN", "HR", "IT_ADMIN")

    def has_permission(self, request, view):
        if not request.user or not request.user.is_authenticated:
            return False
        return getattr(request.user, "role", None) in self.allowed_roles


class IsGlobalAdmin(permissions.BasePermission):
    """Allow access only to the global super administrator."""

    def has_permission(self, request, view):
        return is_global_admin(request.user)


class IsAdminUser(permissions.BasePermission):
    """Allow global or location administrators."""

    def has_permission(self, request, view):
        return is_admin_user(request.user)
