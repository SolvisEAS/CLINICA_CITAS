from django.contrib.auth import get_user_model
from django.contrib.auth.password_validation import validate_password
from rest_framework import serializers

User = get_user_model()


class RegisterSerializer(serializers.ModelSerializer):
    """
    Registro público de pacientes. Los usuarios con role=DOCTOR o
    role=ADMIN los crea un administrador desde /admin/ — no existe un
    endpoint público para auto-asignarse esos roles.
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
