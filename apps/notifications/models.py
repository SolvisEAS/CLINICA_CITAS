from django.db import models


class Notification(models.Model):
    """
    Punto 9 del documento: en vez de enviar el mensaje directamente
    desde la acción de reservar, se registra una tarea de notificación
    para que un proceso en segundo plano (el comando
    send_pending_notifications, pensado para correr por cron) la
    ejecute cuando corresponda.
    """

    class Channel(models.TextChoices):
        EMAIL = "EMAIL", "Correo electrónico"
        # WHATSAPP queda reservado para una fase futura (punto 10 del
        # documento): requiere un proveedor/API separado que todavía
        # no está definido. El modelo ya está preparado para sumarlo
        # sin cambiar el esquema.
        WHATSAPP = "WHATSAPP", "WhatsApp"

    class Type(models.TextChoices):
        CONFIRMACION = "CONFIRMACION", "Confirmación"
        RECORDATORIO = "RECORDATORIO", "Recordatorio"

    class Status(models.TextChoices):
        PENDIENTE = "PENDIENTE", "Pendiente"
        ENVIADA = "ENVIADA", "Enviada"
        ERROR = "ERROR", "Error"

    appointment = models.ForeignKey(
        "appointments.Appointment", on_delete=models.CASCADE, related_name="notifications"
    )
    channel = models.CharField(max_length=20, choices=Channel.choices, default=Channel.EMAIL)
    type = models.CharField(max_length=20, choices=Type.choices)
    scheduled_at = models.DateTimeField()
    sent_at = models.DateTimeField(null=True, blank=True)
    status = models.CharField(max_length=20, choices=Status.choices, default=Status.PENDIENTE)
    attempts = models.PositiveIntegerField(default=0)
    error = models.TextField(blank=True)

    class Meta:
        ordering = ["scheduled_at"]

    def __str__(self):
        return f"{self.get_type_display()} ({self.get_channel_display()}) · cita #{self.appointment_id} · {self.status}"
