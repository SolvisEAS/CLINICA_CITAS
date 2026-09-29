from django.contrib.auth.models import AbstractUser
from django.db import models


class User(AbstractUser):
    """
    Usuario personalizado desde el día 1 (igual que en SOLVIS_CRM):
    cambiar AUTH_USER_MODEL después de la primera migración es muy
    costoso en Django, así que se resuelve ahora.

    role determina qué puede hacer cada usuario:
      - PACIENTE: rol heredado del diseño original; ya no lo usa el
        flujo de reserva (decisión de negocio: el paciente no tiene
        cuenta ni login — ver apps.patients.Patient, identificado por
        cédula). Se deja por compatibilidad, pero ningún endpoint lo
        exige hoy.
      - DOCTOR: gestiona su horario, su agenda, sus pacientes y el
        historial de tratamientos. Lo crea un ADMIN y siempre tiene
        además un perfil en apps.doctors.Doctor.
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
