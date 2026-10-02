"""
Permisos compartidos entre módulos, basados en los Permisos y Grupos de
Django (ver apps.users.roles): un usuario puede lo que le dan sus
permisos, y el superusuario de Django puede todo.
"""
from rest_framework.permissions import BasePermission, DjangoModelPermissions

from apps.users.roles import MANAGE_USERS_PERMISSION


def is_admin(user):
    """Superusuario de Django o con permiso de administrar usuarios (grupo Administradores)."""
    return bool(
        user
        and user.is_authenticated
        and user.is_active
        and (user.is_superuser or user.has_perm(MANAGE_USERS_PERMISSION))
    )


def get_doctor_profile(user):
    """Perfil de doctor del usuario, o None si no tiene (p. ej. un administrador)."""
    if not (user and user.is_authenticated):
        return None
    from apps.doctors.models import Doctor  # import diferido: evita import circular

    return Doctor.objects.filter(user=user).first()


class IsAdministrator(BasePermission):
    message = "Solo un administrador puede hacer esto."

    def has_permission(self, request, view):
        return is_admin(request.user)


class ModelPermissions(DjangoModelPermissions):
    """
    DjangoModelPermissions exige add/change/delete para escribir pero
    deja leer a cualquiera autenticado; acá leer también exige view_.
    """

    perms_map = {
        **DjangoModelPermissions.perms_map,
        "GET": ["%(app_label)s.view_%(model_name)s"],
        "HEAD": ["%(app_label)s.view_%(model_name)s"],
    }


class OwnDoctorObjects(BasePermission):
    """Un administrador opera sobre cualquier objeto; un doctor, solo sobre los suyos (obj.doctor)."""

    def has_object_permission(self, request, view, obj):
        if is_admin(request.user):
            return True
        doctor = getattr(obj, "doctor", None)
        return doctor is not None and doctor.user_id == request.user.id
