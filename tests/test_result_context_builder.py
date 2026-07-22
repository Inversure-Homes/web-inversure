from __future__ import annotations

from copy import deepcopy

from core.views import _build_resultado_context


def test_build_resultado_context_preserves_inputs_and_fill_only_precedence():
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
        "status": "memoria",
        "roi": 2,
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


def test_build_resultado_context_keeps_live_result_over_historical_snapshot():
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

    resultado = _build_resultado_context(resultado_calc, resultado_memoria, snap_result)

    assert resultado == {
        "roi": 16.37293283802096,
        "beneficio_neto": 26019.30,
        "impuesto_sociedades": 0.0,
        "mensaje": "Operacion viable",
    }
