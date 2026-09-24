from django.contrib import admin

from .models import Appointment


@admin.register(Appointment)
class AppointmentAdmin(admin.ModelAdmin):
    list_display = ["id", "patient", "doctor", "start_datetime", "end_datetime", "status"]
    list_filter = ["status", "doctor"]
    search_fields = ["patient__username", "patient__email", "doctor__user__first_name"]
    date_hierarchy = "start_datetime"
