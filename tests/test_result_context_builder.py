from __future__ import annotations

from copy import deepcopy

from core.views import _build_resultado_context


def test_build_resultado_context_preserves_inputs_and_overlay_precedence():
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
