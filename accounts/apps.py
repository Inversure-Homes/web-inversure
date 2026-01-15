from django.apps import AppConfig


def _register_signals():
    from . import signals  # noqa: F401


class AccountsConfig(AppConfig):
    default_auto_field = "django.db.models.BigAutoField"
    name = "accounts"

    def ready(self):
        _register_signals()
