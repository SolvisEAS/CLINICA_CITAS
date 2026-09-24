from django.contrib import admin

from .models import Notification


@admin.register(Notification)
class NotificationAdmin(admin.ModelAdmin):
    list_display = ["id", "appointment", "channel", "type", "status", "scheduled_at", "sent_at", "attempts"]
    list_filter = ["channel", "type", "status"]
    readonly_fields = ["sent_at", "attempts", "error"]
