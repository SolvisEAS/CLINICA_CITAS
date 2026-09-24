from django.conf import settings
from django.contrib.postgres.constraints import ExclusionConstraint
from django.contrib.postgres.fields import DateTimeRangeField
from django.db import models
from django.db.models import Q

from apps.doctors.models import Doctor


class Appointment(models.Model):
    """
    Punto 13 del documento base — "la regla crítica contra doble
    reserva" — se resuelve acá con un ExclusionConstraint de
    PostgreSQL: la base de datos, no solo el código de la aplicación,
    impide físicamente que existan dos citas activas del mismo doctor
    con horarios que se solapen. Esto cubre el caso de dos pacientes
    reservando "casi al mismo tiempo" mencionado en el documento.

    El campo `period` es un rango calculado a partir de
    start_datetime/end_datetime (se mantiene sincronizado en save())
    únicamente para que PostgreSQL pueda aplicar esa restricción; toda
    la API sigue trabajando con start_datetime/end_datetime, tal como
    pide el esquema del documento.
    """

    class Status(models.TextChoices):
        CONFIRMADA = "CONFIRMADA", "Confirmada"
        ATENDIDA = "ATENDIDA", "Atendida"
        CANCELADA = "CANCELADA", "Cancelada"
        NO_ASISTIO = "NO_ASISTIO", "No asistió"

    patient = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="appointments_as_patient"
    )
    doctor = models.ForeignKey(Doctor, on_delete=models.CASCADE, related_name="appointments")
    start_datetime = models.DateTimeField()
    end_datetime = models.DateTimeField()
    period = DateTimeRangeField(editable=False)
    status = models.CharField(max_length=20, choices=Status.choices, default=Status.CONFIRMADA)
    notes = models.TextField("Notas", blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["start_datetime"]
        constraints = [
            models.CheckConstraint(
                check=Q(end_datetime__gt=models.F("start_datetime")),
                name="appointment_end_after_start",
            ),
            ExclusionConstraint(
                name="no_overlapping_active_appointments_per_doctor",
                expressions=[
                    ("doctor", "="),
                    ("period", "&&"),
                ],
                # Solo las citas activas (confirmadas o ya atendidas)
                # bloquean el horario; una cancelada o "no asistió" no.
                condition=Q(status__in=["CONFIRMADA", "ATENDIDA"]),
            ),
        ]

    def save(self, *args, **kwargs):
        self.period = (self.start_datetime, self.end_datetime)
        super().save(*args, **kwargs)

    def __str__(self):
        return f"{self.patient} con {self.doctor} · {self.start_datetime}"
