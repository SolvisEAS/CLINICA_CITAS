"""
Pruebas de lo que un doctor (con su propio usuario/login) puede ver de
sus pacientes: la lista de "sus" pacientes, la ficha completa de uno
(datos + turnos + tratamientos) y el historial de tratamientos.
"""
from datetime import timedelta

from django.contrib.auth import get_user_model
from django.utils import timezone
from django.utils.dateparse import parse_datetime
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

    def test_administrator_group_has_no_access_to_clinical_data(self):
        # El grupo Administradores gestiona usuarios; no ve pacientes ni
        # historiales salvo que se le dé el permiso desde /admin/.
        admin = User.objects.create_user(username="admin1", password="x", role=User.Role.ADMIN)
        self.client.force_authenticate(admin)
        self.assertEqual(self.client.get("/api/patients/").status_code, status.HTTP_403_FORBIDDEN)
        self.assertEqual(self.client.get("/api/patients/87654321/").status_code, status.HTTP_403_FORBIDDEN)

    def test_superuser_sees_all_patients_and_any_detail(self):
        superuser = User.objects.create_superuser(username="root", password="x", email="root@example.com")
        self.client.force_authenticate(superuser)
        response = self.client.get("/api/patients/")
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data["count"], 2)
        detail = self.client.get("/api/patients/87654321/")
        self.assertEqual(detail.status_code, status.HTTP_200_OK)

    def test_patient_list_search_and_last_visit_with_any_doctor(self):
        # La última consulta cuenta las de cualquier doctor, aunque la lista sea la de este doctor.
        past = timezone.now() - timedelta(days=10)
        Appointment.objects.create(
            patient=self.patient, doctor=self.other_doctor, start_datetime=past,
            end_datetime=past + timedelta(minutes=30), status=Appointment.Status.ATENDIDA,
        )
        self.client.force_authenticate(self.doctor_user)
        response = self.client.get("/api/patients/", {"search": "juan"})
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data["count"], 1)
        self.assertIsNotNone(response.data["results"][0]["last_visit"])
        self.assertEqual(self.client.get("/api/patients/", {"search": "zzz"}).data["count"], 0)

    def test_doctor_cannot_read_treatments_of_unrelated_patient(self):
        self.client.force_authenticate(self.doctor_user)
        response = self.client.get("/api/patients/87654321/treatments/")
        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)

    def test_treatment_cannot_be_linked_to_another_patients_appointment(self):
        start = timezone.now() + timedelta(days=2)
        foreign = Appointment.objects.create(
            patient=self.unrelated_patient, doctor=self.doctor,
            start_datetime=start, end_datetime=start + timedelta(minutes=30),
        )
        self.client.force_authenticate(self.doctor_user)
        response = self.client.post(
            "/api/patients/12345678/treatments/",
            {"description": "Control", "appointment": foreign.id},
            format="json",
        )
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)

    def test_treatment_date_is_the_linked_appointment_date(self):
        appointment = self.patient.appointments.get()
        self.client.force_authenticate(self.doctor_user)
        response = self.client.post(
            "/api/patients/12345678/treatments/",
            {"reason": "Control", "description": "Sin novedades", "appointment": appointment.id},
            format="json",
        )
        self.assertEqual(response.status_code, status.HTTP_201_CREATED, response.data)
        self.assertEqual(parse_datetime(response.data["date"]), appointment.start_datetime)

    def test_patient_cannot_be_seen_without_a_token(self):
        response = self.client.get("/api/patients/12345678/")
        self.assertEqual(response.status_code, status.HTTP_401_UNAUTHORIZED)
