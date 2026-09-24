"""
Cálculo de disponibilidad (punto 6 del documento base).

La disponibilidad de un doctor en una fecha dada se calcula a partir de
tres fuentes, exactamente como pide el documento:

  1. Su horario semanal habitual (WeeklySchedule) para ese día.
  2. Sus bloqueos/excepciones puntuales (AvailabilityException).
  3. Sus citas ya reservadas (Appointment) en estado activo.

Esta misma función la usan tanto el endpoint de consulta de
disponibilidad (para mostrarle horarios al paciente) como la reserva
de una cita (para revalidar justo antes de confirmar — punto 13 del
documento: "el backend vuelve a validar la disponibilidad").
"""
from datetime import datetime, timedelta

from django.utils import timezone


def get_available_slots(doctor, date):
    """
    Devuelve una lista de tuplas (inicio, fin) — datetimes con timezone —
    con los horarios disponibles del doctor para la fecha dada, usando
    su duración fija de turno (doctor.appointment_duration_minutes).
    """
    from apps.appointments.models import Appointment  # import diferido: evita import circular

    weekday = date.weekday()
    duration = timedelta(minutes=doctor.appointment_duration_minutes)
    tz = timezone.get_current_timezone()

    windows = doctor.weekly_schedules.filter(weekday=weekday, active=True)

    candidate_slots = []
    for window in windows:
        current_start = timezone.make_aware(datetime.combine(date, window.start_time), tz)
        window_end = timezone.make_aware(datetime.combine(date, window.end_time), tz)
        while current_start + duration <= window_end:
            candidate_slots.append((current_start, current_start + duration))
            current_start += duration

    if not candidate_slots:
        return []

    day_start = timezone.make_aware(datetime.combine(date, datetime.min.time()), tz)
    day_end = day_start + timedelta(days=1)

    exceptions = list(
        doctor.availability_exceptions.filter(
            type="BLOQUEO",
            start_datetime__lt=day_end,
            end_datetime__gt=day_start,
        )
    )

    busy_appointments = list(
        Appointment.objects.filter(
            doctor=doctor,
            status__in=[Appointment.Status.CONFIRMADA, Appointment.Status.ATENDIDA],
            start_datetime__lt=day_end,
            end_datetime__gt=day_start,
        )
    )

    now = timezone.now()
    available = []
    for slot_start, slot_end in candidate_slots:
        if slot_start <= now:
            continue  # no se ofrecen horarios que ya pasaron (o están pasando)
        if any(slot_start < exc.end_datetime and slot_end > exc.start_datetime for exc in exceptions):
            continue
        if any(
            slot_start < appt.end_datetime and slot_end > appt.start_datetime
            for appt in busy_appointments
        ):
            continue
        available.append((slot_start, slot_end))

    return available


def is_slot_available(doctor, start_datetime, end_datetime):
    """Revalidación puntual: ¿este horario exacto sigue disponible?"""
    slots = get_available_slots(doctor, timezone.localtime(start_datetime).date())
    return any(s == start_datetime and e == end_datetime for s, e in slots)
