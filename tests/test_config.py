from django.conf import settings

from config.settings import _build_database_config


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


def test_sqlite_database_url_does_not_add_ssl_options():
    database = _build_database_config("sqlite:///./ci.sqlite3")["default"]

    assert database["ENGINE"] == "django.db.backends.sqlite3"
    assert "OPTIONS" not in database
    assert "sslmode" not in database.get("OPTIONS", {})


def test_postgresql_database_url_requires_ssl():
    database = _build_database_config("postgresql://user:pass@localhost:5432/dbname")["default"]

    assert database["ENGINE"] == "django.db.backends.postgresql"
    assert database["OPTIONS"]["sslmode"] == "require"
