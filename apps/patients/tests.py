"""
Pruebas de lo que un doctor (con su propio usuario/login) puede ver de
sus pacientes: la lista de "sus" pacientes, la ficha completa de uno
(datos + turnos + tratamientos) y el historial de tratamientos.
"""
from datetime import timedelta

from django.contrib.auth import get_user_model
from django.utils import timezone
from rest_framework import status
from rest_framework.test import APITestCase

from apps.appointments.models import Appointment
from apps.doctors.models import Doctor

from .models import Patient, TreatmentRecord

User = get_user_model()


class DoctorViewsOwnPatientsTests(APITestCase):
    def setUp(self):
        self.doctor_user = User.objects.create_user(username="dr_a", password="x", role=User.Role.DOCTOR)
        self.doctor = Doctor.objects.create(user=self.doctor_user, active=True)

        self.other_doctor_user = User.objects.create_user(username="dr_b", password="x", role=User.Role.DOCTOR)
        self.other_doctor = Doctor.objects.create(user=self.other_doctor_user, active=True)

        self.patient = Patient.objects.create(
            document_number="12345678", name="Juan Pérez", phone="099123456", email="juan@example.com"
        )
        self.unrelated_patient = Patient.objects.create(
            document_number="87654321", name="Otro Paciente", phone="099000000", email="otro@example.com"
        )

        start = timezone.now() + timedelta(days=1)
        Appointment.objects.create(
            patient=self.patient, doctor=self.doctor, start_datetime=start, end_datetime=start + timedelta(minutes=30)
        )

    def test_doctor_sees_only_own_patients(self):
        self.client.force_authenticate(self.doctor_user)
        response = self.client.get("/api/patients/")
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        docs = [p["document_number"] for p in response.data["results"]]
        self.assertIn("12345678", docs)
        self.assertNotIn("87654321", docs)

    def test_doctor_can_see_full_patient_detail_with_appointments_and_treatments(self):
        TreatmentRecord.objects.create(patient=self.patient, doctor=self.doctor, description="Limpieza")
        self.client.force_authenticate(self.doctor_user)
        response = self.client.get("/api/patients/12345678/")
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(len(response.data["appointments"]), 1)
        self.assertEqual(len(response.data["treatment_records"]), 1)

    def test_doctor_cannot_see_patient_without_shared_appointment(self):
        self.client.force_authenticate(self.doctor_user)
        response = self.client.get("/api/patients/87654321/")
        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)

    def test_other_doctor_cannot_see_patient_that_is_not_theirs(self):
        self.client.force_authenticate(self.other_doctor_user)
        response = self.client.get("/api/patients/12345678/")
        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)

    def test_admin_sees_all_patients_and_any_detail(self):
        admin = User.objects.create_user(username="admin1", password="x", role=User.Role.ADMIN)
        self.client.force_authenticate(admin)
        response = self.client.get("/api/patients/")
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data["count"], 2)
        detail = self.client.get("/api/patients/87654321/")
        self.assertEqual(detail.status_code, status.HTTP_200_OK)

    def test_patient_cannot_be_seen_without_a_token(self):
        response = self.client.get("/api/patients/12345678/")
        self.assertEqual(response.status_code, status.HTTP_401_UNAUTHORIZED)
