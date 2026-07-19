from __future__ import annotations

import pytest

from core.views import _build_admin_notification_body


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
