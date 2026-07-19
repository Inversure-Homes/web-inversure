from __future__ import annotations

import pytest

from core.views import _build_responsable_label


class _UserLike:
    def __init__(self, full_name: str | None, username: str) -> None:
        self.full_name = full_name
        self.username = username

    def get_full_name(self) -> str | None:
        return self.full_name


@pytest.mark.parametrize(
    ("full_name", "username", "expected"),
    [
        (" Ana Pérez ", "aperez", "Ana Pérez"),
        ("", "aperez", "aperez"),
        (None, "aperez", "aperez"),
        ("   ", "aperez", ""),
        ("", "", ""),
    ],
)
def test_build_responsable_label_preserves_priorities_and_strip(full_name, username, expected):
    user = _UserLike(full_name, username)
    original = (user.full_name, user.username)

    assert _build_responsable_label(user) == expected
    assert (user.full_name, user.username) == original
