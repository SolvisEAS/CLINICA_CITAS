from datetime import timedelta

from django.core.exceptions import ValidationError as DjangoValidationError
from django.db import IntegrityError, transaction
from django.utils import timezone
from rest_framework import serializers

from apps.doctors.models import Doctor
from apps.patients.models import DOCUMENT_NUMBER_VALIDATOR, Patient
from apps.patients.utils import normalize_document_number
from apps.schedules.services import is_slot_available

from .models import Appointment
from .services import can_patient_modify, patient_has_conflicting_appointment


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
        return obj.patient.name

    def get_doctor_name(self, obj):
        return str(obj.doctor)


class PublicAppointmentSerializer(serializers.ModelSerializer):
    """
    Lo que ve el paciente en el portal público, donde se identifica solo
    con su CI: lo mínimo para gestionar la consulta. A propósito no
    incluye su nombre ni el motivo, para que conocer una CI ajena no
    alcance para leer datos personales o de salud.
    """

    doctor_name = serializers.SerializerMethodField()
    doctor_specialty = serializers.CharField(source="doctor.specialty", read_only=True)
    can_modify = serializers.SerializerMethodField()

    class Meta:
        model = Appointment
        fields = [
            "id", "doctor", "doctor_name", "doctor_specialty",
            "start_datetime", "end_datetime", "status", "can_modify",
        ]

    def get_doctor_name(self, obj):
        return str(obj.doctor)

    def get_can_modify(self, obj):
        return can_patient_modify(obj)


class AppointmentCreateSerializer(serializers.Serializer):
    """
    Reserva pública, sin login. Si la cédula ya corresponde a un
    paciente, alcanza con la cédula: se usan sus datos guardados y no se
    sobrescriben (si no, cualquiera que conozca una cédula podría
    cambiarle el nombre o el teléfono a ese paciente). Si la cédula es
    nueva, se exigen nombre y teléfono; el correo es opcional. El
    backend vuelve a validar la disponibilidad y el límite de una cita
    por día — no confía en lo que haya mostrado el frontend.
    """

    document_number = serializers.CharField(max_length=20)
    name = serializers.CharField(max_length=200, required=False, allow_blank=True)
    phone = serializers.CharField(max_length=30, required=False, allow_blank=True)
    email = serializers.EmailField(required=False, allow_blank=True)
    doctor = serializers.PrimaryKeyRelatedField(queryset=Doctor.objects.filter(active=True))
    start_datetime = serializers.DateTimeField()
    notes = serializers.CharField(required=False, allow_blank=True, default="")

    def validate_document_number(self, value):
        digits = normalize_document_number(value)
        if not digits:
            raise serializers.ValidationError("Ingresá un número de documento válido.")
        try:
            DOCUMENT_NUMBER_VALIDATOR(digits)
        except DjangoValidationError as exc:
            raise serializers.ValidationError(exc.messages)
        return digits

    def validate(self, attrs):
        existing_patient = Patient.objects.filter(pk=attrs["document_number"]).first()
        if not existing_patient:
            missing = {
                field: "Este campo es obligatorio para un paciente nuevo."
                for field in ("name", "phone")
                if not attrs.get(field, "").strip()
            }
            if missing:
                raise serializers.ValidationError(missing)

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

        # "El agendamiento de los pacientes solo se puede hacer una vez
        # al día": chequeo rápido acá (buena UX); el chequeo definitivo,
        # con lock de fila, se repite en create() para cubrir el caso de
        # dos reservas casi simultáneas con la misma cédula.
        if existing_patient and patient_has_conflicting_appointment(existing_patient, start):
            raise serializers.ValidationError(
                {"non_field_errors": ["Ya tenés una cita agendada ese día. Solo se permite una cita por día."]}
            )
        return attrs

    def create(self, validated_data):
        from apps.notifications.services import schedule_appointment_notifications

        with transaction.atomic():
            # get_or_create: a un paciente existente no se le tocan los
            # datos guardados, aunque la request traiga otros.
            patient, _ = Patient.objects.get_or_create(
                document_number=validated_data["document_number"],
                defaults={
                    "name": validated_data.get("name", "").strip(),
                    "phone": validated_data.get("phone", "").strip(),
                    "email": validated_data.get("email", ""),
                },
            )
            # Bloquea la fila del paciente durante la transacción: si el
            # mismo paciente envía dos reservas casi al mismo tiempo
            # (doble clic, dos pestañas), la segunda espera a la primera
            # y vuelve a chequear el límite de una cita por día ya con
            # la que se acaba de crear.
            patient = Patient.objects.select_for_update().get(pk=patient.pk)
            if patient_has_conflicting_appointment(patient, validated_data["start_datetime"]):
                raise serializers.ValidationError(
                    {"non_field_errors": ["Ya tenés una cita agendada ese día. Solo se permite una cita por día."]}
                )
            try:
                appointment = Appointment.objects.create(
                    patient=patient,
                    doctor=validated_data["doctor"],
                    start_datetime=validated_data["start_datetime"],
                    end_datetime=validated_data["end_datetime"],
                    notes=validated_data.get("notes", ""),
                    status=Appointment.Status.CONFIRMADA,
                )
            except IntegrityError:
                # Última línea de defensa: dos pacientes distintos
                # pidieron el mismo horario casi simultáneamente y ambos
                # pasaron la validación de arriba. La base de datos
                # (ExclusionConstraint) es la que realmente decide acá.
                raise serializers.ValidationError(
                    {"start_datetime": "Ese horario se acaba de reservar. Elegí otro."}
                )
        schedule_appointment_notifications(appointment)
        return appointment
