from django.urls import path

from .views import (
    DoctorPatientsView,
    PatientDetailView,
    PatientExistsView,
    PatientTreatmentRecordsView,
)

urlpatterns = [
    path("patients/", DoctorPatientsView.as_view(), name="patient-list"),
    path(
        "patients/<str:document_number>/exists/",
        PatientExistsView.as_view(),
        name="patient-exists",
    ),
    path("patients/<str:document_number>/", PatientDetailView.as_view(), name="patient-detail"),
    path(
        "patients/<str:document_number>/treatments/",
        PatientTreatmentRecordsView.as_view(),
        name="patient-treatments",
    ),
]
