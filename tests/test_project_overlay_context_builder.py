from __future__ import annotations

from copy import deepcopy

from core.views import _build_checklist_users_context, _build_project_overlay_context


class _UserLike:
    def __init__(self, user_id: int, full_name: str, username: str) -> None:
        self.id = user_id
        self._full_name = full_name
        self.username = username

    def get_full_name(self) -> str:
        return self._full_name


def test_build_project_overlay_context_preserves_precedence_defaults_and_immutability():
    extra = {
        "landing": {"imagen_id": 11, "beneficio_neto_pct": "18"},
        "publicaciones": {"cabecera_imagen_id": 22},
        "difusion": {"anexos": {"a": True, "b": False}},
        "pending_estado_notif": {"estado": "cerrado"},
    }
    overlay = {
        "landing": {"imagen_id": 99, "beneficio_neto_pct": "12"},
        "publicaciones": {"cabecera_imagen_id": 33},
        "difusion": {"anexos": {"c": True}},
        "pending_estado_notif": {"estado": "abierto"},
    }

    original_extra = deepcopy(extra)
    original_overlay = deepcopy(overlay)

    result = _build_project_overlay_context(extra, overlay)

    assert result == {
        "landing_config": {"imagen_id": 11, "beneficio_neto_pct": "18"},
        "publicaciones_config": {"cabecera_imagen_id": 22},
        "difusion_config": {"anexos": {"a": True, "b": False}},
        "pending_estado_notif": {"estado": "cerrado"},
        "difusion_anexos_ids": {"a"},
    }
    assert extra == original_extra
    assert overlay == original_overlay


def test_build_project_overlay_context_falls_back_and_defaults_when_missing():
    result = _build_project_overlay_context(
        {
            "landing": {},
            "publicaciones": "",
            "difusion": {},
        },
        {
            "landing": {"imagen_id": 7},
            "publicaciones": {"cabecera_imagen_id": 8},
            "difusion": {"anexos": {"x": True, "y": False}},
        },
    )

    assert result["landing_config"] == {"imagen_id": 7}
    assert result["publicaciones_config"] == {"cabecera_imagen_id": 8}
    assert result["difusion_config"] == {"anexos": {"x": True, "y": False}}
    assert result["pending_estado_notif"] is None
    assert result["difusion_anexos_ids"] == {"x"}

    empty = _build_project_overlay_context(None, None)
    assert empty == {
        "landing_config": {},
        "publicaciones_config": {},
        "difusion_config": {},
        "pending_estado_notif": None,
        "difusion_anexos_ids": set(),
    }


def test_build_checklist_users_context_preserves_order_and_fallbacks():
    usuarios = [
        _UserLike(3, " Miguel Pérez ", "mperez"),
        _UserLike(1, "", "usuario1"),
        _UserLike(2, "", ""),
    ]
    original = deepcopy([(u.id, u.get_full_name(), u.username) for u in usuarios])

    result = _build_checklist_users_context(usuarios)

    assert result == [
        {"id": 3, "label": "Miguel Pérez"},
        {"id": 1, "label": "usuario1"},
        {"id": 2, "label": ""},
    ]
    assert [(u.id, u.get_full_name(), u.username) for u in usuarios] == original
    assert _build_checklist_users_context([]) == []
