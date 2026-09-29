from datetime import date as date_cls, timedelta

from django.db import IntegrityError, transaction
from django.utils import timezone
from rest_framework import generics, permissions, status
from rest_framework.exceptions import NotFound, ValidationError
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.doctors.models import Doctor
from apps.patients.models import Patient
from apps.patients.utils import normalize_document_number
from apps.schedules.services import is_slot_available

from .models import Appointment
from .serializers import AppointmentCreateSerializer, AppointmentSerializer
from .services import patient_has_conflicting_appointment


class BookAppointmentView(generics.CreateAPIView):
    """
    POST /api/appointments/ — cualquiera reserva un turno indicando sus
    datos básicos (cédula, nombre, teléfono, correo). No requiere
    cuenta ni login: el paciente no se registra.
    """

    serializer_class = AppointmentCreateSerializer
    permission_classes = [permissions.AllowAny]

    def create(self, request, *args, **kwargs):
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        appointment = serializer.save()
        output = AppointmentSerializer(appointment)
        return Response(output.data, status=status.HTTP_201_CREATED)


def _get_patient_or_404(document_number):
    patient = Patient.objects.filter(pk=normalize_document_number(document_number)).first()
    if not patient:
        raise NotFound("No encontramos ningún paciente con ese número de documento.")
    return patient


def _get_patient_appointment_or_404(document_number, pk):
    patient = _get_patient_or_404(document_number)
    appointment = (
        Appointment.objects.filter(pk=pk, patient=patient)
        .select_related("doctor", "doctor__user", "patient")
        .first()
    )
    if not appointment:
        raise NotFound("Cita no encontrada para ese número de documento.")
    return appointment


class PatientAppointmentsView(generics.ListAPIView):
    """
    GET /api/patients/<document_number>/appointments/ — el paciente
    vuelve a consultar sus citas usando su cédula, sin login.
    """

    serializer_class = AppointmentSerializer
    permission_classes = [permissions.AllowAny]

    def get_queryset(self):
        patient = _get_patient_or_404(self.kwargs["document_number"])
        return (
            Appointment.objects.filter(patient=patient)
            .select_related("doctor", "doctor__user")
            .order_by("-start_datetime")
        )


class PatientRescheduleAppointmentView(APIView):
    """
    PATCH /api/patients/<document_number>/appointments/<pk>/ — el
    paciente edita (reprograma) su propia cita usando su cédula, sin
    login. Acepta `start_datetime` y/o `notes`.
    """

    permission_classes = [permissions.AllowAny]

    def patch(self, request, document_number, pk):
        appointment = _get_patient_appointment_or_404(document_number, pk)
        if appointment.status != Appointment.Status.CONFIRMADA:
            return Response({"detail": "Solo se pueden editar citas confirmadas."}, status=400)
        if appointment.start_datetime <= timezone.now():
            return Response({"detail": "No se puede editar una cita que ya pasó."}, status=400)

        new_start_raw = request.data.get("start_datetime")
        notes = request.data.get("notes")

        if new_start_raw:
            from rest_framework.fields import DateTimeField

            try:
                new_start = DateTimeField().to_internal_value(new_start_raw)
            except ValidationError:
                raise ValidationError({"start_datetime": "Formato de fecha/hora inválido."})
            if new_start <= timezone.now():
                raise ValidationError({"start_datetime": "No se puede reservar un horario en el pasado."})

            new_end = new_start + timedelta(minutes=appointment.doctor.appointment_duration_minutes)
            if not is_slot_available(appointment.doctor, new_start, new_end, exclude_appointment_id=appointment.pk):
                raise ValidationError({"start_datetime": "Ese horario ya no está disponible. Elegí otro."})
            if patient_has_conflicting_appointment(appointment.patient, new_start, exclude_pk=appointment.pk):
                raise ValidationError(
                    {"non_field_errors": ["Ya tenés otra cita agendada ese día. Solo se permite una cita por día."]}
                )
            appointment.start_datetime = new_start
            appointment.end_datetime = new_end

        if notes is not None:
            appointment.notes = notes

        try:
            with transaction.atomic():
                appointment.save()
        except IntegrityError:
            raise ValidationError({"start_datetime": "Ese horario se acaba de reservar. Elegí otro."})

        return Response(AppointmentSerializer(appointment).data)


class PatientCancelAppointmentView(APIView):
    """
    PATCH /api/patients/<document_number>/appointments/<pk>/cancel/ —
    el paciente cancela su propia cita usando su cédula, sin login.
    """

    permission_classes = [permissions.AllowAny]

    def patch(self, request, document_number, pk):
        appointment = _get_patient_appointment_or_404(document_number, pk)
        if appointment.status != Appointment.Status.CONFIRMADA:
            return Response({"detail": "Solo se pueden cancelar citas confirmadas."}, status=400)
        if appointment.start_datetime <= timezone.now():
            return Response({"detail": "No se puede cancelar una cita que ya pasó."}, status=400)
        appointment.status = Appointment.Status.CANCELADA
        appointment.save(update_fields=["status", "period"])
        return Response(AppointmentSerializer(appointment).data)


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
