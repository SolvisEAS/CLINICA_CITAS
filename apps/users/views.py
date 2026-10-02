from django.contrib.auth import get_user_model
from django.db.models import Q
from rest_framework import generics, permissions, status, viewsets
from rest_framework.decorators import action
from rest_framework.exceptions import PermissionDenied
from rest_framework.response import Response
from rest_framework.views import APIView
from rest_framework_simplejwt.tokens import RefreshToken

from core.permissions import IsAdministrator

from .serializers import (
    AdminUserSerializer,
    AdminUserWriteSerializer,
    MeSerializer,
    RegisterSerializer,
    SetPasswordSerializer,
)

User = get_user_model()


class RegisterView(generics.CreateAPIView):
    """POST /api/users/register/ — registro público de pacientes."""

    serializer_class = RegisterSerializer
    permission_classes = [permissions.AllowAny]


class MeView(generics.RetrieveUpdateAPIView):
    """GET/PATCH /api/users/me/ — datos del usuario autenticado."""

    serializer_class = MeSerializer
    permission_classes = [permissions.IsAuthenticated]

    def get_object(self):
        return self.request.user


class LogoutView(APIView):
    """
    POST /api/auth/logout/ con {"refresh": "..."} — invalida (blacklist)
    ese refresh token para que no pueda volver a usarse.
    """

    permission_classes = [permissions.AllowAny]

    def post(self, request):
        refresh = request.data.get("refresh")
        if not refresh:
            return Response({"detail": "Falta el campo 'refresh'."}, status=status.HTTP_400_BAD_REQUEST)
        try:
            token = RefreshToken(refresh)
            token.blacklist()
        except Exception:
            return Response({"detail": "Token inválido o ya invalidado."}, status=status.HTTP_400_BAD_REQUEST)
        return Response(status=status.HTTP_200_OK)


class AdminUserViewSet(viewsets.ModelViewSet):
    """
    Panel de administración de usuarios Doctor/Administrador (solo
    administradores):
      GET   /api/users/[?role=DOCTOR|ADMIN]   listar
      POST  /api/users/                       crear
      GET   /api/users/{id}/                  ver
      PATCH /api/users/{id}/                  editar / activar / desactivar
      PATCH /api/users/{id}/set-password/     restablecer contraseña
    No hay DELETE: a un usuario se lo desactiva, no se lo borra.
    """

    permission_classes = [permissions.IsAuthenticated, IsAdministrator]
    http_method_names = ["get", "post", "patch", "head", "options"]

    def get_serializer_class(self):
        if self.action in ("create", "partial_update"):
            return AdminUserWriteSerializer
        if self.action == "set_password":
            return SetPasswordSerializer
        return AdminUserSerializer

    def get_queryset(self):
        qs = (
            User.objects.filter(Q(role__in=[User.Role.DOCTOR, User.Role.ADMIN]) | Q(is_superuser=True))
            .select_related("doctor_profile")
            .order_by("first_name", "last_name", "username")
        )
        role = self.request.query_params.get("role")
        if role:
            qs = qs.filter(role=role)
        return qs

    @action(detail=True, methods=["patch"], url_path="set-password")
    def set_password(self, request, pk=None):
        user = self.get_object()
        if user.is_superuser and not request.user.is_superuser:
            raise PermissionDenied("Solo un superusuario puede cambiar la contraseña de otro superusuario.")
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        user.set_password(serializer.validated_data["new_password"])
        user.save(update_fields=["password"])
        return Response(status=status.HTTP_200_OK)
