from __future__ import annotations

from copy import deepcopy

from core.views import SafeAccessDict, _build_project_snapshot_context


def test_build_project_snapshot_context_wraps_nested_values_and_keeps_inputs_immutable():
    snapshot = {
        "inmueble": {"estado": "ok"},
        "economico": {"roi": 12.34},
        "comite": {"decision": "sí"},
        "kpis": {"metricas": {"roi": 12.34}},
    }
    inv_calc = {"inversor": {"beneficio": 10}}
    resultado = {"roi": 12.34}
    metricas_raw = {"detalle": {"riesgo": "bajo"}}
    original = deepcopy((snapshot, inv_calc, resultado, metricas_raw))

    result = _build_project_snapshot_context(snapshot, inv_calc, resultado, metricas_raw)

    assert set(result) == {
        "snapshot",
        "inmueble",
        "economico",
        "inversor",
        "inv",
        "comite",
        "kpis",
        "metricas",
        "resultado",
    }
    assert isinstance(result["snapshot"], SafeAccessDict)
    assert result["snapshot"]["inmueble"]["estado"] == "ok"
    assert result["snapshot"]["kpis"]["metricas"]["roi"] == 12.34
    assert isinstance(result["inmueble"], SafeAccessDict)
    assert result["inmueble"] == SafeAccessDict({"estado": "ok"})
    assert result["economico"] == SafeAccessDict({"roi": 12.34})
    assert result["comite"] == SafeAccessDict({"decision": "sí"})
    assert result["inversor"] == SafeAccessDict({"inversor": {"beneficio": 10}})
    assert result["inv"] == result["inversor"]
    assert result["kpis"] == SafeAccessDict({"metricas": {"roi": 12.34}})
    assert result["metricas"] == SafeAccessDict({"detalle": {"riesgo": "bajo"}})
    assert result["resultado"] == SafeAccessDict({"roi": 12.34})
    assert snapshot == original[0]
    assert inv_calc == original[1]
    assert resultado == original[2]
    assert metricas_raw == original[3]


def test_build_project_snapshot_context_keeps_empty_sections_as_safe_access_dicts():
    result = _build_project_snapshot_context({}, {}, {}, {})

    assert result == {
        "snapshot": SafeAccessDict(),
        "inmueble": SafeAccessDict(),
        "economico": SafeAccessDict(),
        "inversor": SafeAccessDict(),
        "inv": SafeAccessDict(),
        "comite": SafeAccessDict(),
        "kpis": SafeAccessDict(),
        "metricas": SafeAccessDict(),
        "resultado": SafeAccessDict(),
    }
