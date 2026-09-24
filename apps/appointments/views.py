from datetime import date as date_cls

from django.utils import timezone
from rest_framework import generics, permissions, status
from rest_framework.exceptions import ValidationError
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.doctors.models import Doctor
from core.permissions import IsPatientRole

from .models import Appointment
from .serializers import AppointmentCreateSerializer, AppointmentSerializer


class BookAppointmentView(generics.CreateAPIView):
    """POST /api/appointments/ — un paciente reserva un turno."""

    serializer_class = AppointmentCreateSerializer
    permission_classes = [permissions.IsAuthenticated, IsPatientRole]

    def create(self, request, *args, **kwargs):
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        appointment = serializer.save()
        output = AppointmentSerializer(appointment)
        return Response(output.data, status=status.HTTP_201_CREATED)


class MyAppointmentsView(generics.ListAPIView):
    """GET /api/appointments/mine/ — citas del paciente autenticado."""

    serializer_class = AppointmentSerializer
    permission_classes = [permissions.IsAuthenticated, IsPatientRole]
    filterset_fields = ["status"]
    ordering_fields = ["start_datetime"]

    def get_queryset(self):
        return (
            Appointment.objects.filter(patient=self.request.user)
            .select_related("doctor", "doctor__user")
            .order_by("-start_datetime")
        )


class DoctorAgendaView(APIView):
    """
    GET /api/appointments/agenda/?date=YYYY-MM-DD — agenda de un doctor.
    Por defecto, las citas del día de hoy. Solo el propio doctor o un
    ADMIN pueden verla.
    """

    permission_classes = [permissions.IsAuthenticated]

    def get(self, request):
        user = request.user
        if user.role == "DOCTOR":
            doctor = Doctor.objects.filter(user=user).first()
            if not doctor:
                return Response({"detail": "Tu usuario no tiene un perfil de doctor asociado."}, status=400)
        elif user.role == "ADMIN":
            doctor_id = request.query_params.get("doctor")
            if not doctor_id:
                raise ValidationError({"doctor": "Los administradores deben indicar ?doctor=<id>."})
            doctor = Doctor.objects.filter(pk=doctor_id).first()
            if not doctor:
                return Response({"detail": "Doctor no encontrado."}, status=404)
        else:
            return Response({"detail": "No autorizado."}, status=403)

        date_param = request.query_params.get("date")
        if date_param:
            try:
                target_date = date_cls.fromisoformat(date_param)
            except ValueError:
                raise ValidationError({"date": "Formato inválido, usá YYYY-MM-DD."})
        else:
            target_date = timezone.localdate()

        appointments = (
            Appointment.objects.filter(
                doctor=doctor,
                start_datetime__date=target_date,
            )
            .select_related("patient", "doctor", "doctor__user")
            .order_by("start_datetime")
        )
        serializer = AppointmentSerializer(appointments, many=True)
        return Response({"date": target_date, "doctor": doctor.id, "appointments": serializer.data})


class CancelAppointmentView(APIView):
    """
    PATCH /api/appointments/{id}/cancel/ — el paciente cancela su propia
    cita (si todavía está confirmada y es en el futuro).
    """

    permission_classes = [permissions.IsAuthenticated, IsPatientRole]

    def patch(self, request, pk):
        appointment = Appointment.objects.filter(pk=pk, patient=request.user).first()
        if not appointment:
            return Response({"detail": "Cita no encontrada."}, status=404)
        if appointment.status != Appointment.Status.CONFIRMADA:
            return Response({"detail": "Solo se pueden cancelar citas confirmadas."}, status=400)
        if appointment.start_datetime <= timezone.now():
            return Response({"detail": "No se puede cancelar una cita que ya pasó."}, status=400)
        appointment.status = Appointment.Status.CANCELADA
        appointment.save(update_fields=["status", "period"])
        return Response(AppointmentSerializer(appointment).data)


class UpdateAppointmentStatusView(APIView):
    """
    PATCH /api/appointments/{id}/status/ con {"status": "ATENDIDA"} —
    el doctor dueño de la cita (o un ADMIN) la marca como atendida,
    no asistió, o cancelada.
    """

    permission_classes = [permissions.IsAuthenticated]

    def patch(self, request, pk):
        appointment = Appointment.objects.select_related("doctor", "doctor__user").filter(pk=pk).first()
        if not appointment:
            return Response({"detail": "Cita no encontrada."}, status=404)

        user = request.user
        is_owner_doctor = user.role == "DOCTOR" and appointment.doctor.user_id == user.id
        if not (is_owner_doctor or user.role == "ADMIN"):
            return Response({"detail": "No autorizado."}, status=403)

        new_status = request.data.get("status")
        valid_statuses = [Appointment.Status.ATENDIDA, Appointment.Status.NO_ASISTIO, Appointment.Status.CANCELADA]
        if new_status not in valid_statuses:
            raise ValidationError({"status": f"Debe ser uno de: {', '.join(valid_statuses)}."})

        appointment.status = new_status
        appointment.save(update_fields=["status", "period"])
        return Response(AppointmentSerializer(appointment).data)
