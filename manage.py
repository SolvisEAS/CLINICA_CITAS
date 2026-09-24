#!/usr/bin/env python
"""Utilidad de línea de comandos de Django para el Sistema de Citas Odontológicas."""
import os
import sys


def main():
    # Lee el .env directamente (no solo el entorno del shell) para
    # decidir qué configuración usar. Así, si el .env dice
    # DJANGO_SETTINGS_MODULE=config.settings.production, se respeta
    # de verdad, en vez de caer siempre en "development" por defecto.
    try:
        from decouple import config as env_config
        default_settings = env_config("DJANGO_SETTINGS_MODULE", default="config.settings.development")
    except ImportError:
        default_settings = "config.settings.development"

    os.environ.setdefault("DJANGO_SETTINGS_MODULE", default_settings)
    try:
        from django.core.management import execute_from_command_line
    except ImportError as exc:
        raise ImportError(
            "No se pudo importar Django. ¿Está instalado y activado "
            "el entorno virtual correcto?"
        ) from exc
    execute_from_command_line(sys.argv)


if __name__ == "__main__":
    main()
