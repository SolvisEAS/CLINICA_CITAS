"""
Roles de la aplicación sobre Grupos y Permisos de Django.

`User.role` sigue diciendo qué tipo de usuario es (Doctor/Administrador),
pero lo que cada uno puede hacer sale de los permisos de Django, que
llegan por el grupo que le corresponde a su rol. El grupo se asigna solo
al guardar el usuario (ver signals.py), y los permisos iniciales de cada
grupo los crea la migración users.0002. Así:

  - el superusuario de Django puede todo sin configurar nada, y
  - un superusuario puede ajustar permisos finos de cada grupo desde
    /admin/ sin tocar código.
"""

ADMIN_GROUP = "Administradores"
DOCTOR_GROUP = "Doctores"

ROLE_GROUPS = {
    "ADMIN": ADMIN_GROUP,
    "DOCTOR": DOCTOR_GROUP,
}

# Permiso que distingue a quien administra la aplicación (lo tiene el
# grupo Administradores y, por definición, el superusuario).
MANAGE_USERS_PERMISSION = "users.change_user"
