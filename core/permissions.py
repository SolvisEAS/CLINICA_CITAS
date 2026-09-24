"""
Permisos compartidos entre módulos, basados en el campo `role` del
usuario (PACIENTE, DOCTOR, ADMIN — ver apps.users.models.User).
"""
from rest_framework.permissions import SAFE_METHODS, BasePermission


class IsAdminRole(BasePermission):
    """Solo usuarios con role=ADMIN."""

    def has_permission(self, request, view):
        user = request.user
        return bool(user and user.is_authenticated and user.role == "ADMIN")


class IsDoctorRole(BasePermission):
    """Solo usuarios con role=DOCTOR."""

    def has_permission(self, request, view):
        user = request.user
        return bool(user and user.is_authenticated and user.role == "DOCTOR")


class IsPatientRole(BasePermission):
    """Solo usuarios con role=PACIENTE."""

    def has_permission(self, request, view):
        user = request.user
        return bool(user and user.is_authenticated and user.role == "PACIENTE")


class IsAdminOrOwnerDoctor(BasePermission):
    """
    Permite el acceso completo a ADMIN. A un DOCTOR le permite operar
    únicamente sobre objetos que le pertenecen a él mismo (por ejemplo,
    su propio horario semanal o sus propios bloqueos).

    Se espera que el objeto tenga un atributo `doctor` (o sea él mismo
    un Doctor) con un campo `user` apuntando al usuario dueño.
    """

    def has_permission(self, request, view):
        user = request.user
        if not (user and user.is_authenticated):
            return False
        if request.method in SAFE_METHODS:
            return user.role in ("ADMIN", "DOCTOR", "PACIENTE")
        return user.role in ("ADMIN", "DOCTOR")

    def has_object_permission(self, request, view, obj):
        user = request.user
        if user.role == "ADMIN":
            return True
        if user.role == "DOCTOR":
            doctor = getattr(obj, "doctor", obj)
            return getattr(doctor, "user_id", None) == user.id
        return request.method in SAFE_METHODS
