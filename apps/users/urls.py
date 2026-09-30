from django.urls import path
from rest_framework.routers import DefaultRouter
from rest_framework_simplejwt.views import TokenObtainPairView, TokenRefreshView

from .views import AdminUserViewSet, LogoutView, MeView, RegisterView

router = DefaultRouter()
router.register("users", AdminUserViewSet, basename="admin-user")

urlpatterns = [
    # Las rutas explícitas van antes que el router: "register" y "me"
    # no deben caer en el patrón .../users/{pk}/ del ViewSet de abajo.
    path("users/register/", RegisterView.as_view(), name="register"),
    path("users/me/", MeView.as_view(), name="me"),
    path("auth/login/", TokenObtainPairView.as_view(), name="login"),
    path("auth/refresh/", TokenRefreshView.as_view(), name="refresh"),
    path("auth/logout/", LogoutView.as_view(), name="logout"),
] + router.urls
