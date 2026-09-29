from datetime import date as date_cls

from rest_framework import permissions, viewsets
from rest_framework.exceptions import ValidationError
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.doctors.models import Doctor
from core.permissions import IsAdminOrOwnerDoctor

from .models import AvailabilityException, WeeklySchedule
from .serializers import (
    AvailabilityExceptionSerializer,
    AvailableSlotSerializer,
    WeeklyScheduleSerializer,
)
from .services import get_available_slots


class WeeklyScheduleViewSet(viewsets.ModelViewSet):
    """
    Gestión del horario semanal habitual de un doctor.
    ADMIN puede gestionar cualquiera; un DOCTOR solo el suyo propio.
    """

    serializer_class = WeeklyScheduleSerializer
    permission_classes = [permissions.IsAuthenticated, IsAdminOrOwnerDoctor]
    filterset_fields = ["doctor", "weekday", "active"]

    def get_queryset(self):
        qs = WeeklySchedule.objects.select_related("doctor", "doctor__user").all()
        user = self.request.user
        if user.role == "DOCTOR":
            qs = qs.filter(doctor__user=user)
        return qs

    def perform_create(self, serializer):
        user = self.request.user
        if user.role == "DOCTOR":
            doctor = Doctor.objects.get(user=user)
            serializer.save(doctor=doctor)
        else:
            serializer.save()


class AvailabilityExceptionViewSet(viewsets.ModelViewSet):
    """Bloqueos/ausencias puntuales de un doctor (mismo esquema de permisos)."""

    serializer_class = AvailabilityExceptionSerializer
    permission_classes = [permissions.IsAuthenticated, IsAdminOrOwnerDoctor]
    filterset_fields = ["doctor", "type"]

    def get_queryset(self):
        qs = AvailabilityException.objects.select_related("doctor", "doctor__user").all()
        user = self.request.user
        if user.role == "DOCTOR":
            qs = qs.filter(doctor__user=user)
        return qs

    def perform_create(self, serializer):
        user = self.request.user
        if user.role == "DOCTOR":
            doctor = Doctor.objects.get(user=user)
            serializer.save(doctor=doctor)
        else:
            serializer.save()


class DoctorAvailabilityView(APIView):
    """
    GET /api/doctors/{doctor_id}/availability/?date=YYYY-MM-DD

    Devuelve los horarios disponibles de ese doctor para esa fecha.
    Público, sin login: el paciente lo necesita para elegir un horario
    antes de reservar y no tiene cuenta.
    """

    permission_classes = [permissions.AllowAny]

    def get(self, request, doctor_id):
        doctor = Doctor.objects.filter(pk=doctor_id, active=True).first()
        if not doctor:
            return Response({"detail": "Doctor no encontrado o inactivo."}, status=404)

        date_param = request.query_params.get("date")
        if not date_param:
            raise ValidationError({"date": "Este parámetro es obligatorio (formato YYYY-MM-DD)."})
        try:
            target_date = date_cls.fromisoformat(date_param)
        except ValueError:
            raise ValidationError({"date": "Formato inválido, usá YYYY-MM-DD."})

        slots = get_available_slots(doctor, target_date)
        data = [{"start_datetime": s, "end_datetime": e} for s, e in slots]
        serializer = AvailableSlotSerializer(data, many=True)
        return Response(serializer.data)
