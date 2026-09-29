from django.urls import path

from .views import (
    BookAppointmentView,
    DoctorAgendaView,
    PatientAppointmentsView,
    PatientCancelAppointmentView,
    PatientRescheduleAppointmentView,
    UpdateAppointmentStatusView,
)

urlpatterns = [
    path("appointments/", BookAppointmentView.as_view(), name="appointment-book"),
    path("appointments/agenda/", DoctorAgendaView.as_view(), name="appointment-agenda"),
    path("appointments/<int:pk>/status/", UpdateAppointmentStatusView.as_view(), name="appointment-status"),
    path(
        "patients/<str:document_number>/appointments/",
        PatientAppointmentsView.as_view(),
        name="patient-appointments",
    ),
    path(
        "patients/<str:document_number>/appointments/<int:pk>/",
        PatientRescheduleAppointmentView.as_view(),
        name="patient-appointment-detail",
    ),
    path(
        "patients/<str:document_number>/appointments/<int:pk>/cancel/",
        PatientCancelAppointmentView.as_view(),
        name="patient-appointment-cancel",
    ),
]
