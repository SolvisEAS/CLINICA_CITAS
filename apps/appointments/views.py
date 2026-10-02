from datetime import date as date_cls, timedelta

from django.db import IntegrityError, transaction
from django.utils import timezone
from rest_framework import generics, permissions, status
from rest_framework.exceptions import NotFound, PermissionDenied, ValidationError
from rest_framework.fields import DateTimeField
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.doctors.models import Doctor
from apps.notifications.services import reschedule_appointment_notifications
from apps.patients.models import Patient
from apps.patients.utils import normalize_document_number
from apps.schedules.services import is_slot_available
from core.permissions import get_doctor_profile, is_admin

from .models import Appointment
from .serializers import AppointmentCreateSerializer, AppointmentSerializer, PublicAppointmentSerializer
from .services import can_patient_modify, patient_has_conflicting_appointment

ONE_PER_DAY_ERROR = "Ya tenés otra cita agendada ese día. Solo se permite una cita por día."
NOT_MODIFIABLE_ERROR = (
    "Esta consulta ya no se puede modificar: solo se pueden modificar consultas pendientes "
    "cuya fecha y hora todavía no llegaron."
)


class BookAppointmentView(generics.CreateAPIView):
    """
    POST /api/appointments/ — cualquiera reserva un turno con su cédula
    (y sus datos, si es la primera vez). No requiere cuenta ni login.
    """

    serializer_class = AppointmentCreateSerializer
    permission_classes = [permissions.AllowAny]
    throttle_scope = "public_ci"

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
    GET /api/patients/<document_number>/appointments/ — "Mis consultas"
    del portal público: el paciente, identificado solo con su cédula, ve
    sus consultas futuras pendientes (no las pasadas, atendidas ni
    canceladas), con los datos mínimos para gestionarlas.
    """

    serializer_class = PublicAppointmentSerializer
    permission_classes = [permissions.AllowAny]
    throttle_scope = "public_ci"

    def get_queryset(self):
        patient = _get_patient_or_404(self.kwargs["document_number"])
        return (
            Appointment.objects.filter(
                patient=patient,
                status=Appointment.Status.CONFIRMADA,
                start_datetime__gt=timezone.now(),
            )
            .select_related("doctor", "doctor__user")
            .order_by("start_datetime")
        )


class PatientRescheduleAppointmentView(APIView):
    """
    PATCH /api/patients/<document_number>/appointments/<pk>/ — el
    paciente modifica su propia cita con su cédula, sin login. Acepta
    `start_datetime`, `doctor` (para cambiar de doctor; exige también un
    horario nuevo) y `notes`. Solo mientras la cita sea futura y esté
    pendiente; el horario anterior queda libre al guardar.
    """

    permission_classes = [permissions.AllowAny]
    throttle_scope = "public_ci"

    def patch(self, request, document_number, pk):
        appointment = _get_patient_appointment_or_404(document_number, pk)
        if not can_patient_modify(appointment):
            return Response({"detail": NOT_MODIFIABLE_ERROR}, status=400)

        doctor = appointment.doctor
        doctor_id = request.data.get("doctor")
        if doctor_id not in (None, ""):
            doctor = Doctor.objects.filter(pk=doctor_id, active=True).first()
            if not doctor:
                raise ValidationError({"doctor": "Doctor no encontrado o inactivo."})

        new_start_raw = request.data.get("start_datetime")
        if doctor.pk != appointment.doctor_id and not new_start_raw:
            raise ValidationError({"start_datetime": "Al cambiar de doctor elegí también un horario nuevo."})

        schedule_changed = False
        if new_start_raw:
            try:
                new_start = DateTimeField().to_internal_value(new_start_raw)
            except ValidationError:
                raise ValidationError({"start_datetime": "Formato de fecha/hora inválido."})
            if new_start <= timezone.now():
                raise ValidationError({"start_datetime": "No se puede reservar un horario en el pasado."})
            new_end = new_start + timedelta(minutes=doctor.appointment_duration_minutes)
            if not is_slot_available(doctor, new_start, new_end, exclude_appointment_id=appointment.pk):
                raise ValidationError({"start_datetime": "Ese horario ya no está disponible. Elegí otro."})
            appointment.doctor = doctor
            appointment.start_datetime = new_start
            appointment.end_datetime = new_end
            schedule_changed = True

        notes = request.data.get("notes")
        if notes is not None:
            appointment.notes = notes

        try:
            with transaction.atomic():
                # Igual que al reservar: el lock evita que dos cambios casi
                # simultáneos de la misma cédula esquiven "una cita por día".
                patient = Patient.objects.select_for_update().get(pk=appointment.patient_id)
                if schedule_changed and patient_has_conflicting_appointment(
                    patient, appointment.start_datetime, exclude_pk=appointment.pk
                ):
                    raise ValidationError({"non_field_errors": [ONE_PER_DAY_ERROR]})
                appointment.save()
        except IntegrityError:
            raise ValidationError({"start_datetime": "Ese horario se acaba de reservar. Elegí otro."})

        if schedule_changed:
            reschedule_appointment_notifications(appointment)
        return Response(PublicAppointmentSerializer(appointment).data)


class PatientCancelAppointmentView(APIView):
    """
    PATCH /api/patients/<document_number>/appointments/<pk>/cancel/ —
    el paciente cancela su propia cita usando su cédula, sin login.
    """

    permission_classes = [permissions.AllowAny]
    throttle_scope = "public_ci"

    def patch(self, request, document_number, pk):
        appointment = _get_patient_appointment_or_404(document_number, pk)
        if not can_patient_modify(appointment):
            return Response({"detail": NOT_MODIFIABLE_ERROR}, status=400)
        appointment.status = Appointment.Status.CANCELADA
        appointment.save(update_fields=["status", "period"])
        return Response(PublicAppointmentSerializer(appointment).data)


def _resolve_agenda_doctor(request):
    """
    De qué doctor se pide la agenda: un administrador puede indicar
    ?doctor=<id>; un doctor siempre ve la suya.
    """
    user = request.user
    if not user.has_perm("appointments.view_appointment"):
        raise PermissionDenied("No autorizado.")
    doctor_param = request.query_params.get("doctor")
    if doctor_param and is_admin(user):
        doctor = Doctor.objects.filter(pk=doctor_param).first()
        if not doctor:
            raise NotFound("Doctor no encontrado.")
        return doctor
    doctor = get_doctor_profile(user)
    if not doctor:
        raise ValidationError(
            {"doctor": "Indicá ?doctor=<id>." if is_admin(user) else "Tu usuario no tiene un perfil de doctor asociado."}
        )
    return doctor


class DoctorAgendaView(APIView):
    """
    GET /api/appointments/agenda/?date=YYYY-MM-DD — agenda de un día
    (por defecto, hoy) del doctor logueado.
    """

    permission_classes = [permissions.IsAuthenticated]

    def get(self, request):
        doctor = _resolve_agenda_doctor(request)

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


class UpcomingAppointmentsView(generics.ListAPIView):
    """
    GET /api/appointments/upcoming/ — próximas consultas pendientes del
    doctor logueado, de ahora en adelante y en orden cronológico.
    """

    serializer_class = AppointmentSerializer
    permission_classes = [permissions.IsAuthenticated]

    def get_queryset(self):
        doctor = _resolve_agenda_doctor(self.request)
        return (
            Appointment.objects.filter(
                doctor=doctor,
                status=Appointment.Status.CONFIRMADA,
                start_datetime__gte=timezone.now(),
            )
            .select_related("patient", "doctor", "doctor__user")
            .order_by("start_datetime")
        )


class UpdateAppointmentStatusView(APIView):
    """
    PATCH /api/appointments/{id}/status/ con {"status": "ATENDIDA"} —
    el doctor dueño de la cita (o un administrador) la marca como
    atendida, no asistió, o cancelada.
    """

    permission_classes = [permissions.IsAuthenticated]

    def patch(self, request, pk):
        appointment = Appointment.objects.select_related("doctor", "doctor__user").filter(pk=pk).first()
        if not appointment:
            return Response({"detail": "Cita no encontrada."}, status=404)

        user = request.user
        is_owner_doctor = appointment.doctor.user_id == user.id
        if not (user.has_perm("appointments.change_appointment") and (is_owner_doctor or is_admin(user))):
            return Response({"detail": "No autorizado."}, status=403)

        new_status = request.data.get("status")
        valid_statuses = [Appointment.Status.ATENDIDA, Appointment.Status.NO_ASISTIO, Appointment.Status.CANCELADA]
        if new_status not in valid_statuses:
            raise ValidationError({"status": f"Debe ser uno de: {', '.join(valid_statuses)}."})

        appointment.status = new_status
        appointment.save(update_fields=["status", "period"])
        return Response(AppointmentSerializer(appointment).data)
