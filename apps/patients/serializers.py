from django.db.models.functions import Coalesce
from rest_framework import serializers

from .models import Patient, TreatmentRecord


def treatment_history(patient):
    """
    Historial de un paciente, del más reciente al más viejo según su
    fecha: la de la consulta asociada o, si no tiene, la de carga.
    """
    return (
        TreatmentRecord.objects.filter(patient=patient)
        .select_related("doctor", "doctor__user", "appointment")
        .order_by(Coalesce("appointment__start_datetime", "created_at").desc(), "-created_at")
    )


class PatientSerializer(serializers.ModelSerializer):
    # Viene anotada en la consulta (ver patients.views._with_last_visit).
    last_visit = serializers.DateTimeField(read_only=True, default=None)

    class Meta:
        model = Patient
        fields = ["document_number", "name", "phone", "email", "created_at", "last_visit"]
        read_only_fields = ["document_number", "created_at"]


class TreatmentRecordSerializer(serializers.ModelSerializer):
    doctor_name = serializers.SerializerMethodField()
    date = serializers.SerializerMethodField()

    class Meta:
        model = TreatmentRecord
        fields = [
            "id", "patient", "doctor", "doctor_name", "appointment", "date",
            "reason", "description", "treatment", "created_at",
        ]
        read_only_fields = ["id", "patient", "doctor", "created_at"]

    def get_doctor_name(self, obj):
        return str(obj.doctor)

    def get_date(self, obj):
        """Fecha del registro: la de la consulta asociada o, si no tiene, la de carga."""
        moment = obj.appointment.start_datetime if obj.appointment else obj.created_at
        return serializers.DateTimeField().to_representation(moment)


class PatientDetailSerializer(serializers.ModelSerializer):
    """
    Ficha completa de un paciente para el doctor/admin: datos básicos +
    historial de turnos (con cualquier doctor) + historial de
    tratamientos, en una sola llamada.
    """

    last_visit = serializers.DateTimeField(read_only=True, default=None)
    appointments = serializers.SerializerMethodField()
    treatment_records = serializers.SerializerMethodField()

    class Meta:
        model = Patient
        fields = [
            "document_number", "name", "phone", "email", "created_at", "last_visit",
            "appointments", "treatment_records",
        ]

    def get_appointments(self, obj):
        # Import diferido: evita el import circular con
        # apps.appointments.serializers (que a su vez importa
        # apps.patients.models).
        from apps.appointments.serializers import AppointmentSerializer

        queryset = obj.appointments.select_related("doctor", "doctor__user").order_by("-start_datetime")
        return AppointmentSerializer(queryset, many=True).data

    def get_treatment_records(self, obj):
        return TreatmentRecordSerializer(treatment_history(obj), many=True).data
