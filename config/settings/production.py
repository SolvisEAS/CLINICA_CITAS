"""Configuración de producción."""
from decouple import Csv, config

from .base import *  # noqa: F401,F403

DEBUG = False
# Estos tres quedan en False hasta que el servidor tenga un dominio y
# certificado SSL configurados (con Nginx + Let's Encrypt, más
# adelante). Mientras se acceda por http:// plano, ponerlos en True
# rompe el acceso: el navegador redirige a https y esa conexión no
# existe todavía. Una vez que haya HTTPS, poner las tres en True en
# el .env (o borrar esas líneas, ya que True es el valor por defecto).
SECURE_SSL_REDIRECT = config("SECURE_SSL_REDIRECT", default=False, cast=bool)
SESSION_COOKIE_SECURE = config("SESSION_COOKIE_SECURE", default=False, cast=bool)
CSRF_COOKIE_SECURE = config("CSRF_COOKIE_SECURE", default=False, cast=bool)

STATICFILES_STORAGE = "whitenoise.storage.CompressedManifestStaticFilesStorage"
MIDDLEWARE.insert(1, "whitenoise.middleware.WhiteNoiseMiddleware")  # noqa: F405
