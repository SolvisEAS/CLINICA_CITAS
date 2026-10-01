from datetime import timedelta

from django.contrib.auth import get_user_model
from django.utils import timezone
from rest_framework import status
from rest_framework.test import APITestCase

from apps.doctors.models import Doctor

from .models import WeeklySchedule

User = get_user_model()


class AvailableDaysTests(APITestCase):
    def setUp(self):
        user = User.objects.create_user(username="dra_lopez", password="x", role=User.Role.DOCTOR)
        self.doctor = Doctor.objects.create(user=user, appointment_duration_minutes=30, active=True)
        today = timezone.localdate()
        self.monday = today + timedelta(days=(0 - today.weekday()) % 7 + 7)
        WeeklySchedule.objects.create(doctor=self.doctor, weekday=0, start_time="09:00", end_time="10:00")

    def _get(self, start, end):
        return self.client.get(
            f"/api/doctors/{self.doctor.id}/available-days/",
            {"start": start.isoformat(), "end": end.isoformat()},
        )

    def test_only_days_with_free_slots_are_returned(self):
        response = self._get(self.monday, self.monday + timedelta(days=6))
        self.assertEqual(response.status_code, status.HTTP_200_OK, response.data)
        self.assertEqual(response.data, [{"date": self.monday.isoformat(), "available_slots": 2}])

    def test_range_is_validated(self):
        self.assertEqual(self._get(self.monday, self.monday - timedelta(days=1)).status_code, 400)
        self.assertEqual(self._get(self.monday, self.monday + timedelta(days=80)).status_code, 400)
