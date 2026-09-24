from django.contrib import admin

from .models import AvailabilityException, WeeklySchedule


@admin.register(WeeklySchedule)
class WeeklyScheduleAdmin(admin.ModelAdmin):
    list_display = ["doctor", "get_weekday_display", "start_time", "end_time", "active"]
    list_filter = ["weekday", "active", "doctor"]

    @admin.display(description="Día")
    def get_weekday_display(self, obj):
        return obj.get_weekday_display()


@admin.register(AvailabilityException)
class AvailabilityExceptionAdmin(admin.ModelAdmin):
    list_display = ["doctor", "start_datetime", "end_datetime", "type", "reason"]
    list_filter = ["type", "doctor"]
