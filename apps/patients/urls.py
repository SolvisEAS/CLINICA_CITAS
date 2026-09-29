from django.urls import path

from .views import DoctorPatientsView, PatientDetailView, PatientTreatmentRecordsView

urlpatterns = [
    path("patients/", DoctorPatientsView.as_view(), name="patient-list"),
    path("patients/<str:document_number>/", PatientDetailView.as_view(), name="patient-detail"),
    path(
        "patients/<str:document_number>/treatments/",
        PatientTreatmentRecordsView.as_view(),
        name="patient-treatments",
    ),
]
