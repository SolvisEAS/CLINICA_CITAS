from django.contrib import admin

from .models import Patient, TreatmentRecord


@admin.register(Patient)
class PatientAdmin(admin.ModelAdmin):
    list_display = ["document_number", "name", "email", "phone", "created_at"]
    search_fields = ["name", "document_number", "email"]


@admin.register(TreatmentRecord)
class TreatmentRecordAdmin(admin.ModelAdmin):
    list_display = ["patient", "doctor", "created_at"]
    search_fields = ["patient__name", "patient__document_number", "description"]
    list_filter = ["doctor"]
