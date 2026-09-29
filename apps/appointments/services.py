"""
Reglas de negocio sobre citas que no son puramente de disponibilidad
de horario (eso vive en apps.schedules.services).

Acá: el límite de "una cita por paciente por día", pedido para el
agendamiento sin login — un mismo paciente (identificado por su
cédula) no puede tener más de una cita activa el mismo día,
sin importar el doctor.
"""
from django.utils import timezone

from .models import Appointment


def patient_has_conflicting_appointment(patient, start_datetime, exclude_pk=None):
    """
    True si `patient` ya tiene una cita activa (CONFIRMADA o ATENDIDA)
    el mismo día (hora local) que `start_datetime`.
    """
    local_date = timezone.localtime(start_datetime).date()
    qs = Appointment.objects.filter(
        patient=patient,
        status__in=[Appointment.Status.CONFIRMADA, Appointment.Status.ATENDIDA],
        start_datetime__date=local_date,
    )
    if exclude_pk:
        qs = qs.exclude(pk=exclude_pk)
    return qs.exists()
