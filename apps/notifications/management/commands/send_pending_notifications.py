from django.core.management.base import BaseCommand
from django.utils import timezone

from apps.notifications.models import Notification
from apps.notifications.services import MAX_ATTEMPTS, send_notification


class Command(BaseCommand):
    """
    Worker/scheduler del punto 19 del documento: revisa las
    notificaciones pendientes cuya fecha de ejecución ya llegó y las
    envía. Pensado para ejecutarse periódicamente vía cron, por
    ejemplo cada 5 minutos:

        */5 * * * * cd /ruta/al/proyecto && venv/bin/python manage.py send_pending_notifications
    """

    help = "Envía las notificaciones (email) pendientes cuya fecha de ejecución ya llegó."

    def handle(self, *args, **options):
        pending = Notification.objects.filter(
            status=Notification.Status.PENDIENTE,
            scheduled_at__lte=timezone.now(),
            attempts__lt=MAX_ATTEMPTS,
        )
        sent, failed = 0, 0
        for notification in pending:
            ok = send_notification(notification)
            if ok:
                sent += 1
            else:
                failed += 1
        self.stdout.write(self.style.SUCCESS(f"Listo. Enviadas: {sent}. Con error/omitidas: {failed}."))
