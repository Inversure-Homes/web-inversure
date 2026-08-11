from pathlib import Path

from django.conf import settings
from django.contrib.staticfiles.storage import staticfiles_storage


def test_manifest_staticfiles_storage_collects_and_resolves_relevant_asset():
    static_root = Path(settings.STATIC_ROOT)

    manifest_path = static_root / "staticfiles.json"
    assert manifest_path.exists()

    resolved_url = staticfiles_storage.url("core/logo_inversure.png")
    assert resolved_url.startswith(settings.STATIC_URL)

    relative_path = resolved_url.removeprefix(settings.STATIC_URL)
    assert "logo_inversure." in relative_path
    assert (static_root / relative_path).exists()
