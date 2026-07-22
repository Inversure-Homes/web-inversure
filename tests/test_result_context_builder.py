from __future__ import annotations

from copy import deepcopy
from types import SimpleNamespace

from core.views import (
    _build_project_result_context,
    _build_resultado_context,
    _default_new_project_extra,
    _project_result_source_version,
    _project_uses_live_result_precedence,
)


def test_build_resultado_context_preserves_inputs_and_legacy_snapshot_precedence():
    resultado_calc = {
        "status": "calc",
        "roi": 1,
        "extra": "calc",
        "blank": "base",
        "mem_list": [1],
        "snap_list": [2],
        "keep_none": "base",
    }
    resultado_memoria = {
        "status": "memoria",
        "roi": 2,
        "extra": "memoria",
        "blank": "",
        "mem_list": [],
        "keep_none": None,
        "ignored": None,
    }
    snap_result = {
        "status": "snap",
        "roi": 3,
        "extra": [],
        "blank": [],
        "snap_list": [],
        "final": "snap",
    }

    original_calc = deepcopy(resultado_calc)
    original_memoria = deepcopy(resultado_memoria)
    original_snap = deepcopy(snap_result)

    resultado = _build_resultado_context(resultado_calc, resultado_memoria, snap_result)

    assert resultado == {
        "status": "snap",
        "roi": 3,
        "extra": "memoria",
        "blank": "base",
        "mem_list": [],
        "snap_list": [2],
        "keep_none": "base",
        "final": "snap",
    }
    assert resultado is not resultado_calc
    assert resultado_calc == original_calc
    assert resultado_memoria == original_memoria
    assert snap_result == original_snap


def test_build_resultado_context_fill_only_mode_keeps_live_result_over_historical_snapshot():
    resultado_calc = {
        "roi": 20.063014,
        "beneficio_neto": 31883.45,
    }
    resultado_memoria = {
        "roi": 16.37293283802096,
        "beneficio_neto": 26019.30,
        "impuesto_sociedades": 0.0,
    }
    snap_result = {
        "roi": 16.3729,
        "beneficio_neto": 26019.30,
        "mensaje": "Operacion viable",
    }

    resultado = _build_resultado_context(
        resultado_calc,
        resultado_memoria,
        snap_result,
        snapshot_fill_only=True,
    )

    assert resultado == {
        "roi": 16.37293283802096,
        "beneficio_neto": 26019.30,
        "impuesto_sociedades": 0.0,
        "mensaje": "Operacion viable",
    }


def test_project_result_source_version_defaults_to_legacy():
    proyecto = SimpleNamespace(extra={})

    assert _project_result_source_version(proyecto, {}) == 1
    assert _project_uses_live_result_precedence(proyecto, {}) is False


def test_project_result_source_version_uses_explicit_v2_flag():
    proyecto = SimpleNamespace(extra={"resultado_source_version": 2})

    assert _project_result_source_version(proyecto, {}) == 2
    assert _project_uses_live_result_precedence(proyecto, {}) is True


def test_default_new_project_extra_sets_resultado_source_version():
    assert _default_new_project_extra() == {"resultado_source_version": 2}
    assert _default_new_project_extra({"foo": "bar"}) == {
        "foo": "bar",
        "resultado_source_version": 2,
    }


def test_build_project_result_context_keeps_legacy_snapshot_for_existing_projects():
    proyecto = SimpleNamespace(extra={})
    resultado = _build_project_result_context(
        proyecto,
        {},
        {"roi": 50.0},
        {"roi": 40.0},
        {"roi": 16.3729},
    )

    assert resultado["roi"] == 16.3729


def test_build_project_result_context_prefers_live_values_for_version_two_projects():
    proyecto = SimpleNamespace(extra={"resultado_source_version": 2})
    resultado = _build_project_result_context(
        proyecto,
        {},
        {"roi": 50.0},
        {"roi": 40.0, "beneficio_neto": 26019.30},
        {"roi": 16.3729, "beneficio_neto": 25000.0, "mensaje": "Operacion viable"},
    )

    assert resultado == {
        "roi": 40.0,
        "beneficio_neto": 26019.30,
        "mensaje": "Operacion viable",
    }
