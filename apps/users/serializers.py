from django.contrib.auth import get_user_model
from django.contrib.auth.password_validation import validate_password
from django.db import transaction
from rest_framework import serializers

from apps.doctors.models import Doctor
from core.permissions import get_doctor_profile, is_admin

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
    # Lo que el frontend necesita para armar cada experiencia: si
    # administra (permiso de Django, incluye al superusuario) y cuál es
    # su perfil de doctor, si tiene.
    is_admin = serializers.SerializerMethodField()
    doctor_id = serializers.SerializerMethodField()

    class Meta:
        model = User
        fields = [
            "id", "username", "email", "first_name", "last_name",
            "phone", "role", "is_active", "date_joined", "is_admin", "doctor_id",
        ]
        read_only_fields = ["role", "is_active", "date_joined"]

    def get_is_admin(self, obj):
        return is_admin(obj)

    def get_doctor_id(self, obj):
        doctor = get_doctor_profile(obj)
        return doctor.id if doctor else None


def _sync_doctor_profile(user, specialty=None, duration=None):
    """
    Un usuario Doctor siempre tiene su perfil de Doctor, y ese perfil
    recibe turnos (active) solo mientras el usuario esté activo. Si deja
    de ser Doctor, su perfil se conserva (turnos e historial) pero deja
    de aparecer para reservar.
    """
    # Por el accessor y no con una consulta aparte: así se actualiza el mismo
    # objeto que quedó cacheado en `user` y la respuesta muestra lo guardado.
    try:
        doctor = user.doctor_profile
    except Doctor.DoesNotExist:
        doctor = None
    if user.role != User.Role.DOCTOR:
        if doctor and doctor.active:
            doctor.active = False
            doctor.save(update_fields=["active"])
        return
    if doctor is None:
        doctor = Doctor(user=user)
    if specialty is not None:
        doctor.specialty = specialty
    if duration is not None:
        doctor.appointment_duration_minutes = duration
    doctor.active = user.is_active
    doctor.save()


class AdminUserSerializer(serializers.ModelSerializer):
    """Usuario Doctor/Administrador tal como lo ve el panel de administración."""

    is_admin = serializers.SerializerMethodField()
    doctor = serializers.SerializerMethodField()

    class Meta:
        model = User
        fields = [
            "id", "username", "email", "first_name", "last_name", "phone", "role",
            "is_active", "is_superuser", "is_admin", "date_joined", "last_login", "doctor",
        ]

    def get_is_admin(self, obj):
        return is_admin(obj)

    def get_doctor(self, obj):
        doctor = getattr(obj, "doctor_profile", None)
        if not doctor:
            return None
        return {
            "id": doctor.id,
            "specialty": doctor.specialty,
            "appointment_duration_minutes": doctor.appointment_duration_minutes,
            "active": doctor.active,
        }


class AdminUserWriteSerializer(serializers.ModelSerializer):
    """
    Alta y edición de usuarios Doctor/Administrador desde el panel de
    administración. Al crear un Doctor crea también su perfil de Doctor,
    y el grupo de permisos lo asigna el rol (ver users.signals). La
    contraseña solo se fija al crear; después se cambia con
    set-password. Desactivar no borra nada: el usuario deja de poder
    entrar y deja de recibir turnos, pero conserva su historial.
    """

    password = serializers.CharField(
        write_only=True, required=False, validators=[validate_password], style={"input_type": "password"}
    )
    password_confirm = serializers.CharField(write_only=True, required=False, style={"input_type": "password"})
    specialty = serializers.CharField(required=False, allow_blank=True, write_only=True, max_length=150)
    appointment_duration_minutes = serializers.IntegerField(
        required=False, write_only=True, min_value=5, max_value=240
    )

    class Meta:
        model = User
        fields = [
            "username", "email", "first_name", "last_name", "phone", "role", "is_active",
            "password", "password_confirm", "specialty", "appointment_duration_minutes",
        ]
        extra_kwargs = {
            "first_name": {"required": True, "allow_blank": False},
            "last_name": {"required": True, "allow_blank": False},
            "role": {"required": True},
        }

    def validate_role(self, value):
        if value not in (User.Role.DOCTOR, User.Role.ADMIN):
            raise serializers.ValidationError("El rol tiene que ser Doctor o Administrador.")
        return value

    def validate(self, attrs):
        creating = self.instance is None
        if creating:
            if not attrs.get("password"):
                raise serializers.ValidationError({"password": "Este campo es obligatorio."})
            if attrs["password"] != attrs.get("password_confirm"):
                raise serializers.ValidationError({"password_confirm": "Las contraseñas no coinciden."})
            return attrs

        if "password" in attrs:
            raise serializers.ValidationError({"password": "Para cambiar la contraseña usá «Restablecer contraseña»."})

        requester = self.context["request"].user
        if self.instance.is_superuser and not requester.is_superuser:
            raise serializers.ValidationError("Solo un superusuario puede modificar a otro superusuario.")
        if self.instance.pk == requester.pk:
            # Evita que un administrador se deje a sí mismo sin acceso.
            if attrs.get("is_active") is False:
                raise serializers.ValidationError({"is_active": "No podés desactivar tu propio usuario."})
            if attrs.get("role", User.Role.ADMIN) != User.Role.ADMIN and not requester.is_superuser:
                raise serializers.ValidationError({"role": "No podés quitarte el rol de administrador."})
        return attrs

    @transaction.atomic
    def create(self, validated_data):
        password = validated_data.pop("password")
        validated_data.pop("password_confirm", None)
        specialty = validated_data.pop("specialty", "")
        duration = validated_data.pop("appointment_duration_minutes", 30)
        user = User(**validated_data)
        user.set_password(password)
        user.save()
        _sync_doctor_profile(user, specialty, duration)
        return user

    @transaction.atomic
    def update(self, instance, validated_data):
        validated_data.pop("password_confirm", None)
        specialty = validated_data.pop("specialty", None)
        duration = validated_data.pop("appointment_duration_minutes", None)
        for field, value in validated_data.items():
            setattr(instance, field, value)
        instance.save()
        _sync_doctor_profile(instance, specialty, duration)
        return instance

    def to_representation(self, instance):
        return AdminUserSerializer(instance, context=self.context).data


class SetPasswordSerializer(serializers.Serializer):
    new_password = serializers.CharField(write_only=True, validators=[validate_password])
    new_password_confirm = serializers.CharField(write_only=True)

    def validate(self, attrs):
        if attrs["new_password"] != attrs["new_password_confirm"]:
            raise serializers.ValidationError({"new_password_confirm": "Las contraseñas no coinciden."})
        return attrs
