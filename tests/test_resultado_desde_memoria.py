from __future__ import annotations

from datetime import date
from decimal import Decimal

import pytest

from core import views as core_views
from core.models import GastoProyecto, IngresoProyecto

from .factories import ProyectoFactory

pytestmark = pytest.mark.django_db

EXPECTED_KEYS = {
    "beneficio_neto",
    "beneficio_neto_tras_impuestos",
    "impuesto_sociedades",
    "impuesto_sociedades_pct",
    "beneficio_neto_pre_impuestos",
    "roi",
    "inversion_total",
    "valor_adquisicion",
    "valor_transmision",
    "ratio_euro",
    "precio_minimo_venta",
    "colchon_seguridad",
    "margen_neto",
    "ajuste_precio_venta",
    "ajuste_gastos",
    "gastos_real_total",
    "gastos_est_total",
    "origen_memoria",
    "base_memoria_real",
}

FLOAT_KEYS = EXPECTED_KEYS - {"origen_memoria", "base_memoria_real"}


def _make_project(
    *,
    name: str,
    state: str = "cerrado",
    purchase_price: Decimal | None = Decimal("100000.00"),
    snapshot: dict | None = None,
):
    return ProyectoFactory(
        nombre=name,
        estado=state,
        fecha=date(2026, 1, 1),
        precio_propiedad=purchase_price,
        precio_compra_inmueble=purchase_price,
        snapshot_datos=snapshot or {},
        extra={},
    )


def _add_gasto(
    *,
    project,
    fecha: date,
    categoria: str,
    concepto: str,
    importe: Decimal,
    estado: str = "confirmado",
    imputable_inversores: bool = True,
):
    return GastoProyecto.objects.create(
        proyecto=project,
        fecha=fecha,
        categoria=categoria,
        concepto=concepto,
        importe=importe,
        importe_estimado=importe,
        importe_real=importe,
        estado=estado,
        imputable_inversores=imputable_inversores,
        pagado=True,
    )


def _add_ingreso(
    *,
    project,
    fecha: date,
    tipo: str,
    concepto: str,
    importe: Decimal,
    estado: str = "confirmado",
    imputable_inversores: bool = True,
):
    return IngresoProyecto.objects.create(
        proyecto=project,
        fecha=fecha,
        tipo=tipo,
        concepto=concepto,
        importe=importe,
        importe_estimado=importe,
        importe_real=importe,
        estado=estado,
        imputable_inversores=imputable_inversores,
        pagado=True,
    )


def _resultado(project, snapshot: dict | None = None, *, only_imputable_inversores: bool = False):
    return core_views._resultado_desde_memoria(
        project,
        snapshot or {},
        only_imputable_inversores=only_imputable_inversores,
    )


def _assert_public_types(result: dict) -> None:
    assert set(result) == EXPECTED_KEYS
    for key in FLOAT_KEYS:
        assert type(result[key]) is float, key
    assert type(result["origen_memoria"]) is bool
    assert type(result["base_memoria_real"]) is bool


def test_resultado_desde_memoria_returns_expected_keys_and_types_for_profitable_project():
    project = _make_project(name="Rentable")
    _add_gasto(
        project=project,
        fecha=date(2026, 1, 2),
        categoria="adquisicion",
        concepto="Compraventa inmueble",
        importe=Decimal("100000.00"),
    )
    _add_gasto(
        project=project,
        fecha=date(2026, 1, 10),
        categoria="legales",
        concepto="Notaría",
        importe=Decimal("2500.00"),
    )
    _add_ingreso(
        project=project,
        fecha=date(2026, 6, 1),
        tipo="venta",
        concepto="Venta final",
        importe=Decimal("140000.00"),
    )

    result = _resultado(project)

    _assert_public_types(result)
    assert result["origen_memoria"] is True
    assert result["base_memoria_real"] is True
    assert result["valor_adquisicion"] == pytest.approx(102500.0)
    assert result["valor_transmision"] == pytest.approx(140000.0)
    assert result["beneficio_neto"] == pytest.approx(37500.0)
    assert result["roi"] == pytest.approx(36.58536585365854)
    assert result["margen_neto"] == pytest.approx(26.785714285714285)


def test_resultado_desde_memoria_preserves_losses_and_negative_income_adjustments():
    project = _make_project(name="Pérdidas", state="descartado")
    _add_gasto(
        project=project,
        fecha=date(2026, 1, 2),
        categoria="adquisicion",
        concepto="Compraventa inmueble",
        importe=Decimal("100000.00"),
    )
    _add_ingreso(
        project=project,
        fecha=date(2026, 6, 1),
        tipo="venta",
        concepto="Venta final",
        importe=Decimal("90000.00"),
    )
    _add_ingreso(
        project=project,
        fecha=date(2026, 6, 2),
        tipo="devolucion",
        concepto="Devolución de reserva",
        importe=Decimal("-1000.00"),
    )

    result = _resultado(project)

    assert result["beneficio_neto"] == pytest.approx(-11000.0)
    assert result["roi"] == pytest.approx(-11.0)
    assert result["margen_neto"] == pytest.approx(-12.222222222222221)
    assert result["base_memoria_real"] is True


