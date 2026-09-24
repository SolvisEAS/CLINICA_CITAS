from django.urls import path
from rest_framework_simplejwt.views import TokenObtainPairView, TokenRefreshView

from .views import LogoutView, MeView, RegisterView

urlpatterns = [
    path("users/register/", RegisterView.as_view(), name="register"),
    path("users/me/", MeView.as_view(), name="me"),
    path("auth/login/", TokenObtainPairView.as_view(), name="login"),
    path("auth/refresh/", TokenRefreshView.as_view(), name="refresh"),
    path("auth/logout/", LogoutView.as_view(), name="logout"),
]
