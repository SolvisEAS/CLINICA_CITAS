"""
Pruebas del flujo de reserva sin login: el paciente manda sus cuatro
datos básicos (cédula, nombre, teléfono, correo) y puede después
volver a consultar, editar o cancelar su cita indicando su cédula.

Cubre también las dos reglas críticas de agendamiento:
  - un doctor no puede tener dos citas activas que se solapen
    (ExclusionConstraint a nivel de PostgreSQL);
  - un paciente no puede tener más de una cita activa el mismo día.
"""
from datetime import date, datetime, timedelta

from django.contrib.auth import get_user_model
from django.utils import timezone
from rest_framework import status
from rest_framework.test import APITestCase

from apps.doctors.models import Doctor
from apps.patients.models import Patient
from apps.schedules.models import WeeklySchedule

from .models import Appointment

User = get_user_model()


def next_weekday(weekday):
    """Próxima fecha (incluyendo hoy) que caiga en `weekday` (0=lunes)."""
    today = timezone.localdate()
    days_ahead = (weekday - today.weekday()) % 7
    return today + timedelta(days=days_ahead + 7)  # +7: nos aseguramos de que sea en el futuro


class BookingWithoutLoginTests(APITestCase):
    def setUp(self):
        user = User.objects.create_user(username="dra_lopez", password="x", role=User.Role.DOCTOR)
        self.doctor = Doctor.objects.create(user=user, appointment_duration_minutes=30, active=True)
        self.target_date = next_weekday(0)  # un lunes futuro
        WeeklySchedule.objects.create(
            doctor=self.doctor,
            weekday=self.target_date.weekday(),
            start_time="09:00",
            end_time="12:00",
        )

    def _slot(self, hour=9, minute=0):
        local_dt = datetime.combine(self.target_date, datetime.min.time()).replace(hour=hour, minute=minute)
        return timezone.make_aware(local_dt)

    def _book(self, **overrides):
        payload = {
            "document_number": "12345678",
            "name": "Juan Pérez",
            "phone": "099123456",
            "email": "juan@example.com",
            "doctor": self.doctor.id,
            "start_datetime": self._slot().isoformat(),
            "notes": "",
        }
        payload.update(overrides)
        return self.client.post("/api/appointments/", payload, format="json")

    def test_book_creates_patient_without_login(self):
        response = self._book()
        self.assertEqual(response.status_code, status.HTTP_201_CREATED, response.data)
        self.assertEqual(Patient.objects.count(), 1)
        patient = Patient.objects.get()
        self.assertEqual(patient.document_number, "12345678")
        self.assertEqual(patient.name, "Juan Pérez")
        self.assertEqual(Appointment.objects.count(), 1)

    def test_document_number_is_normalized(self):
        response = self._book(document_number="1.234.567-8")
        self.assertEqual(response.status_code, status.HTTP_201_CREATED, response.data)
        self.assertTrue(Patient.objects.filter(pk="12345678").exists())

    def test_patient_cannot_book_twice_same_day(self):
        first = self._book()
        self.assertEqual(first.status_code, status.HTTP_201_CREATED, first.data)
        second = self._book(start_datetime=self._slot(hour=10).isoformat())
        self.assertEqual(second.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertEqual(Appointment.objects.count(), 1)

    def test_two_patients_cannot_book_same_doctor_overlapping_slot(self):
        first = self._book()
        self.assertEqual(first.status_code, status.HTTP_201_CREATED, first.data)
        second = self._book(document_number="87654321", name="Otra Paciente")
        self.assertEqual(second.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertEqual(Appointment.objects.count(), 1)

    def test_patient_can_list_appointments_by_document_number(self):
        self._book()
        response = self.client.get("/api/patients/12345678/appointments/")
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data["count"], 1)

    def test_patient_can_cancel_appointment_by_document_number(self):
        created = self._book().data
        response = self.client.patch(f"/api/patients/12345678/appointments/{created['id']}/cancel/")
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data["status"], "CANCELADA")

    def test_patient_can_reschedule_appointment_by_document_number(self):
        created = self._book().data
        new_start = self._slot(hour=10).isoformat()
        response = self.client.patch(
            f"/api/patients/12345678/appointments/{created['id']}/",
            {"start_datetime": new_start},
            format="json",
        )
        self.assertEqual(response.status_code, status.HTTP_200_OK, response.data)
        self.assertEqual(response.data["start_datetime"], new_start)

    def test_other_patient_cannot_see_or_cancel_appointment(self):
        created = self._book().data
        # Otra cédula que nunca reservó nada.
        response = self.client.get("/api/patients/99999999/appointments/")
        self.assertEqual(response.status_code, status.HTTP_404_NOT_FOUND)
        cancel = self.client.patch(f"/api/patients/99999999/appointments/{created['id']}/cancel/")
        self.assertEqual(cancel.status_code, status.HTTP_404_NOT_FOUND)
