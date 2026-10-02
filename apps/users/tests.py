"""
Roles sobre Grupos/Permisos de Django y panel de administración de
usuarios médicos: alta, edición, activación/desactivación y contraseñas.
"""
from django.contrib.auth import get_user_model
from django.contrib.auth.models import Group
from django.core.cache import cache
from rest_framework import status
from rest_framework.test import APITestCase

from apps.doctors.models import Doctor

from .roles import ADMIN_GROUP, DOCTOR_GROUP

User = get_user_model()

NEW_DOCTOR = {
    "first_name": "Carlos",
    "last_name": "Gómez",
    "username": "dr_gomez",
    "password": "Clave-Segura-2026",
    "password_confirm": "Clave-Segura-2026",
    "role": "DOCTOR",
    "specialty": "Pediatría",
    "is_active": True,
}


class RolesAndGroupsTests(APITestCase):
    def test_groups_exist_with_their_permissions(self):
        admins = Group.objects.get(name=ADMIN_GROUP)
        doctors = Group.objects.get(name=DOCTOR_GROUP)
        self.assertTrue(admins.permissions.filter(codename="change_user").exists())
        self.assertFalse(admins.permissions.filter(codename="view_patient").exists())
        self.assertTrue(doctors.permissions.filter(codename="add_treatmentrecord").exists())
        self.assertFalse(doctors.permissions.filter(codename="change_user").exists())

    def test_role_assigns_and_moves_the_group(self):
        user = User.objects.create_user(username="u", password="x", role=User.Role.DOCTOR)
        self.assertEqual(list(user.groups.values_list("name", flat=True)), [DOCTOR_GROUP])
        user.role = User.Role.ADMIN
        user.save()
        self.assertEqual(list(user.groups.values_list("name", flat=True)), [ADMIN_GROUP])

    def test_me_reports_admin_and_doctor_profile(self):
        doctor_user = User.objects.create_user(username="doc", password="x", role=User.Role.DOCTOR)
        doctor = Doctor.objects.create(user=doctor_user)
        self.client.force_authenticate(doctor_user)
        me = self.client.get("/api/users/me/").data
        self.assertEqual((me["is_admin"], me["doctor_id"]), (False, doctor.id))

        superuser = User.objects.create_superuser(username="root", password="x", email="r@example.com")
        self.client.force_authenticate(superuser)
        self.assertTrue(self.client.get("/api/users/me/").data["is_admin"])


