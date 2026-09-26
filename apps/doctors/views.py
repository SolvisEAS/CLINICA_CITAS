from rest_framework import permissions, viewsets

from core.permissions import IsAdminRole

from .models import Doctor
from .serializers import DoctorSerializer


class DoctorViewSet(viewsets.ModelViewSet):
    """
    GET /api/doctors/ y /api/doctors/{id}/ — público, sin login (el
    paciente necesita ver la lista de doctores para reservar y no
    tiene cuenta).

    POST/PUT/PATCH/DELETE — solo ADMIN.
    """

    queryset = Doctor.objects.select_related("user").all()
    serializer_class = DoctorSerializer
    filterset_fields = ["active", "specialty"]
    search_fields = ["user__first_name", "user__last_name", "specialty"]
    ordering_fields = ["user__first_name", "created_at"]

    def get_permissions(self):
        if self.action in ("list", "retrieve"):
            return [permissions.AllowAny()]
        return [permissions.IsAuthenticated(), IsAdminRole()]

    def get_queryset(self):
        qs = super().get_queryset()
        user = self.request.user
        # Solo un ADMIN o DOCTOR autenticado necesita ver los inactivos
        # también; cualquier otra persona (paciente sin cuenta incluido)
        # solo ve los activos al listar.
        is_staff = user.is_authenticated and user.role in ("ADMIN", "DOCTOR")
        if self.action == "list" and not is_staff:
            qs = qs.filter(active=True)
        return qs
