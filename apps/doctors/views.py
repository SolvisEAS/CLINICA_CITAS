from rest_framework import permissions, viewsets

from core.permissions import IsAdminRole

from .models import Doctor
from .serializers import DoctorSerializer


class DoctorViewSet(viewsets.ModelViewSet):
    """
    GET /api/doctors/ y /api/doctors/{id}/ — cualquier usuario autenticado
    (los pacientes necesitan ver la lista de doctores para reservar).

    POST/PUT/PATCH/DELETE — solo ADMIN.
    """

    queryset = Doctor.objects.select_related("user").all()
    serializer_class = DoctorSerializer
    filterset_fields = ["active", "specialty"]
    search_fields = ["user__first_name", "user__last_name", "specialty"]
    ordering_fields = ["user__first_name", "created_at"]

    def get_permissions(self):
        if self.action in ("list", "retrieve"):
            return [permissions.IsAuthenticated()]
        return [permissions.IsAuthenticated(), IsAdminRole()]

    def get_queryset(self):
        qs = super().get_queryset()
        # Los pacientes solo necesitan ver doctores activos para reservar.
        if self.request.user.role == "PACIENTE" and self.action == "list":
            qs = qs.filter(active=True)
        return qs
