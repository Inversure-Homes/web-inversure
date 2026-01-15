from django.contrib.auth.models import Group, User
from django.db.models.signals import post_migrate, post_save
from django.dispatch import receiver

from .models import UserAccess
from .utils import ROLE_ADMIN, ROLE_COMERCIAL, ROLE_MARKETING


@receiver(post_migrate)
def ensure_role_groups(sender, **kwargs):
    if sender.name != "accounts":
        return
    for name in (ROLE_ADMIN, ROLE_MARKETING, ROLE_COMERCIAL):
        Group.objects.get_or_create(name=name)
    for user in User.objects.all():
        UserAccess.objects.get_or_create(user=user)


@receiver(post_save, sender=User)
def ensure_user_access(sender, instance, created, **kwargs):
    if created:
        UserAccess.objects.get_or_create(user=instance)
