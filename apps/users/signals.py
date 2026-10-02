from django.contrib.auth.models import Group
from django.db.models.signals import post_save
from django.dispatch import receiver

from .models import User
from .roles import ROLE_GROUPS


@receiver(post_save, sender=User)
def sync_role_group(sender, instance, raw=False, update_fields=None, **kwargs):
    """
    Mantiene al usuario en el grupo que corresponde a su rol (y fuera de
    los demás grupos de rol). No toca otros grupos que se le hayan
    asignado a mano desde /admin/.
    """
    if raw:  # loaddata: los grupos vienen en el fixture
        return
    if update_fields is not None and "role" not in update_fields:
        return  # p. ej. el login solo actualiza last_login

    wanted = ROLE_GROUPS.get(instance.role)
    other_role_groups = Group.objects.filter(name__in=ROLE_GROUPS.values()).exclude(name=wanted)
    instance.groups.remove(*other_role_groups)
    if wanted:
        group, _ = Group.objects.get_or_create(name=wanted)
        instance.groups.add(group)
