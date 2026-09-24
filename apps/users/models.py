from django.contrib.auth.models import AbstractUser
from django.db import models


class User(AbstractUser):
    """
    Usuario personalizado desde el día 1 (igual que en SOLVIS_CRM):
    cambiar AUTH_USER_MODEL después de la primera migración es muy
    costoso en Django, así que se resuelve ahora.

    role determina qué puede hacer cada usuario:
      - PACIENTE: se auto-registra, reserva y gestiona sus propias citas.
      - DOCTOR: gestiona su horario y su agenda. Lo crea un ADMIN y
        siempre tiene además un perfil en apps.doctors.Doctor.
      - ADMIN: gestiona doctores, usuarios y configuración general.
    """

    class Role(models.TextChoices):
        PACIENTE = "PACIENTE", "Paciente"
        DOCTOR = "DOCTOR", "Doctor"
        ADMIN = "ADMIN", "Administrador"

    role = models.CharField(max_length=20, choices=Role.choices, default=Role.PACIENTE)
    phone = models.CharField(max_length=30, blank=True)

    def __str__(self):
        return self.get_full_name() or self.username
