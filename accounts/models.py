from django.contrib.auth.models import User
from django.db import models


class UserAccess(models.Model):
    user = models.OneToOneField(User, on_delete=models.CASCADE, related_name="user_access")
    use_custom_perms = models.BooleanField(
        default=False,
        help_text="Si está activo, se usan los permisos individuales y se ignoran los roles.",
    )
    can_simulador = models.BooleanField(default=False)
    can_estudios = models.BooleanField(default=False)
    can_proyectos = models.BooleanField(default=False)
    can_clientes = models.BooleanField(default=False)
    can_inversores = models.BooleanField(default=False)
    can_usuarios = models.BooleanField(default=False)
    can_cms = models.BooleanField(default=False)
    can_facturas_preview = models.BooleanField(default=False)

    def __str__(self):
        return f"Permisos · {self.user.username}"
