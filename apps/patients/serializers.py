from rest_framework import serializers

from .models import Patient, TreatmentRecord


class PatientSerializer(serializers.ModelSerializer):
    class Meta:
        model = Patient
        fields = ["document_number", "name", "phone", "email", "created_at"]
        read_only_fields = ["document_number", "created_at"]


class TreatmentRecordSerializer(serializers.ModelSerializer):
    doctor_name = serializers.SerializerMethodField()

    class Meta:
        model = TreatmentRecord
        fields = [
            "id", "patient", "doctor", "doctor_name", "appointment",
            "reason", "description", "treatment", "created_at",
        ]
        read_only_fields = ["id", "patient", "doctor", "created_at"]

    def get_doctor_name(self, obj):
        return str(obj.doctor)


class PatientDetailSerializer(serializers.ModelSerializer):
    """
    Ficha completa de un paciente para el doctor/admin: datos básicos +
    historial de turnos (con cualquier doctor) + historial de
    tratamientos, en una sola llamada.
    """

    appointments = serializers.SerializerMethodField()
    treatment_records = TreatmentRecordSerializer(many=True, read_only=True)

    class Meta:
        model = Patient
        fields = [
            "document_number", "name", "phone", "email", "created_at",
            "appointments", "treatment_records",
        ]

    def get_appointments(self, obj):
        # Import diferido: evita el import circular con
        # apps.appointments.serializers (que a su vez importa
        # apps.patients.models).
        from apps.appointments.serializers import AppointmentSerializer

        queryset = obj.appointments.select_related("doctor", "doctor__user").order_by("-start_datetime")
        return AppointmentSerializer(queryset, many=True).data
