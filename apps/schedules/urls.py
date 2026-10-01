from django.urls import path
from rest_framework.routers import DefaultRouter

from .views import (
    AvailabilityExceptionViewSet,
    DoctorAvailabilityView,
    DoctorAvailableDaysView,
    WeeklyScheduleViewSet,
)

router = DefaultRouter()
router.register("weekly-schedules", WeeklyScheduleViewSet, basename="weekly-schedule")
router.register("availability-exceptions", AvailabilityExceptionViewSet, basename="availability-exception")

urlpatterns = router.urls + [
    path("doctors/<int:doctor_id>/availability/", DoctorAvailabilityView.as_view(), name="doctor-availability"),
    path(
        "doctors/<int:doctor_id>/available-days/",
        DoctorAvailableDaysView.as_view(),
        name="doctor-available-days",
    ),
]
