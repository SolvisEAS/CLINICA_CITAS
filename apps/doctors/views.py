from rest_framework import permissions, viewsets

from core.permissions import ModelPermissions, is_admin

from .models import Doctor
from .serializers import DoctorSerializer


class DoctorViewSet(viewsets.ModelViewSet):
    """
    GET /api/doctors/ y /api/doctors/{id}/ — público, sin login (el
    paciente necesita ver la lista de doctores para reservar y no
    tiene cuenta).

    POST/PUT/PATCH/DELETE — según los permisos de Django sobre Doctor
    (grupo Administradores: crear y editar; borrar, solo el superusuario:
    a un doctor se lo desactiva, no se lo elimina).
    """

    queryset = Doctor.objects.select_related("user").all()
    serializer_class = DoctorSerializer
    filterset_fields = ["active", "specialty"]
    search_fields = ["user__first_name", "user__last_name", "specialty"]
    ordering_fields = ["user__first_name", "created_at"]

    def get_permissions(self):
        if self.action in ("list", "retrieve"):
            return [permissions.AllowAny()]
        return [permissions.IsAuthenticated(), ModelPermissions()]

    def get_queryset(self):
        qs = super().get_queryset()
        # Solo un administrador necesita ver también los inactivos; el
        # resto (paciente sin cuenta incluido) ve los activos al listar.
        if self.action == "list" and not is_admin(self.request.user):
            qs = qs.filter(active=True)
        return qs
