from __future__ import annotations

import pytest

from core.views import _build_responsable_label, _build_user_display_name


class _UserLike:
    def __init__(self, full_name: str | None, username: str) -> None:
        self.full_name = full_name
        self.username = username

    def get_full_name(self) -> str | None:
        return self.full_name

    def get_username(self) -> str:
        return self.username


class _UserLikeWithCustomUsername(_UserLike):
    def get_username(self) -> str:
        return "username-method"


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


@pytest.mark.parametrize(
    ("full_name", "username", "expected"),
    [
        (" Ana Pérez ", "aperez", " Ana Pérez "),
        ("", "aperez", "aperez"),
        (None, "aperez", "aperez"),
        ("   ", "aperez", "   "),
    ],
)
def test_build_user_display_name_preserves_raw_fallback(full_name, username, expected):
    user = _UserLike(full_name, username)
    original = (user.full_name, user.username)

    assert _build_user_display_name(user) == expected
    assert (user.full_name, user.username) == original


def test_build_user_display_name_can_prefer_get_username():
    user = _UserLikeWithCustomUsername("", "username-attr")

    assert _build_user_display_name(user, prefer_get_username=True) == "username-method"