def test_resultado_desde_memoria_handles_zero_investment_total_without_dividing_by_zero():
    project = _make_project(name="Sin inversión", purchase_price=None)
    _add_ingreso(
        project=project,
        fecha=date(2026, 6, 1),
        tipo="venta",
        concepto="Venta",
        importe=Decimal("5000.00"),
    )

    result = _resultado(project)

    assert result["valor_adquisicion"] == pytest.approx(0.0)
    assert result["inversion_total"] == pytest.approx(0.0)
    assert result["beneficio_neto"] == pytest.approx(5000.0)
    assert result["roi"] == pytest.approx(0.0)
    assert result["ratio_euro"] == pytest.approx(0.0)
    assert result["margen_neto"] == pytest.approx(100.0)


def test_resultado_desde_memoria_uses_snapshot_for_acquisition_even_with_live_data():
    project = _make_project(name="Snapshot frente a vivo")
    _add_gasto(
        project=project,
        fecha=date(2026, 1, 2),
        categoria="adquisicion",
        concepto="Compraventa inmueble",
        importe=Decimal("100000.00"),
    )
    _add_gasto(
        project=project,
        fecha=date(2026, 1, 10),
        categoria="legales",
        concepto="Notaría",
        importe=Decimal("2500.00"),
    )
    _add_ingreso(
        project=project,
        fecha=date(2026, 6, 1),
        tipo="venta",
        concepto="Venta final",
        importe=Decimal("140000.00"),
    )

    snapshot = {
        "economico": {
            "valor_adquisicion_total": 150000.0,
            "valor_transmision": 300000.0,
            "beneficio": 999999.0,
        },
        "kpis": {
            "metricas": {
                "valor_adquisicion_total": 150000.0,
                "valor_transmision": 300000.0,
                "beneficio": 999999.0,
            }
        },
    }

    result = _resultado(project, snapshot)

    assert result["valor_adquisicion"] == pytest.approx(150000.0)
    assert result["beneficio_neto"] == pytest.approx(37500.0)
    assert result["valor_transmision"] == pytest.approx(140000.0)
    assert result["base_memoria_real"] is True


def test_resultado_desde_memoria_uses_snapshot_values_when_there_are_no_movements():
    project = _make_project(name="Snapshot sin movimientos", purchase_price=None)
    snapshot = {
        "economico": {
            "valor_adquisicion_total": 120000.0,
            "valor_transmision": 150000.0,
            "beneficio": 30000.0,
        },
        "kpis": {
            "metricas": {
                "valor_adquisicion_total": 120000.0,
                "valor_transmision": 150000.0,
                "beneficio": 30000.0,
            }
        },
    }

    result = _resultado(project, snapshot)

    assert result["valor_adquisicion"] == pytest.approx(120000.0)
    assert result["valor_transmision"] == pytest.approx(150000.0)
    assert result["beneficio_neto"] == pytest.approx(30000.0)
    assert result["roi"] == pytest.approx(25.0)
    assert result["margen_neto"] == pytest.approx(20.0)
    assert result["base_memoria_real"] is False


def test_resultado_desde_memoria_closed_projects_treat_anticipo_as_transmission():
    project = _make_project(name="Cerrado con anticipo", state="cerrado")
    _add_gasto(
        project=project,
        fecha=date(2026, 1, 2),
        categoria="adquisicion",
        concepto="Compraventa inmueble",
        importe=Decimal("100000.00"),
    )
    _add_ingreso(
        project=project,
        fecha=date(2026, 6, 1),
        tipo="anticipo",
        concepto="Cobro anticipo",
        importe=Decimal("109000.00"),
    )

    result = _resultado(project)

    assert result["valor_transmision"] == pytest.approx(109000.0)
    assert result["beneficio_neto"] == pytest.approx(9000.0)


def test_resultado_desde_memoria_respects_only_imputable_inversores_filter():
    project = _make_project(name="Filtro imputable")
    _add_gasto(
        project=project,
        fecha=date(2026, 1, 2),
        categoria="adquisicion",
        concepto="Compraventa inmueble",
        importe=Decimal("100000.00"),
    )
    _add_gasto(
        project=project,
        fecha=date(2026, 1, 15),
        categoria="otros",
        concepto="Gasto no imputable",
        importe=Decimal("15000.00"),
        imputable_inversores=False,
    )
    _add_ingreso(
        project=project,
        fecha=date(2026, 6, 1),
        tipo="venta",
        concepto="Venta",
        importe=Decimal("130000.00"),
    )
    _add_ingreso(
        project=project,
        fecha=date(2026, 6, 2),
        tipo="otro",
        concepto="Ingreso no imputable",
        importe=Decimal("5000.00"),
        imputable_inversores=False,
    )

    full_result = _resultado(project)
    imputable_result = _resultado(project, only_imputable_inversores=True)

    assert full_result["gastos_real_total"] == pytest.approx(115000.0)
    assert imputable_result["gastos_real_total"] == pytest.approx(100000.0)
    assert full_result["beneficio_neto"] == pytest.approx(20000.0)
    assert imputable_result["beneficio_neto"] == pytest.approx(30000.0)
    assert full_result["valor_transmision"] == pytest.approx(130000.0)
    assert imputable_result["valor_transmision"] == pytest.approx(130000.0)
