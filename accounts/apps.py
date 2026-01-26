from django.apps import AppConfig


def _register_signals():
    from . import signals  # noqa: F401


def _register_auditlog():
    from auditlog.registry import auditlog
    from .models import UserAccess, UserSession, UserConnectionLog

    auditlog.register(UserAccess)
    auditlog.register(UserSession)
    auditlog.register(UserConnectionLog)


class AccountsConfig(AppConfig):
    default_auto_field = "django.db.models.BigAutoField"
    name = "accounts"

    def ready(self):
        _register_signals()
        _register_auditlog()
