from decimal import Decimal

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


def test_calc_inversor_settlement_uses_decimal_str_int_float_inputs_without_rounding():
    result = calc_inversor_settlement(
        capital_invertido=Decimal("1000.50"),
        total_proyecto_invertido="2000",
        beneficio_bruto_operacion=1500.1,
        comision_pct=10,
        comision_eur=None,
        retencion_pct=20,
        limit_loss_to_capital=False,
    )

    assert set(result) == {
        "beneficio_bruto",
        "comision_eur",
        "beneficio_neto_total",
        "participacion_pct",
        "capital_invertido",
        "beneficio_inversor",
        "retencion_pct",
        "retencion",
        "neto_cobrar",
        "total_a_percibir",
        "roi_bruto_pct",
        "roi_neto_pct",
    }
    assert all(isinstance(result[key], float) for key in result)
    assert result["beneficio_bruto"] == pytest.approx(1500.1)
    assert result["comision_eur"] == pytest.approx(150.01)
    assert result["beneficio_neto_total"] == pytest.approx(1350.09)
    assert result["participacion_pct"] == pytest.approx(50.025)
    assert result["capital_invertido"] == pytest.approx(1000.5)
    assert result["beneficio_inversor"] == pytest.approx(675.3825225)
    assert result["retencion_pct"] == pytest.approx(20.0)
    assert result["retencion"] == pytest.approx(135.0765045)
    assert result["neto_cobrar"] == pytest.approx(540.306018)
    assert result["total_a_percibir"] == pytest.approx(1540.806018)
    assert result["roi_bruto_pct"] == pytest.approx(67.5045)
    assert result["roi_neto_pct"] == pytest.approx(54.0036)


def test_calc_inversor_settlement_treats_none_and_empty_strings_as_zero():
    result = calc_inversor_settlement(
        capital_invertido=None,
        total_proyecto_invertido="",
        beneficio_bruto_operacion=None,
        comision_pct="",
        comision_eur="",
        retencion_pct=0,
        limit_loss_to_capital=False,
    )

    assert result["beneficio_bruto"] == 0.0
    assert result["comision_eur"] == 0.0
    assert result["beneficio_neto_total"] == 0.0
    assert result["participacion_pct"] == 0.0
    assert result["capital_invertido"] == 0.0
    assert result["beneficio_inversor"] == 0.0
    assert result["retencion_pct"] == 0.0
    assert result["retencion"] == 0.0
    assert result["neto_cobrar"] == 0.0
    assert result["total_a_percibir"] == 0.0
    assert result["roi_bruto_pct"] == 0.0
    assert result["roi_neto_pct"] == 0.0


def test_calc_inversor_settlement_keeps_boolean_compatibility_for_legacy_float_boundary():
    result = calc_inversor_settlement(
        capital_invertido=True,
        total_proyecto_invertido=2,
        beneficio_bruto_operacion=True,
        comision_pct=False,
        comision_eur="",
        retencion_pct=True,
        limit_loss_to_capital=False,
    )

    assert result["capital_invertido"] == 1.0
    assert result["beneficio_bruto"] == 1.0
    assert result["comision_eur"] == 0.0
    assert result["beneficio_neto_total"] == 1.0
    assert result["participacion_pct"] == 50.0
    assert result["beneficio_inversor"] == 0.5
    assert result["retencion_pct"] == 1.0
    assert result["retencion"] == 0.005
    assert result["neto_cobrar"] == 0.495
    assert result["total_a_percibir"] == 1.495
    assert result["roi_bruto_pct"] == 50.0
    assert result["roi_neto_pct"] == 49.5


def test_calc_inversor_settlement_keeps_roi_at_zero_when_capital_is_zero():
    result = calc_inversor_settlement(
        capital_invertido=0,
        total_proyecto_invertido=100,
        beneficio_bruto_operacion=100,
        comision_pct=10,
        retencion_pct=0,
        limit_loss_to_capital=False,
    )

    assert result["participacion_pct"] == 0.0
    assert result["beneficio_inversor"] == 0.0
    assert result["retencion"] == 0.0
    assert result["neto_cobrar"] == 0.0
    assert result["total_a_percibir"] == 0.0
    assert result["roi_bruto_pct"] == 0.0
    assert result["roi_neto_pct"] == 0.0


