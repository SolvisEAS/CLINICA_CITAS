from django.contrib.auth import get_user_model
from django.contrib.auth.password_validation import validate_password
from rest_framework import serializers

User = get_user_model()


class RegisterSerializer(serializers.ModelSerializer):
    """
    Registro público con role=PACIENTE. Ya no lo usa el flujo de
    reserva (el paciente no tiene cuenta ni login — ver
    apps.patients.Patient), se deja por compatibilidad. Los usuarios
    con role=DOCTOR o role=ADMIN los crea un administrador desde
    /admin/ — no existe un endpoint público para auto-asignarse esos
    roles.
    """

    password = serializers.CharField(write_only=True, validators=[validate_password])

    class Meta:
        model = User
        fields = ["id", "username", "email", "password", "first_name", "last_name", "phone"]

    def create(self, validated_data):
        password = validated_data.pop("password")
        user = User(role=User.Role.PACIENTE, **validated_data)
        user.set_password(password)
        user.save()
        return user

    def to_representation(self, instance):
        data = super().to_representation(instance)
        data.pop("password", None)
        return data


class MeSerializer(serializers.ModelSerializer):
    class Meta:
        model = User
        fields = [
            "id", "username", "email", "first_name", "last_name",
            "phone", "role", "is_active", "date_joined",
        ]
        read_only_fields = ["role", "is_active", "date_joined"]


class AdminCreateUserSerializer(serializers.ModelSerializer):
    """
    Alta de usuarios DOCTOR o ADMIN, solo para un ADMIN (ver
    IsAdminRole en la vista). Reemplaza tener que pasar por /admin/
    de Django para dar de alta doctores desde el frontend desacoplado.
    Si el rol es DOCTOR, crea también su perfil en apps.doctors.Doctor
    en la misma operación (si no, quedaría un usuario DOCTOR sin
    perfil, y no podría recibir turnos).
    """

    password = serializers.CharField(write_only=True, validators=[validate_password])
    specialty = serializers.CharField(required=False, allow_blank=True, write_only=True, default="")
    appointment_duration_minutes = serializers.IntegerField(
        required=False, write_only=True, default=30, min_value=5
    )

    class Meta:
        model = User
        fields = [
            "id", "username", "email", "password", "first_name", "last_name",
            "phone", "role", "specialty", "appointment_duration_minutes",
        ]

    def validate_role(self, value):
        if value not in (User.Role.DOCTOR, User.Role.ADMIN):
            raise serializers.ValidationError("Acá solo se pueden crear usuarios DOCTOR o ADMIN.")
        return value

    def create(self, validated_data):
        from apps.doctors.models import Doctor

        password = validated_data.pop("password")
        specialty = validated_data.pop("specialty", "")
        appointment_duration_minutes = validated_data.pop("appointment_duration_minutes", 30)
        user = User(**validated_data)
        user.set_password(password)
        user.save()
        if user.role == User.Role.DOCTOR:
            Doctor.objects.create(
                user=user,
                specialty=specialty,
                appointment_duration_minutes=appointment_duration_minutes,
            )
        return user

    def to_representation(self, instance):
        data = super().to_representation(instance)
        data.pop("password", None)
        return data


class AdminUserListSerializer(serializers.ModelSerializer):
    class Meta:
        model = User
        fields = [
            "id", "username", "email", "first_name", "last_name",
            "phone", "role", "is_active", "date_joined",
        ]


class SetPasswordSerializer(serializers.Serializer):
    new_password = serializers.CharField(write_only=True, validators=[validate_password])
