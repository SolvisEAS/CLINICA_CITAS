from django.urls import path

from .views import (
    BookAppointmentView,
    CancelAppointmentView,
    DoctorAgendaView,
    MyAppointmentsView,
    UpdateAppointmentStatusView,
)

urlpatterns = [
    path("appointments/", BookAppointmentView.as_view(), name="appointment-book"),
    path("appointments/mine/", MyAppointmentsView.as_view(), name="appointment-mine"),
    path("appointments/agenda/", DoctorAgendaView.as_view(), name="appointment-agenda"),
    path("appointments/<int:pk>/cancel/", CancelAppointmentView.as_view(), name="appointment-cancel"),
    path("appointments/<int:pk>/status/", UpdateAppointmentStatusView.as_view(), name="appointment-status"),
]
