from django.conf import settings


def test_django_settings_load():
    assert settings.ROOT_URLCONF == "config.urls"
    assert settings.DEFAULT_AUTO_FIELD == "django.db.models.BigAutoField"
    assert "django.contrib.auth" in settings.INSTALLED_APPS
    assert "accounts.apps.AccountsConfig" in settings.INSTALLED_APPS
    assert "core.apps.CoreConfig" in settings.INSTALLED_APPS
    assert "landing" in settings.INSTALLED_APPS
    assert "cms" in settings.INSTALLED_APPS
    assert hasattr(settings, "DEBUG_TOOLBAR_ENABLED")
    assert hasattr(settings, "DEV_APPS_ENABLED")
