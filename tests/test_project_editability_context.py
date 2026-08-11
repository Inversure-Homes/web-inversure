from __future__ import annotations

from core.views import _build_project_editability_flags


def test_build_project_editability_flags_keeps_base_state_for_open_projects():
    assert _build_project_editability_flags(True, "abierto") == (True, True)
    assert _build_project_editability_flags(False, "abierto") == (False, False)


def test_build_project_editability_flags_blocks_closed_states_without_changing_editable_estado():
    assert _build_project_editability_flags(True, "cerrado") == (False, True)
    assert _build_project_editability_flags(True, "cerrado_positivo") == (False, True)
    assert _build_project_editability_flags(True, "cerrado_negativo") == (False, True)
    assert _build_project_editability_flags(True, "finalizado") == (False, True)
    assert _build_project_editability_flags(True, "descartado") == (False, True)
