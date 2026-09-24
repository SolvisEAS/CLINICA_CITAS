from django.conf import settings
from django.db import models


class Doctor(models.Model):
    """
    Perfil de doctor. Se crea vinculado a un User con role=DOCTOR
    (lo hace un ADMIN desde /admin/).

    appointment_duration_minutes fija la duración de TODOS los turnos
    de este doctor (decisión tomada para el MVP: duración fija por
    doctor, no variable por tipo de tratamiento).
    """

    user = models.OneToOneField(
        settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="doctor_profile"
    )
    specialty = models.CharField("Especialidad", max_length=150, blank=True)
    appointment_duration_minutes = models.PositiveIntegerField(
        "Duración de cada turno (minutos)", default=30
    )
    active = models.BooleanField("Activo", default=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["user__first_name", "user__last_name"]

    def __str__(self):
        return self.user.get_full_name() or self.user.username
