from rest_framework import generics, permissions, status
from rest_framework.response import Response
from rest_framework.views import APIView
from rest_framework_simplejwt.tokens import RefreshToken

from .serializers import MeSerializer, RegisterSerializer


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
