"""
Crea los grupos Administradores y Doctores con sus permisos iniciales y
asigna a los usuarios existentes según su `role`. Solo datos: no cambia
el esquema. Los permisos quedan congelados acá a propósito; cambios
futuros van en migraciones nuevas (o a mano desde /admin/).
"""
from django.contrib.auth.management import create_permissions
from django.db import migrations

GROUP_PERMISSIONS = {
    "Administradores": [
        ("users", "view_user"),
        ("users", "add_user"),
        ("users", "change_user"),
        ("doctors", "view_doctor"),
        ("doctors", "add_doctor"),
        ("doctors", "change_doctor"),
        ("schedules", "view_weeklyschedule"),
        ("schedules", "add_weeklyschedule"),
        ("schedules", "change_weeklyschedule"),
        ("schedules", "delete_weeklyschedule"),
        ("schedules", "view_availabilityexception"),
        ("schedules", "add_availabilityexception"),
        ("schedules", "change_availabilityexception"),
        ("schedules", "delete_availabilityexception"),
    ],
    "Doctores": [
        ("appointments", "view_appointment"),
        ("appointments", "change_appointment"),
        ("patients", "view_patient"),
        ("patients", "view_treatmentrecord"),
        ("patients", "add_treatmentrecord"),
        ("schedules", "view_weeklyschedule"),
        ("schedules", "add_weeklyschedule"),
        ("schedules", "change_weeklyschedule"),
        ("schedules", "delete_weeklyschedule"),
        ("schedules", "view_availabilityexception"),
        ("schedules", "add_availabilityexception"),
        ("schedules", "change_availabilityexception"),
        ("schedules", "delete_availabilityexception"),
    ],
}

ROLE_GROUPS = {"ADMIN": "Administradores", "DOCTOR": "Doctores"}


def create_groups(apps, schema_editor):
    # Los permisos de Django se crean al final de `migrate`; en una base
    # nueva todavía no existen en este punto, así que se crean acá.
    for app_config in apps.get_app_configs():
        app_config.models_module = True
        create_permissions(app_config, apps=apps, verbosity=0)
        app_config.models_module = None

    Group = apps.get_model("auth", "Group")
    Permission = apps.get_model("auth", "Permission")
    User = apps.get_model("users", "User")

    for group_name, perms in GROUP_PERMISSIONS.items():
        group, _ = Group.objects.get_or_create(name=group_name)
        for app_label, codename in perms:
            group.permissions.add(Permission.objects.get(content_type__app_label=app_label, codename=codename))

    for role, group_name in ROLE_GROUPS.items():
        group = Group.objects.get(name=group_name)
        for user in User.objects.filter(role=role):
            user.groups.add(group)


def remove_groups(apps, schema_editor):
    apps.get_model("auth", "Group").objects.filter(name__in=GROUP_PERMISSIONS.keys()).delete()


class Migration(migrations.Migration):
    dependencies = [
        ("users", "0001_initial"),
        ("auth", "0012_alter_user_first_name_max_length"),
        ("contenttypes", "0002_remove_content_type_name"),
        ("doctors", "0002_initial"),
        ("schedules", "0001_initial"),
        ("appointments", "0003_appointment_patient_and_more"),
        ("patients", "0002_email_opcional_y_campos_historial"),
    ]

    operations = [migrations.RunPython(create_groups, remove_groups)]
