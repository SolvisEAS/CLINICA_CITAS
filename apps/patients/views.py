from rest_framework import generics, permissions
from rest_framework.exceptions import NotFound, PermissionDenied

from apps.doctors.models import Doctor

from .models import Patient, TreatmentRecord
from .serializers import PatientDetailSerializer, PatientSerializer, TreatmentRecordSerializer
from .utils import normalize_document_number


def _get_patient_or_404(document_number):
    document_number = normalize_document_number(document_number)
    patient = Patient.objects.filter(pk=document_number).first()
    if not patient:
        raise NotFound("Paciente no encontrado.")
    return patient


def _get_requesting_doctor_or_none(user):
    if user.role != "DOCTOR":
        return None
    return Doctor.objects.filter(user=user).first()


class DoctorPatientsView(generics.ListAPIView):
    """
    GET /api/patients/ — un DOCTOR ve la lista de sus propios pacientes
    (los que tienen al menos una cita con él); un ADMIN ve todos.
    """

    serializer_class = PatientSerializer
    permission_classes = [permissions.IsAuthenticated]

    def get_queryset(self):
        user = self.request.user
        if user.role == "ADMIN":
            return Patient.objects.all().order_by("name")
        if user.role == "DOCTOR":
            doctor = _get_requesting_doctor_or_none(user)
            if not doctor:
                return Patient.objects.none()
            return Patient.objects.filter(appointments__doctor=doctor).distinct().order_by("name")
        raise PermissionDenied("No autorizado.")


class PatientTreatmentRecordsView(generics.ListCreateAPIView):
    """
    GET/POST /api/patients/<document_number>/treatments/ — historial de
    tratamientos de un paciente. Solo lo gestionan doctores y
    administradores (el paciente no tiene cuenta para verlo acá).
    """

    serializer_class = TreatmentRecordSerializer
    permission_classes = [permissions.IsAuthenticated]

    def get_patient(self):
        return _get_patient_or_404(self.kwargs["document_number"])

    def get_queryset(self):
        if self.request.user.role not in ("DOCTOR", "ADMIN"):
            raise PermissionDenied("No autorizado.")
        return (
            TreatmentRecord.objects.filter(patient=self.get_patient())
            .select_related("doctor", "doctor__user")
        )

    def perform_create(self, serializer):
        user = self.request.user
        if user.role == "DOCTOR":
            doctor = _get_requesting_doctor_or_none(user)
            if not doctor:
                raise PermissionDenied("Tu usuario no tiene un perfil de doctor asociado.")
        elif user.role == "ADMIN":
            doctor_id = self.request.data.get("doctor")
            doctor = Doctor.objects.filter(pk=doctor_id).first() if doctor_id else None
            if not doctor:
                raise PermissionDenied("Los administradores deben indicar 'doctor' en el body.")
        else:
            raise PermissionDenied("No autorizado.")
        serializer.save(patient=self.get_patient(), doctor=doctor)


class PatientDetailView(generics.RetrieveAPIView):
    """
    GET /api/patients/<document_number>/ — ficha completa de un
    paciente para el doctor/admin: datos básicos + historial de turnos
    (con cualquier doctor) + historial de tratamientos, en una sola
    llamada. Un DOCTOR solo puede ver pacientes que tuvieron al menos
    un turno con él; un ADMIN ve cualquiera.
    """

    serializer_class = PatientDetailSerializer
    permission_classes = [permissions.IsAuthenticated]

    def get_object(self):
        patient = _get_patient_or_404(self.kwargs["document_number"])
        user = self.request.user
        if user.role == "ADMIN":
            return patient
        if user.role == "DOCTOR":
            doctor = _get_requesting_doctor_or_none(user)
            if not doctor or not patient.appointments.filter(doctor=doctor).exists():
                raise PermissionDenied("Ese paciente no tiene turnos con vos.")
            return patient
        raise PermissionDenied("No autorizado.")
