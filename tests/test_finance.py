import pytest

from core.finance import calc_inversor_settlement, calc_operacion_economica, retencion_pct_for_tipo_persona


def test_calc_operacion_economica_clamps_positive_benefit():
    result = calc_operacion_economica(beneficio_bruto=10000, comision_pct=10)
    assert result.beneficio_bruto == 10000.0
    assert result.comision_eur == 1000.0
    assert result.beneficio_neto_total == 9000.0


def test_calc_inversor_settlement_limits_losses_to_capital():
    result = calc_inversor_settlement(
        capital_invertido=1000,
        total_proyecto_invertido=1000,
        beneficio_bruto_operacion=-500,
    )
    assert result["retencion"] == 0.0
    assert result["total_a_percibir"] == 500.0
    assert result["roi_bruto_pct"] == -50.0


def test_calc_operacion_economica_preserves_overrides_and_clamps_commission_to_benefit():
    result = calc_operacion_economica(
        beneficio_bruto=1000,
        comision_pct=25,
        comision_eur=1200,
        override_bruto=750,
        override_comision_eur=900,
        override_beneficio_neto_total=500,
    )

    assert result.beneficio_bruto == 750.0
    assert result.comision_eur == 750.0
    assert result.beneficio_neto_total == 500.0


def test_calc_inversor_settlement_handles_zero_denominator_without_dividing_and_respects_loss_clamp():
    result = calc_inversor_settlement(
        capital_invertido=1000,
        total_proyecto_invertido=0,
        beneficio_bruto_operacion=-500,
        comision_pct=0,
        limit_loss_to_capital=False,
    )

    assert result["participacion_pct"] == 0.0
    assert result["beneficio_inversor"] == 0.0
    assert result["retencion"] == 0.0
    assert result["neto_cobrar"] == 0.0
    assert result["total_a_percibir"] == 1000.0
    assert result["roi_bruto_pct"] == 0.0
    assert result["roi_neto_pct"] == 0.0


def test_calc_inversor_settlement_uses_person_type_retention_override(monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setenv("INVERSOR_RETENCION_PCT_F", "17")
    monkeypatch.setenv("INVERSOR_RETENCION_PCT_J", "24")

    assert retencion_pct_for_tipo_persona("F") == 17.0
    assert retencion_pct_for_tipo_persona("J") == 24.0

    result = calc_inversor_settlement(
        capital_invertido=1000,
        total_proyecto_invertido=1000,
        beneficio_bruto_operacion=-1500,
        tipo_persona="J",
        comision_pct=0,
        limit_loss_to_capital=True,
    )

    assert result["retencion_pct"] == 24.0
    assert result["beneficio_inversor"] == -1500.0
    assert result["neto_cobrar"] == -1000.0
    assert result["total_a_percibir"] == 0.0
    assert result["roi_bruto_pct"] == -150.0
    assert result["roi_neto_pct"] == -100.0
