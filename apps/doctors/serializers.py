from rest_framework import serializers

from .models import Doctor


class DoctorSerializer(serializers.ModelSerializer):
    full_name = serializers.SerializerMethodField()
    email = serializers.EmailField(source="user.email", read_only=True)

    class Meta:
        model = Doctor
        fields = [
            "id", "user", "full_name", "email", "specialty",
            "appointment_duration_minutes", "active", "created_at",
        ]
        read_only_fields = ["created_at"]

    def get_full_name(self, obj):
        return obj.user.get_full_name() or obj.user.username

    def validate_user(self, user):
        if user.role != user.Role.DOCTOR:
            raise serializers.ValidationError(
                "El usuario seleccionado no tiene role=DOCTOR. Cambiá su rol primero desde /admin/."
            )
        return user
