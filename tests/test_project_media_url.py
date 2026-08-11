from __future__ import annotations

from types import SimpleNamespace

import pytest

from core.views import _build_project_media_url


@pytest.mark.parametrize(
    ("media", "expected"),
    [
        (
            SimpleNamespace(
                signed_url="signed-url",
                archivo=SimpleNamespace(url="plain-url"),
            ),
            "signed-url",
        ),
        (
            SimpleNamespace(
                signed_url="",
                archivo=SimpleNamespace(url="plain-url"),
            ),
            "plain-url",
        ),
        (
            SimpleNamespace(
                archivo=SimpleNamespace(url="plain-url"),
            ),
            "plain-url",
        ),
    ],
)
def test_build_project_media_url_prefers_signed_url_and_falls_back_to_archivo_url(media, expected):
    original = dict(getattr(media, "__dict__", {}))

    assert _build_project_media_url(media) == expected
    assert dict(getattr(media, "__dict__", {})) == original
