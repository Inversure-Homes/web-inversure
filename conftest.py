import pytest
from django.contrib.staticfiles.storage import staticfiles_storage
from django.core.files.storage import storages
from django.utils.functional import empty


@pytest.fixture(autouse=True)
def use_plain_staticfiles_storage(settings):
    settings.STATICFILES_STORAGE = "django.contrib.staticfiles.storage.StaticFilesStorage"

    if hasattr(settings, "STORAGES") and isinstance(settings.STORAGES, dict):
        settings.STORAGES.setdefault("staticfiles", {})["BACKEND"] = (
            "django.contrib.staticfiles.storage.StaticFilesStorage"
        )

    storages._backends = None
    storages.__dict__.pop("backends", None)
    storages._storages.pop("staticfiles", None)
    staticfiles_storage._wrapped = empty

    yield

    storages._backends = None
    storages.__dict__.pop("backends", None)
    storages._storages.pop("staticfiles", None)
    staticfiles_storage._wrapped = empty
