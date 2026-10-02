from django.db.models import Max, Q
from django.db.models.functions import Coalesce
from django.utils import timezone
from rest_framework import generics, permissions
from rest_framework.exceptions import NotFound, PermissionDenied, ValidationError
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.appointments.models import Appointment
from apps.doctors.models import Doctor
from core.permissions import get_doctor_profile, is_admin

from .models import Patient
from .serializers import (
    PatientDetailSerializer,
    PatientSerializer,
    TreatmentRecordSerializer,
    treatment_history,
)
from .utils import normalize_document_number


class PatientExistsView(APIView):
    """
    GET /api/patients/<document_number>/exists/ — público, sin login.
    Chequeo mínimo para el flujo de reserva: le permite al frontend
    reconocer a un paciente ya cargado (por Django admin o por una
    reserva anterior) y precompletar su nombre, sin exponer teléfono
    ni correo. A diferencia de GET .../appointments/, no exige que el
    paciente tenga turnos previos.
    """

    permission_classes = [permissions.AllowAny]
    throttle_scope = "public_ci"

    def get(self, request, document_number):
        document_number = normalize_document_number(document_number)
        patient = Patient.objects.filter(pk=document_number).first()
        if not patient:
            return Response({"exists": False})
        return Response({"exists": True, "name": patient.name})


def _get_patient_or_404(document_number):
    document_number = normalize_document_number(document_number)
    patient = Patient.objects.filter(pk=document_number).first()
    if not patient:
        raise NotFound("Paciente no encontrado.")
    return patient


def _check_patient_access(user, patient, permission):
    """
    Un administrador (con el permiso) ve cualquier paciente; un doctor,
    solo los que tuvieron al menos un turno con él.
    """
    if not user.has_perm(permission):
        raise PermissionDenied("No autorizado.")
    if is_admin(user):
        return
    doctor = get_doctor_profile(user)
    if not doctor or not patient.appointments.filter(doctor=doctor).exists():
        raise PermissionDenied("Ese paciente no tiene turnos con vos.")


def _with_last_visit(queryset):
    """
    Anota `last_visit`: la última consulta atendida o, si nunca se marcó
    ninguna, el último turno ya pasado que no se canceló.
    """
    now = timezone.now()
    past = Q(appointments__start_datetime__lte=now)
    return queryset.annotate(
        last_visit=Coalesce(
            Max("appointments__start_datetime", filter=past & Q(appointments__status="ATENDIDA")),
            Max("appointments__start_datetime", filter=past & ~Q(appointments__status="CANCELADA")),
        )
    )


class DoctorPatientsView(generics.ListAPIView):
    """
    GET /api/patients/?search=<nombre o CI> — un doctor ve sus propios
    pacientes (los que tienen al menos una cita con él); un
    administrador, todos. Incluye la fecha de la última consulta.
    """

    serializer_class = PatientSerializer
    permission_classes = [permissions.IsAuthenticated]
    search_fields = ["name", "document_number"]

    def get_queryset(self):
        user = self.request.user
        if not user.has_perm("patients.view_patient"):
            raise PermissionDenied("No autorizado.")
        qs = Patient.objects.all()
        if not is_admin(user):
            doctor = get_doctor_profile(user)
            if not doctor:
                return Patient.objects.none()
            # Subconsulta y no un filtro por join: si no, la anotación de
            # last_visit solo vería los turnos con este doctor.
            qs = qs.filter(pk__in=Appointment.objects.filter(doctor=doctor).values("patient"))
        return _with_last_visit(qs).order_by("name")


class PatientTreatmentRecordsView(generics.ListCreateAPIView):
    """
    GET/POST /api/patients/<document_number>/treatments/ — historial de
    tratamientos de un paciente (de cualquier doctor: es compartido
    dentro de la clínica), con la misma regla de acceso que la ficha.
    """

    serializer_class = TreatmentRecordSerializer
    permission_classes = [permissions.IsAuthenticated]

    def get_patient(self):
        return _get_patient_or_404(self.kwargs["document_number"])

    def get_queryset(self):
        patient = self.get_patient()
        _check_patient_access(self.request.user, patient, "patients.view_treatmentrecord")
        return treatment_history(patient)

    def perform_create(self, serializer):
        user = self.request.user
        patient = self.get_patient()
        _check_patient_access(user, patient, "patients.add_treatmentrecord")

        appointment = serializer.validated_data.get("appointment")
        if appointment and appointment.patient_id != patient.pk:
            raise ValidationError({"appointment": "Ese turno no es de este paciente."})

        if is_admin(user):
            doctor_id = self.request.data.get("doctor")
            doctor = Doctor.objects.filter(pk=doctor_id).first() if doctor_id else None
            if not doctor:
                raise ValidationError({"doctor": "Indicá qué doctor firma el registro."})
        else:
            doctor = get_doctor_profile(user)
            if not doctor:
                raise PermissionDenied("Tu usuario no tiene un perfil de doctor asociado.")
        serializer.save(patient=patient, doctor=doctor)


class PatientDetailView(generics.RetrieveAPIView):
    """
    GET /api/patients/<document_number>/ — ficha completa de un paciente:
    datos básicos + turnos (con cualquier doctor) + historial de
    tratamientos, en una sola llamada. Un doctor solo puede ver
    pacientes que tuvieron al menos un turno con él.
    """

    serializer_class = PatientDetailSerializer
    permission_classes = [permissions.IsAuthenticated]

    def get_object(self):
        patient = _get_patient_or_404(self.kwargs["document_number"])
        _check_patient_access(self.request.user, patient, "patients.view_patient")
        return _with_last_visit(Patient.objects.filter(pk=patient.pk)).get()
