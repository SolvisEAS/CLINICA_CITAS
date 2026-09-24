from django.contrib import admin

from .models import Doctor


@admin.register(Doctor)
class DoctorAdmin(admin.ModelAdmin):
    list_display = ["__str__", "specialty", "appointment_duration_minutes", "active"]
    list_filter = ["active", "specialty"]
    search_fields = ["user__first_name", "user__last_name", "user__email"]
    autocomplete_fields = ["user"]
