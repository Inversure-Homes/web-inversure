from __future__ import annotations

from types import SimpleNamespace

import pytest

from core import views as core_views
from core.views import _admin_notify_users, _build_admin_notification_body


@pytest.mark.parametrize(
    ("mensaje", "actor", "project_label", "expected"),
    [
        ("Aviso", "", "", "Aviso"),
        ("Aviso", "Miguel", "", "Aviso\nUsuario: Miguel"),
        ("Aviso", "", "Proyecto: 1", "Aviso\n\nProyecto: 1"),
        ("Aviso", "Miguel", "Proyecto: 1", "Aviso\n\nProyecto: 1\nUsuario: Miguel"),
    ],
)
def test_build_admin_notification_body_preserves_order_and_omits_empty_labels(mensaje, actor, project_label, expected):
    assert _build_admin_notification_body(mensaje, actor, project_label) == expected


def test_admin_notify_users_excludes_non_admin_username_bypass(monkeypatch):
    admin = SimpleNamespace(username="admin")
    mperez = SimpleNamespace(username="mperez")

    monkeypatch.setattr(core_views.User.objects, "filter", lambda **kwargs: [admin, mperez])
    monkeypatch.setattr(core_views, "is_admin_user", lambda user: getattr(user, "username", "") == "admin")
    monkeypatch.setattr(core_views, "is_direccion_user", lambda user: False)

    assert _admin_notify_users() == [admin]
