"""Configuración de desarrollo local."""
from .base import *  # noqa: F401,F403
from .base import INSTALLED_APPS

INSTALLED_APPS += ["django_extensions"]