class AdminUserManagementTests(APITestCase):
    def setUp(self):
        cache.clear()
        self.admin = User.objects.create_user(username="admin", password="x", role=User.Role.ADMIN)
        self.client.force_authenticate(self.admin)

    def _create_doctor(self, **overrides):
        return self.client.post("/api/users/", {**NEW_DOCTOR, **overrides}, format="json")

    def test_superuser_without_role_can_manage_users(self):
        superuser = User.objects.create_superuser(username="root", password="x", email="r@example.com")
        self.client.force_authenticate(superuser)
        self.assertEqual(self.client.get("/api/users/").status_code, status.HTTP_200_OK)

    def test_doctor_cannot_manage_users(self):
        doctor = User.objects.create_user(username="doc", password="x", role=User.Role.DOCTOR)
        self.client.force_authenticate(doctor)
        self.assertEqual(self.client.get("/api/users/").status_code, status.HTTP_403_FORBIDDEN)
        self.assertEqual(self._create_doctor().status_code, status.HTTP_403_FORBIDDEN)

    def test_create_doctor_builds_account_profile_and_group(self):
        response = self._create_doctor()
        self.assertEqual(response.status_code, status.HTTP_201_CREATED, response.data)
        self.assertNotIn("password", response.data)
        user = User.objects.get(username="dr_gomez")
        self.assertNotEqual(user.password, NEW_DOCTOR["password"])  # se guarda el hash, nunca el texto
        self.assertTrue(user.check_password(NEW_DOCTOR["password"]))
        self.assertTrue(user.groups.filter(name=DOCTOR_GROUP).exists())
        self.assertEqual(user.doctor_profile.specialty, "Pediatría")
        self.assertTrue(user.doctor_profile.active)
        self.assertEqual(response.data["doctor"]["specialty"], "Pediatría")

        self.client.force_authenticate(None)
        login = self.client.post(
            "/api/auth/login/", {"username": "dr_gomez", "password": NEW_DOCTOR["password"]}, format="json"
        )
        self.assertEqual(login.status_code, status.HTTP_200_OK)

    def test_create_requires_matching_password_confirmation(self):
        response = self._create_doctor(password_confirm="otra-cosa")
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn("password_confirm", response.data)

    def test_deactivated_doctor_cannot_log_in_but_keeps_its_data(self):
        user_id = self._create_doctor().data["id"]
        response = self.client.patch(f"/api/users/{user_id}/", {"is_active": False}, format="json")
        self.assertEqual(response.status_code, status.HTTP_200_OK, response.data)
        user = User.objects.get(pk=user_id)
        self.assertFalse(user.is_active)
        self.assertFalse(user.doctor_profile.active)  # deja de aparecer para reservar

        self.client.force_authenticate(None)
        login = self.client.post(
            "/api/auth/login/", {"username": "dr_gomez", "password": NEW_DOCTOR["password"]}, format="json"
        )
        self.assertEqual(login.status_code, status.HTTP_401_UNAUTHORIZED)

        self.client.force_authenticate(self.admin)
        self.client.patch(f"/api/users/{user_id}/", {"is_active": True}, format="json")
        self.assertTrue(Doctor.objects.get(user_id=user_id).active)

    def test_token_of_a_deactivated_user_stops_working(self):
        self._create_doctor()
        self.client.force_authenticate(None)
        access = self.client.post(
            "/api/auth/login/", {"username": "dr_gomez", "password": NEW_DOCTOR["password"]}, format="json"
        ).data["access"]
        User.objects.filter(username="dr_gomez").update(is_active=False)
        self.client.credentials(HTTP_AUTHORIZATION=f"Bearer {access}")
        self.assertEqual(self.client.get("/api/users/me/").status_code, status.HTTP_401_UNAUTHORIZED)

    def test_edit_doctor_data(self):
        user_id = self._create_doctor().data["id"]
        response = self.client.patch(
            f"/api/users/{user_id}/", {"last_name": "Gómez Ruiz", "specialty": "Ortodoncia"}, format="json"
        )
        self.assertEqual(response.status_code, status.HTTP_200_OK, response.data)
        self.assertEqual(response.data["last_name"], "Gómez Ruiz")
        self.assertEqual(response.data["doctor"]["specialty"], "Ortodoncia")

    def test_admin_cannot_lock_themselves_out(self):
        own = f"/api/users/{self.admin.id}/"
        self.assertEqual(self.client.patch(own, {"is_active": False}, format="json").status_code, 400)
        self.assertEqual(self.client.patch(own, {"role": "DOCTOR"}, format="json").status_code, 400)

    def test_reset_password_requires_confirmation(self):
        user_id = self._create_doctor().data["id"]
        url = f"/api/users/{user_id}/set-password/"
        mismatch = self.client.patch(url, {"new_password": "Nueva-Clave-99", "new_password_confirm": "x"}, format="json")
        self.assertEqual(mismatch.status_code, status.HTTP_400_BAD_REQUEST)
        ok = self.client.patch(
            url, {"new_password": "Nueva-Clave-99", "new_password_confirm": "Nueva-Clave-99"}, format="json"
        )
        self.assertEqual(ok.status_code, status.HTTP_200_OK)
        self.assertTrue(User.objects.get(pk=user_id).check_password("Nueva-Clave-99"))

    def test_regular_admin_cannot_touch_a_superuser(self):
        superuser = User.objects.create_superuser(username="root", password="x", email="r@example.com")
        response = self.client.patch(f"/api/users/{superuser.id}/", {"is_active": False}, format="json")
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        reset = self.client.patch(
            f"/api/users/{superuser.id}/set-password/",
            {"new_password": "Nueva-Clave-99", "new_password_confirm": "Nueva-Clave-99"},
            format="json",
        )
        self.assertEqual(reset.status_code, status.HTTP_403_FORBIDDEN)