@pytest.mark.parametrize(("retencion_pct", "expected_retencion"), [(-10, 0.0), (150, 100.0)])
def test_calc_inversor_settlement_clamps_retencion_pct_bounds(retencion_pct, expected_retencion):
    result = calc_inversor_settlement(
        capital_invertido=100,
        total_proyecto_invertido=100,
        beneficio_bruto_operacion=100,
        comision_pct=0,
        retencion_pct=retencion_pct,
        limit_loss_to_capital=False,
    )

    assert result["beneficio_inversor"] == 100.0
    assert result["retencion_pct"] == expected_retencion
    assert result["retencion"] == expected_retencion
    assert result["neto_cobrar"] == pytest.approx(100.0 - expected_retencion)
    assert result["total_a_percibir"] == pytest.approx(200.0 - expected_retencion)
    assert result["roi_bruto_pct"] == 100.0
    assert result["roi_neto_pct"] == pytest.approx(100.0 - expected_retencion)


def test_calc_inversor_settlement_respects_override_precedence():
    result = calc_inversor_settlement(
        capital_invertido=100,
        total_proyecto_invertido=100,
        beneficio_bruto_operacion=1000,
        comision_pct=10,
        retencion_pct=30,
        operacion_override={
            "beneficio_bruto": 200,
            "comision_eur": 50,
            "beneficio_neto_total": 300,
        },
        inversor_override={
            "beneficio_inversor": 123.45,
            "retencion_pct": 7,
            "retencion": 5,
            "neto_cobrar": 100,
        },
        limit_loss_to_capital=False,
    )

    assert result["beneficio_bruto"] == 200.0
    assert result["comision_eur"] == 50.0
    assert result["beneficio_neto_total"] == 300.0
    assert result["beneficio_inversor"] == 123.45
    assert result["retencion_pct"] == 7.0
    assert result["retencion"] == 5.0
    assert result["neto_cobrar"] == 100.0
    assert result["total_a_percibir"] == 200.0
    assert result["participacion_pct"] == 100.0
    assert result["roi_bruto_pct"] == 123.45
    assert result["roi_neto_pct"] == 100.0


def test_calc_inversor_settlement_leaves_negative_total_when_loss_clamp_is_disabled():
    result = calc_inversor_settlement(
        capital_invertido=100,
        total_proyecto_invertido=100,
        beneficio_bruto_operacion=-250,
        comision_pct=0,
        retencion_pct=0,
        limit_loss_to_capital=False,
    )

    assert result["beneficio_inversor"] == -250.0
    assert result["retencion"] == 0.0
    assert result["neto_cobrar"] == -250.0
    assert result["total_a_percibir"] == -150.0
    assert result["roi_bruto_pct"] == -250.0
    assert result["roi_neto_pct"] == -250.0


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


@pytest.mark.parametrize(
    ("kwargs", "expected"),
    [
        (
            {"beneficio_bruto": Decimal("1000.10"), "comision_pct": "12.5"},
            {"beneficio_bruto": 1000.1, "comision_eur": 125.0125, "beneficio_neto_total": 875.0875},
        ),
        (
            {"beneficio_bruto": 1000, "comision_pct": None},
            {"beneficio_bruto": 1000.0, "comision_eur": 0.0, "beneficio_neto_total": 1000.0},
        ),
        (
            {"beneficio_bruto": -250.5, "comision_pct": 99},
            {"beneficio_bruto": -250.5, "comision_eur": 0.0, "beneficio_neto_total": -250.5},
        ),
    ],
)
def test_calc_operacion_economica_handles_numeric_variants_without_changing_the_external_contract(kwargs, expected):
    result = calc_operacion_economica(**kwargs)

    assert result.beneficio_bruto == pytest.approx(expected["beneficio_bruto"])
    assert result.comision_eur == pytest.approx(expected["comision_eur"])
    assert result.beneficio_neto_total == pytest.approx(expected["beneficio_neto_total"])


def test_calc_operacion_economica_keeps_boolean_compatibility_for_float_contract():
    # Compatibilidad legacy: el contrato anterior basado en float aceptaba True/False como 1.0/0.0.
    result = calc_operacion_economica(beneficio_bruto=True, comision_pct=False)

    assert result.beneficio_bruto == 1.0
    assert result.comision_eur == 0.0
    assert result.beneficio_neto_total == 1.0


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
