from django.contrib.auth.models import User
from django.db import models
from django.utils import timezone


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


class UserSession(models.Model):
    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name="sessions")
    session_key = models.CharField(max_length=40, unique=True)
    ip_address = models.CharField(max_length=64, blank=True)
    user_agent = models.TextField(blank=True)
    created_at = models.DateTimeField(default=timezone.now)
    last_seen_at = models.DateTimeField(default=timezone.now)
    ended_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering = ["-last_seen_at"]

    def __str__(self):
        return f"{self.user.username} · {self.session_key}"

    def is_active(self, timeout_minutes=15):
        if self.ended_at:
            return False
        return self.last_seen_at >= timezone.now() - timezone.timedelta(minutes=timeout_minutes)


class UserConnectionLog(models.Model):
    EVENT_LOGIN = "login"
    EVENT_LOGOUT = "logout"
    EVENT_CHOICES = [
        (EVENT_LOGIN, "Login"),
        (EVENT_LOGOUT, "Logout"),
    ]

    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name="connection_logs")
    event = models.CharField(max_length=10, choices=EVENT_CHOICES)
    ip_address = models.CharField(max_length=64, blank=True)
    user_agent = models.TextField(blank=True)
    created_at = models.DateTimeField(default=timezone.now)

    class Meta:
        ordering = ["-created_at"]

    def __str__(self):
        return f"{self.user.username} · {self.event} · {self.created_at:%Y-%m-%d %H:%M:%S}"
