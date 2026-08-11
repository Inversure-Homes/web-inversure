from __future__ import annotations

from types import SimpleNamespace

import pytest

from core.views import _build_username_key


@pytest.mark.parametrize(
    ("user", "expected"),
    [
        (SimpleNamespace(username=" Miguel "), "miguel"),
        (SimpleNamespace(username="MiXedCase"), "mixedcase"),
        (SimpleNamespace(username=""), ""),
        (SimpleNamespace(username=None), ""),
        (SimpleNamespace(), ""),
    ],
)
def test_build_username_key_preserves_strip_lower_and_missing_values(user, expected):
    original = dict(getattr(user, "__dict__", {}))

    assert _build_username_key(user) == expected
    assert dict(getattr(user, "__dict__", {})) == original
