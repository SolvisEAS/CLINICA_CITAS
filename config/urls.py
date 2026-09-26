from pathlib import Path

from django.contrib import admin
from django.http import HttpResponse
from django.urls import include, path

# Ruta al proyecto (config/urls.py -> config -> raíz del proyecto).
PROJECT_ROOT = Path(__file__).resolve().parent.parent


def patient_app(request):
    """
    Sirve la página de demo para pacientes (pages/reservar.html) como
    HTML plano. Se lee del disco en cada request (no se importa una
    sola vez) para poder editarla sin reiniciar Gunicorn.
    Es una demo de referencia para probar el flujo completo desde un
    navegador — no reemplaza a un frontend definitivo.
    """
    html_path = PROJECT_ROOT / "pages" / "reservar.html"
    content = html_path.read_text(encoding="utf-8")
    return HttpResponse(content, content_type="text/html; charset=utf-8")


urlpatterns = [
    path("admin/", admin.site.urls),
    path("api/", include("apps.users.urls")),
    path("api/", include("apps.doctors.urls")),
    path("api/", include("apps.schedules.urls")),
    path("api/", include("apps.appointments.urls")),
    path("api/", include("apps.patients.urls")),
    path("reservar/", patient_app, name="patient-app"),
]
