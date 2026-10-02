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

from unittest.mock import patch

from django.conf import settings
from django.contrib.auth import get_user_model
from django.core.cache import cache
from django.utils import timezone
from django.utils.dateparse import parse_datetime as parse_dt
from rest_framework import status
from rest_framework.test import APITestCase
from rest_framework.throttling import ScopedRateThrottle

from apps.doctors.models import Doctor
from apps.notifications.models import Notification
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
        cache.clear()  # el límite de intentos por IP no debe arrastrarse entre tests
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

    def test_existing_patient_books_with_only_document_number(self):
        Patient.objects.create(document_number="12345678", name="Juan Pérez", phone="099123456", email="")
        response = self.client.post(
            "/api/appointments/",
            {"document_number": "12345678", "doctor": self.doctor.id, "start_datetime": self._slot().isoformat()},
            format="json",
        )
        self.assertEqual(response.status_code, status.HTTP_201_CREATED, response.data)
        self.assertEqual(response.data["patient_name"], "Juan Pérez")

    def test_existing_patient_data_is_not_overwritten(self):
        Patient.objects.create(document_number="12345678", name="Juan Pérez", phone="099123456", email="")
        response = self._book(name="Otro Nombre", phone="000", email="otro@example.com")
        self.assertEqual(response.status_code, status.HTTP_201_CREATED, response.data)
        patient = Patient.objects.get(pk="12345678")
        self.assertEqual((patient.name, patient.phone, patient.email), ("Juan Pérez", "099123456", ""))

    def test_new_patient_requires_name_and_phone(self):
        response = self._book(name="", phone="")
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn("name", response.data)
        self.assertIn("phone", response.data)
        self.assertFalse(Patient.objects.exists())

    def test_new_patient_email_is_optional(self):
        payload_without_email = self._book(email="")
        self.assertEqual(payload_without_email.status_code, status.HTTP_201_CREATED, payload_without_email.data)
        self.assertEqual(Patient.objects.get().email, "")

    def test_other_patient_cannot_see_or_cancel_appointment(self):
        created = self._book().data
        # Otra cédula que nunca reservó nada.
        response = self.client.get("/api/patients/99999999/appointments/")
        self.assertEqual(response.status_code, status.HTTP_404_NOT_FOUND)
        cancel = self.client.patch(f"/api/patients/99999999/appointments/{created['id']}/cancel/")
        self.assertEqual(cancel.status_code, status.HTTP_404_NOT_FOUND)


