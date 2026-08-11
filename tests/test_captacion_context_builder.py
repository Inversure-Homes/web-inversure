from __future__ import annotations

from core.views import SafeAccessDict, _build_captacion_context


def test_build_captacion_context_preserves_clamps_formats_and_type():
    result = _build_captacion_context(100000.0, 60000.0)

    assert isinstance(result, SafeAccessDict)
    assert result == {
        "capital_objetivo": 100000.0,
        "capital_captado": 60000.0,
        "pct_captado": 60.0,
        "restante": 40000.0,
        "pct_restante": 40.0,
        "capital_objetivo_fmt": "100.000,00 €",
        "capital_captado_fmt": "60.000,00 €",
        "restante_fmt": "40.000,00 €",
        "pct_captado_fmt": "60,00 %",
        "pct_restante_fmt": "40,00 %",
    }


def test_build_captacion_context_handles_zero_negative_and_over_capture():
    zero = _build_captacion_context(0.0, 25000.0)
    negative = _build_captacion_context(-100.0, -50.0)
    over = _build_captacion_context(100.0, 150.0)

    assert zero["pct_captado"] == 0.0
    assert zero["pct_restante"] == 100.0
    assert zero["restante"] == 0.0
    assert zero["capital_objetivo_fmt"] == "0,00 €"
    assert zero["capital_captado_fmt"] == "25.000,00 €"
    assert zero["restante_fmt"] == "0,00 €"
    assert zero["pct_captado_fmt"] == "0,00 %"
    assert zero["pct_restante_fmt"] == "100,00 %"

    assert negative["capital_objetivo"] == 0.0
    assert negative["capital_captado"] == 0.0
    assert negative["pct_captado"] == 0.0
    assert negative["restante"] == 0.0
    assert negative["pct_restante"] == 100.0
    assert negative["capital_objetivo_fmt"] == "0,00 €"
    assert negative["capital_captado_fmt"] == "0,00 €"
    assert negative["restante_fmt"] == "0,00 €"
    assert negative["pct_captado_fmt"] == "0,00 %"
    assert negative["pct_restante_fmt"] == "100,00 %"

    assert over["capital_objetivo"] == 100.0
    assert over["capital_captado"] == 150.0
    assert over["pct_captado"] == 100.0
    assert over["restante"] == 0.0
    assert over["pct_restante"] == 0.0
    assert over["capital_objetivo_fmt"] == "100,00 €"
    assert over["capital_captado_fmt"] == "150,00 €"
    assert over["restante_fmt"] == "0,00 €"
    assert over["pct_captado_fmt"] == "100,00 %"
    assert over["pct_restante_fmt"] == "0,00 %"
