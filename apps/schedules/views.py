from datetime import date as date_cls
from datetime import timedelta

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


class DoctorOwnedMixin:
    """
    Un DOCTOR siempre opera sobre su propio perfil (se ignora cualquier
    `doctor` que mande); un ADMIN tiene que indicar `doctor` al crear.
    """

    def _save_with_doctor(self, serializer, creating):
        user = self.request.user
        if user.role == "DOCTOR":
            doctor = Doctor.objects.filter(user=user).first()
            if not doctor:
                raise ValidationError({"doctor": "Tu usuario no tiene un perfil de doctor asociado."})
            serializer.save(doctor=doctor)
        else:
            if creating and not serializer.validated_data.get("doctor"):
                raise ValidationError({"doctor": "Indicá el doctor."})
            serializer.save()

    def perform_create(self, serializer):
        self._save_with_doctor(serializer, creating=True)

    def perform_update(self, serializer):
        self._save_with_doctor(serializer, creating=False)


class WeeklyScheduleViewSet(DoctorOwnedMixin, viewsets.ModelViewSet):
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


class AvailabilityExceptionViewSet(DoctorOwnedMixin, viewsets.ModelViewSet):
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


class DoctorAvailableDaysView(APIView):
    """
    GET /api/doctors/{doctor_id}/available-days/?start=YYYY-MM-DD&end=YYYY-MM-DD

    Público, sin login. Días del rango (ambos extremos incluidos) en los
    que el doctor tiene al menos un horario libre, para que el
    calendario del paciente marque qué días se pueden elegir sin pedir
    la disponibilidad día por día. Usa la misma lógica que el endpoint
    de horarios, así que nunca marca un día que después aparezca vacío.
    """

    permission_classes = [permissions.AllowAny]
    MAX_RANGE_DAYS = 62

    def get(self, request, doctor_id):
        doctor = Doctor.objects.filter(pk=doctor_id, active=True).first()
        if not doctor:
            return Response({"detail": "Doctor no encontrado o inactivo."}, status=404)

        try:
            start = date_cls.fromisoformat(request.query_params.get("start", ""))
            end = date_cls.fromisoformat(request.query_params.get("end", ""))
        except ValueError:
            raise ValidationError({"detail": "Indicá 'start' y 'end' con formato YYYY-MM-DD."})
        if end < start:
            raise ValidationError({"end": "Debe ser igual o posterior a 'start'."})
        if (end - start).days >= self.MAX_RANGE_DAYS:
            raise ValidationError({"end": f"El rango no puede superar {self.MAX_RANGE_DAYS} días."})

        days = []
        current = start
        while current <= end:
            count = len(get_available_slots(doctor, current))
            if count:
                days.append({"date": current.isoformat(), "available_slots": count})
            current += timedelta(days=1)
        return Response(days)