class MyAppointmentsAndModifyTests(APITestCase):
    """Portal público: "Ver mis consultas" y "Modificar consulta" con la CI."""

    def setUp(self):
        cache.clear()
        self.doctor = self._make_doctor("dra_lopez", "Odontología general")
        self.other_doctor = self._make_doctor("dr_gomez", "Ortodoncia")
        self.monday = next_weekday(0)
        self.patient = Patient.objects.create(
            document_number="12345678", name="Juan Pérez", phone="099123456", email="juan@example.com"
        )

    def _make_doctor(self, username, specialty):
        user = User.objects.create_user(username=username, password="x", role=User.Role.DOCTOR)
        doctor = Doctor.objects.create(user=user, specialty=specialty, appointment_duration_minutes=30, active=True)
        WeeklySchedule.objects.create(doctor=doctor, weekday=0, start_time="09:00", end_time="12:00")
        return doctor

    def _at(self, day, hour, minute=0):
        return timezone.make_aware(datetime.combine(day, datetime.min.time()).replace(hour=hour, minute=minute))

    def _create(self, start, status=Appointment.Status.CONFIRMADA, patient=None):
        return Appointment.objects.create(
            patient=patient or self.patient, doctor=self.doctor, status=status,
            start_datetime=start, end_datetime=start + timedelta(minutes=30),
        )

    def _book(self, start):
        return self.client.post(
            "/api/appointments/",
            {"document_number": "12345678", "doctor": self.doctor.id, "start_datetime": start.isoformat()},
            format="json",
        )

    def _modify(self, appointment_id, **data):
        return self.client.patch(f"/api/patients/12345678/appointments/{appointment_id}/", data, format="json")

    def test_my_appointments_lists_only_future_pending_with_minimal_data(self):
        upcoming = self._create(self._at(self.monday, 9))
        self._create(self._at(self.monday + timedelta(days=7), 9), status=Appointment.Status.CANCELADA)
        self._create(self._at(self.monday + timedelta(days=14), 9), status=Appointment.Status.ATENDIDA)
        self._create(timezone.now() - timedelta(days=2))

        response = self.client.get("/api/patients/12345678/appointments/")
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual([a["id"] for a in response.data["results"]], [upcoming.id])
        item = response.data["results"][0]
        self.assertEqual(item["doctor_specialty"], "Odontología general")
        self.assertTrue(item["can_modify"])
        for private_field in ("patient", "patient_name", "notes"):
            self.assertNotIn(private_field, item)

    def test_modify_can_change_doctor_and_frees_the_old_slot(self):
        created = self._book(self._at(self.monday, 9)).data
        new_start = self._at(self.monday, 10)
        response = self._modify(created["id"], doctor=self.other_doctor.id, start_datetime=new_start.isoformat())
        self.assertEqual(response.status_code, status.HTTP_200_OK, response.data)
        appointment = Appointment.objects.get(pk=created["id"])
        self.assertEqual(appointment.doctor, self.other_doctor)
        self.assertEqual(appointment.end_datetime, new_start + timedelta(minutes=30))

        freed = self.client.get(f"/api/doctors/{self.doctor.id}/availability/", {"date": self.monday.isoformat()})
        self.assertIn(self._at(self.monday, 9), [parse_dt(s["start_datetime"]) for s in freed.data])

    def test_modify_is_rejected_once_the_appointment_time_arrived(self):
        started = self._create(timezone.now() - timedelta(minutes=5))
        response = self._modify(started.id, start_datetime=self._at(self.monday, 10).isoformat())
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn("ya no se puede modificar", response.data["detail"])
        cancel = self.client.patch(f"/api/patients/12345678/appointments/{started.id}/cancel/")
        self.assertEqual(cancel.status_code, status.HTTP_400_BAD_REQUEST)

    def test_changing_doctor_requires_a_new_time(self):
        created = self._book(self._at(self.monday, 9)).data
        response = self._modify(created["id"], doctor=self.other_doctor.id)
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn("start_datetime", response.data)

    def test_modify_into_a_taken_slot_is_rejected(self):
        other_patient = Patient.objects.create(document_number="87654321", name="Otra", phone="099000000")
        self._create(self._at(self.monday, 10), patient=other_patient)
        created = self._book(self._at(self.monday, 9)).data
        response = self._modify(created["id"], start_datetime=self._at(self.monday, 10).isoformat())
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertEqual(Appointment.objects.get(pk=created["id"]).start_datetime, self._at(self.monday, 9))

    def test_modify_replaces_the_pending_reminder(self):
        created = self._book(self._at(self.monday, 9)).data
        new_start = self._at(self.monday, 11)
        self._modify(created["id"], start_datetime=new_start.isoformat())
        reminders = Notification.objects.filter(
            appointment_id=created["id"], type=Notification.Type.RECORDATORIO, status=Notification.Status.PENDIENTE
        )
        self.assertEqual(reminders.count(), 1)
        self.assertEqual(reminders.get().scheduled_at, new_start - timedelta(hours=settings.REMINDER_HOURS_BEFORE))

    def test_no_notifications_are_queued_for_a_patient_without_email(self):
        response = self.client.post(
            "/api/appointments/",
            {
                "document_number": "55555555", "name": "Sin Correo", "phone": "099111222",
                "doctor": self.doctor.id, "start_datetime": self._at(self.monday, 9).isoformat(),
            },
            format="json",
        )
        self.assertEqual(response.status_code, status.HTTP_201_CREATED, response.data)
        self.assertFalse(Notification.objects.filter(appointment_id=response.data["id"]).exists())

    def test_public_ci_endpoints_are_rate_limited(self):
        with patch.dict(ScopedRateThrottle.THROTTLE_RATES, {"public_ci": "3/minute"}):
            codes = [self.client.get("/api/patients/12345678/exists/").status_code for _ in range(4)]
        self.assertEqual(codes, [200, 200, 200, 429])

    def test_doctor_sees_own_upcoming_appointments(self):
        first = self._create(self._at(self.monday, 9))
        second = self._create(self._at(self.monday + timedelta(days=7), 9))
        self._create(self._at(self.monday + timedelta(days=14), 9), status=Appointment.Status.CANCELADA)
        self.client.force_authenticate(self.doctor.user)
        response = self.client.get("/api/appointments/upcoming/")
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual([a["id"] for a in response.data["results"]], [first.id, second.id])

        self.client.force_authenticate(self.other_doctor.user)
        self.assertEqual(self.client.get("/api/appointments/upcoming/").data["count"], 0)
