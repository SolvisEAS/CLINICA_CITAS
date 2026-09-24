from django.db import models

from apps.doctors.models import Doctor


class WeeklySchedule(models.Model):
    """Horario semanal habitual de un doctor (punto 6 del documento base)."""

    class Weekday(models.IntegerChoices):
        LUNES = 0, "Lunes"
        MARTES = 1, "Martes"
        MIERCOLES = 2, "Miércoles"
        JUEVES = 3, "Jueves"
        VIERNES = 4, "Viernes"
        SABADO = 5, "Sábado"
        DOMINGO = 6, "Domingo"

    doctor = models.ForeignKey(Doctor, on_delete=models.CASCADE, related_name="weekly_schedules")
    weekday = models.IntegerField("Día de la semana", choices=Weekday.choices)
    start_time = models.TimeField("Hora de inicio")
    end_time = models.TimeField("Hora de fin")
    active = models.BooleanField("Activo", default=True)

    class Meta:
        ordering = ["weekday", "start_time"]
        constraints = [
            models.CheckConstraint(
                check=models.Q(end_time__gt=models.F("start_time")),
                name="weekly_schedule_end_after_start",
            ),
        ]

    def __str__(self):
        return f"{self.doctor} · {self.get_weekday_display()} {self.start_time}-{self.end_time}"


class AvailabilityException(models.Model):
    """
    Bloqueo puntual de disponibilidad: un día concreto, una tarde, unas
    vacaciones, etc. (punto 6 del documento base). Para el MVP el único
    tipo soportado es BLOQUEO (quitar disponibilidad); el campo `type`
    queda listo para agregar más adelante, por ejemplo disponibilidad
    extra puntual, sin tener que rehacer el modelo.
    """

    class Type(models.TextChoices):
        BLOQUEO = "BLOQUEO", "Bloqueo / ausencia"

    doctor = models.ForeignKey(Doctor, on_delete=models.CASCADE, related_name="availability_exceptions")
    start_datetime = models.DateTimeField("Desde")
    end_datetime = models.DateTimeField("Hasta")
    type = models.CharField(max_length=20, choices=Type.choices, default=Type.BLOQUEO)
    reason = models.CharField("Motivo", max_length=255, blank=True)

    class Meta:
        ordering = ["start_datetime"]
        constraints = [
            models.CheckConstraint(
                check=models.Q(end_datetime__gt=models.F("start_datetime")),
                name="availability_exception_end_after_start",
            ),
        ]

    def __str__(self):
        return f"{self.doctor} · {self.start_datetime} a {self.end_datetime}"
