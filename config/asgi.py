import os

from decouple import config as env_config
from django.core.asgi import get_asgi_application

os.environ.setdefault(
    "DJANGO_SETTINGS_MODULE",
    env_config("DJANGO_SETTINGS_MODULE", default="config.settings.development"),
)

application = get_asgi_application()
