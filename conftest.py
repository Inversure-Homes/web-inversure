import tempfile
from pathlib import Path

import pytest
from django.contrib.staticfiles.storage import staticfiles_storage
from django.core.files.storage import storages
from django.core.management import call_command
from django.utils.functional import empty

_STATIC_ROOT = Path(tempfile.mkdtemp(prefix="web-inversure-static-"))
_STATICFILES_COLLECTED = False


def _clear_staticfiles_cache() -> None:
    storages._backends = None
    storages.__dict__.pop("backends", None)
    storages._storages.pop("staticfiles", None)
    staticfiles_storage._wrapped = empty


@pytest.fixture(autouse=True)
def use_manifest_staticfiles_storage(settings):
    global _STATICFILES_COLLECTED

    settings.STATIC_ROOT = _STATIC_ROOT
    _clear_staticfiles_cache()

    if not _STATICFILES_COLLECTED:
        call_command("collectstatic", interactive=False, verbosity=0, clear=True, link=False)
        _STATICFILES_COLLECTED = True

    yield

    _clear_staticfiles_cache()
