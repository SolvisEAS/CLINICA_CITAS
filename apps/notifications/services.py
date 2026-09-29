"""
Creación y envío de notificaciones de citas.

schedule_appointment_notifications() se llama justo después de crear
una cita: registra las tareas (no envía nada todavía). El envío real
lo hace el comando `send_pending_notifications`, pensado para
ejecutarse periódicamente vía cron en el servidor (punto 19 del
documento: "worker o scheduler independiente del frontend").
"""
from datetime import timedelta

from django.conf import settings
from django.core.mail import send_mail
from django.utils import timezone

from .models import Notification

MAX_ATTEMPTS = 5


def schedule_appointment_notifications(appointment):
    """Crea la notificación de confirmación (inmediata) y un recordatorio."""
    Notification.objects.create(
        appointment=appointment,
        channel=Notification.Channel.EMAIL,
        type=Notification.Type.CONFIRMACION,
        scheduled_at=timezone.now(),
    )

    reminder_at = appointment.start_datetime - timedelta(hours=settings.REMINDER_HOURS_BEFORE)
    if reminder_at > timezone.now():
        Notification.objects.create(
            appointment=appointment,
            channel=Notification.Channel.EMAIL,
            type=Notification.Type.RECORDATORIO,
            scheduled_at=reminder_at,
        )


def _build_email(notification):
    appointment = notification.appointment
    doctor_name = str(appointment.doctor)
    local_start = timezone.localtime(appointment.start_datetime)
    fecha = local_start.strftime("%d/%m/%Y")
    hora = local_start.strftime("%H:%M")

    if notification.type == Notification.Type.CONFIRMACION:
        subject = f"Confirmación de tu cita — {fecha} {hora}"
        body = (
            f"Hola {appointment.patient.name},\n\n"
            f"Tu cita quedó confirmada:\n"
            f"  Doctor: {doctor_name}\n"
            f"  Fecha: {fecha}\n"
            f"  Hora: {hora}\n\n"
            f"Si necesitás editarla o cancelarla, podés hacerlo indicando tu"
            f" número de documento ({appointment.patient.document_number})."
        )
    else:
        subject = f"Recordatorio de tu cita — {fecha} {hora}"
        body = (
            f"Hola {appointment.patient.name},\n\n"
            f"Te recordamos tu cita:\n"
            f"  Doctor: {doctor_name}\n"
            f"  Fecha: {fecha}\n"
            f"  Hora: {hora}\n"
        )
    return subject, body


def send_notification(notification):
    """
    Envía una notificación individual. Devuelve True/False.
    No deja excepciones sin capturar: el llamador (el comando) es
    responsable de registrar attempts/error.
    """
    appointment = notification.appointment

    # Reglas de aceptación del documento: no se envían recordatorios de
    # citas que ya fueron canceladas.
    if appointment.status not in ("CONFIRMADA", "ATENDIDA"):
        notification.status = Notification.Status.ERROR
        notification.error = f"Cita en estado {appointment.status}, se omite el envío."
        notification.save(update_fields=["status", "error"])
        return False

    if notification.channel != Notification.Channel.EMAIL:
        # WhatsApp todavía no está implementado (ver docstring del modelo).
        notification.status = Notification.Status.ERROR
        notification.error = "Canal WHATSAPP todavía no implementado."
        notification.save(update_fields=["status", "error"])
        return False

    subject, body = _build_email(notification)
    try:
        send_mail(
            subject,
            body,
            settings.DEFAULT_FROM_EMAIL,
            [appointment.patient.email],
            fail_silently=False,
        )
    except Exception as exc:  # noqa: BLE001 — se registra el motivo exacto
        notification.attempts += 1
        notification.error = str(exc)
        if notification.attempts >= MAX_ATTEMPTS:
            notification.status = Notification.Status.ERROR
        notification.save(update_fields=["attempts", "error", "status"])
        return False

    notification.status = Notification.Status.ENVIADA
    notification.sent_at = timezone.now()
    notification.attempts += 1
    notification.save(update_fields=["status", "sent_at", "attempts"])
    return True
