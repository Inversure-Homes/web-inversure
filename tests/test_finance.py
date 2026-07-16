from core.finance import calc_inversor_settlement, calc_operacion_economica


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
