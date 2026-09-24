from datetime import timedelta

from django.db import IntegrityError, transaction
from django.utils import timezone
from rest_framework import serializers

from apps.doctors.models import Doctor
from apps.schedules.services import is_slot_available

from .models import Appointment


class AppointmentSerializer(serializers.ModelSerializer):
    patient_name = serializers.SerializerMethodField()
    doctor_name = serializers.SerializerMethodField()

    class Meta:
        model = Appointment
        fields = [
            "id", "patient", "patient_name", "doctor", "doctor_name",
            "start_datetime", "end_datetime", "status", "notes", "created_at",
        ]
        read_only_fields = ["patient", "end_datetime", "status", "created_at"]

    def get_patient_name(self, obj):
        return obj.patient.get_full_name() or obj.patient.username

    def get_doctor_name(self, obj):
        return str(obj.doctor)


class AppointmentCreateSerializer(serializers.Serializer):
    """
    Punto 4 y 18 del documento: el paciente elige doctor + horario, y el
    backend vuelve a validar la disponibilidad (no confía en lo que
    haya mostrado el frontend) antes de confirmar.
    """

    doctor = serializers.PrimaryKeyRelatedField(queryset=Doctor.objects.filter(active=True))
    start_datetime = serializers.DateTimeField()
    notes = serializers.CharField(required=False, allow_blank=True, default="")

    def validate(self, attrs):
        doctor = attrs["doctor"]
        start = attrs["start_datetime"]
        if start <= timezone.now():
            raise serializers.ValidationError({"start_datetime": "No se puede reservar un horario en el pasado."})
        end = start + timedelta(minutes=doctor.appointment_duration_minutes)
        if not is_slot_available(doctor, start, end):
            raise serializers.ValidationError(
                {"start_datetime": "Ese horario ya no está disponible. Elegí otro."}
            )
        attrs["end_datetime"] = end
        return attrs

    def create(self, validated_data):
        from apps.notifications.services import schedule_appointment_notifications

        request = self.context["request"]
        try:
            with transaction.atomic():
                appointment = Appointment.objects.create(
                    patient=request.user,
                    doctor=validated_data["doctor"],
                    start_datetime=validated_data["start_datetime"],
                    end_datetime=validated_data["end_datetime"],
                    notes=validated_data.get("notes", ""),
                    status=Appointment.Status.CONFIRMADA,
                )
        except IntegrityError:
            # Última línea de defensa: dos pacientes pidieron el mismo
            # horario casi simultáneamente y ambos pasaron la validación
            # de arriba. La base de datos (ExclusionConstraint) es la que
            # realmente decide acá, tal como pide el punto 13 del documento.
            raise serializers.ValidationError(
                {"start_datetime": "Ese horario se acaba de reservar. Elegí otro."}
            )
        schedule_appointment_notifications(appointment)
        return appointment
