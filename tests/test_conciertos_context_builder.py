from __future__ import annotations

from copy import deepcopy

from core.views import SafeAccessDict, _build_conciertos_context


def test_build_conciertos_context_preserves_alias_precedence_and_defaults():
    original = {
        "plazo": "12 meses",
        "interes": "5",
        "empresa": "Empresa base",
        "empresa_acuerdo": "Empresa acuerdo",
        "gasto": "1000",
        "liquidacion_fecha": "2026-07-18",
    }
    snapshot = deepcopy(original)

    result = _build_conciertos_context(original)

    assert isinstance(result, SafeAccessDict)
    assert result == {
        "plazo_acuerdo": "12 meses",
        "interes_acordado": "5",
        "empresa": "Empresa base",
        "empresa_acuerdo": "Empresa acuerdo",
        "gasto_solicitado": "1000",
        "fecha_liquidacion": "2026-07-18",
    }
    assert original == snapshot


def test_build_conciertos_context_handles_none_empty_and_alias_fallbacks():
    result = _build_conciertos_context(
        {
            "plazo_acuerdo": "",
            "plazo": "18 meses",
            "interes_acordado": "",
            "interes": "7",
            "empresa": "",
            "empresa_acuerdo": "Acuerdo SL",
            "gasto_solicitado": "",
            "gasto": "2500",
            "fecha_liquidacion": "",
            "liquidacion_fecha": "2026-08-01",
        }
    )

    assert result["plazo_acuerdo"] == "18 meses"
    assert result["interes_acordado"] == "7"
    assert result["empresa"] == "Acuerdo SL"
    assert result["empresa_acuerdo"] == "Acuerdo SL"
    assert result["gasto_solicitado"] == "2500"
    assert result["fecha_liquidacion"] == "2026-08-01"

    empty = _build_conciertos_context(None)
    assert empty == {
        "plazo_acuerdo": "",
        "interes_acordado": "",
        "empresa": "",
        "empresa_acuerdo": "",
        "gasto_solicitado": "",
        "fecha_liquidacion": "",
    }
