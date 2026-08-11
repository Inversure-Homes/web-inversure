from __future__ import annotations

from datetime import timedelta
from decimal import Decimal
from types import SimpleNamespace
from unittest.mock import patch

import pytest
from django.urls import reverse
from django.utils import timezone

from accounts.models import UserAccess
from core.decimal_utils import ZERO, to_decimal
from core.models import ChecklistItem, GastoProyecto, IngresoProyecto, Participacion, SolicitudParticipacion
from core.services.financial_dashboard import (
    FinancialDashboardFilters,
    FinancialDashboardService,
    _build_project_metric_row,
    build_financial_dashboard_data,
)

from .factories import ClienteFactory, InversorPerfilFactory, ProyectoFactory, UserAccessFactory, UserFactory

pytestmark = pytest.mark.django_db


def _build_service_dataset():
    today = timezone.localdate()

    user = UserFactory()
    UserAccessFactory(user=user, role=UserAccess.ROLE_DIRECCION)

    cliente_cerrado = ClienteFactory(cuota_abonada=True)
    cliente_activo = ClienteFactory(cuota_abonada=False)
    InversorPerfilFactory(cliente=cliente_cerrado)
    inversor_activo = InversorPerfilFactory(cliente=cliente_activo)

    proyecto_cerrado = ProyectoFactory(nombre="Proyecto Cerrado", estado="cerrado")
    proyecto_activo = ProyectoFactory(nombre="Proyecto Activo", estado="captacion")

    Participacion.objects.create(
        proyecto=proyecto_cerrado,
        cliente=cliente_cerrado,
        importe_invertido=Decimal("6000.00"),
        estado="confirmada",
        fecha_aportacion=today - timedelta(days=35),
    )
    Participacion.objects.create(
        proyecto=proyecto_activo,
        cliente=cliente_activo,
        importe_invertido=Decimal("4000.00"),
        estado="confirmada",
        fecha_aportacion=today - timedelta(days=5),
    )

    GastoProyecto.objects.create(
        proyecto=proyecto_cerrado,
        fecha=today - timedelta(days=60),
        categoria="adquisicion",
        concepto="Compra",
        importe=Decimal("12000.00"),
        importe_real=Decimal("12000.00"),
        estado="confirmado",
        imputable_inversores=True,
        pagado=True,
    )
    IngresoProyecto.objects.create(
        proyecto=proyecto_cerrado,
        fecha=today - timedelta(days=15),
        tipo="venta",
        concepto="Venta",
        importe=Decimal("18000.00"),
        importe_real=Decimal("18000.00"),
        estado="confirmado",
        imputable_inversores=True,
        pagado=True,
    )
    GastoProyecto.objects.create(
        proyecto=proyecto_activo,
        fecha=today - timedelta(days=12),
        categoria="operativos",
        concepto="Marketing",
        importe=Decimal("2500.00"),
        importe_real=Decimal("2500.00"),
        estado="estimado",
        imputable_inversores=True,
        pagado=False,
    )
    IngresoProyecto.objects.create(
        proyecto=proyecto_activo,
        fecha=today - timedelta(days=10),
        tipo="senal",
        concepto="Señal",
        importe=Decimal("7000.00"),
        importe_real=Decimal("7000.00"),
        estado="estimado",
        imputable_inversores=True,
        pagado=False,
    )

    ChecklistItem.objects.create(
        proyecto=proyecto_cerrado,
        fase="operacion",
        titulo="Tarea vencida",
        responsable="Operaciones",
        responsable_user=user,
        fecha_objetivo=today - timedelta(days=2),
        estado="pendiente",
    )
    ChecklistItem.objects.create(
        proyecto=proyecto_activo,
        fase="venta",
        titulo="Tarea en curso",
        responsable="Ventas",
        responsable_user=user,
        fecha_objetivo=today + timedelta(days=7),
        estado="en_curso",
    )

    SolicitudParticipacion.objects.create(
        proyecto=proyecto_activo,
        inversor=inversor_activo,
        importe_solicitado=Decimal("1500.00"),
        estado="pendiente",
    )

    project_payloads = {
        proyecto_cerrado.id: {
            "beneficio_neto": 1200.0,
            "valor_adquisicion": 20000.0,
            "roi": 6.0,
            "beneficio_neto_tras_impuestos": 1100.0,
            "ratio_euro": 1.2,
            "margen_neto": 0.1,
            "inversion_total": 20000.0,
            "gastos_real_total": 6500.0,
            "gastos_est_total": 7000.0,
            "base_memoria_real": True,
            "has_movimientos": True,
        },
        proyecto_activo.id: {
            "beneficio_neto": 400.0,
            "valor_adquisicion": 10000.0,
            "roi": -3.0,
            "beneficio_neto_tras_impuestos": 350.0,
            "ratio_euro": 0.8,
            "margen_neto": 0.05,
            "inversion_total": 10000.0,
            "gastos_real_total": 2500.0,
            "gastos_est_total": 2000.0,
            "base_memoria_real": False,
            "has_movimientos": True,
        },
    }

    memory_payloads = {
        proyecto_cerrado.id: {"beneficio_estimado": 1000.0, "beneficio_real": 1200.0, "has_movimientos": True},
        proyecto_activo.id: {"beneficio_estimado": 500.0, "beneficio_real": 400.0, "has_movimientos": True},
    }

    capital_objetivo = {
        proyecto_cerrado.id: Decimal("25000.00"),
        proyecto_activo.id: Decimal("10000.00"),
    }

    return {
        "user": user,
        "proyectos": {
            "cerrado": proyecto_cerrado,
            "activo": proyecto_activo,
        },
        "project_payloads": project_payloads,
        "memory_payloads": memory_payloads,
        "capital_objetivo": capital_objetivo,
    }


def _fake_core_views_factory(dataset):
    def _fake_get_snapshot_comunicacion(project):
        return {"inversor": {"comision_inversure_pct": 0.0}}

    def _fake_resultado_desde_memoria(project, snapshot):
        return dataset["project_payloads"][project.id]

    def _fake_capital_objetivo_desde_memoria(project, snapshot):
        return dataset["capital_objetivo"][project.id]

    def _fake_beneficio_estimado_real_memoria(project):
        return dataset["memory_payloads"][project.id]

    return SimpleNamespace(
        _get_snapshot_comunicacion=_fake_get_snapshot_comunicacion,
        _resultado_desde_memoria=_fake_resultado_desde_memoria,
        _capital_objetivo_desde_memoria=_fake_capital_objetivo_desde_memoria,
        _beneficio_estimado_real_memoria=_fake_beneficio_estimado_real_memoria,
    )


def _fake_settlement(*, capital_invertido, total_proyecto_invertido, beneficio_bruto_operacion, **kwargs):
    roi = (beneficio_bruto_operacion / total_proyecto_invertido * 100.0) if total_proyecto_invertido else 0.0
    return {
        "total_a_percibir": capital_invertido + beneficio_bruto_operacion,
        "neto_cobrar": beneficio_bruto_operacion,
        "roi_bruto_pct": roi,
        "roi_neto_pct": roi / 2.0,
    }


def _legacy_dashboard_to_decimal(value, default=ZERO):
    if value is None or value == "":
        return default
    if isinstance(value, Decimal):
        return value
    try:
        return Decimal(str(value))
    except Exception:
        return default


def test_financial_dashboard_filters_normalize_inputs():
    filters = FinancialDashboardFilters.from_mapping(
        {
            "fecha_desde": "2026-07-10",
            "fecha_hasta": "2026-07-01",
            "proyecto": "42",
            "estado_proyecto": "CERRADO",
        }
    )

    assert filters.fecha_desde.isoformat() == "2026-07-01"
    assert filters.fecha_hasta.isoformat() == "2026-07-10"
    assert filters.proyecto_id == 42
    assert filters.estado == "cerrado"
    assert filters.to_dict() == {
        "fecha_desde": "2026-07-01",
        "fecha_hasta": "2026-07-10",
        "proyecto_id": 42,
        "estado": "cerrado",
    }


def test_financial_dashboard_service_builds_structured_payload():
    dataset = _build_service_dataset()
    fake_core_views = _fake_core_views_factory(dataset)

    with (
        patch("core.services.financial_dashboard._core_views", return_value=fake_core_views),
        patch("core.services.financial_dashboard.calc_inversor_settlement", side_effect=_fake_settlement),
    ):
        payload = FinancialDashboardService(dataset["user"]).build()
        alias_payload = build_financial_dashboard_data(dataset["user"])

    assert payload["meta"]["cache_key"].startswith("financial-dashboard:")
    assert payload["meta"]["cache_ready"] is True
    assert alias_payload["meta"]["cache_key"] == payload["meta"]["cache_key"]
    assert payload["filters"] == {
        "fecha_desde": None,
        "fecha_hasta": None,
        "proyecto_id": None,
        "estado": None,
    }
    assert payload["scope"] == {
        "project_count": 2,
        "active_project_count": 1,
        "finalized_project_count": 1,
        "has_filters": False,
    }

    assert payload["kpis"]["capital_total_invertido"] == Decimal("10000.00")
    assert payload["kpis"]["capital_actual"] == Decimal("4000.00")
    assert payload["kpis"]["capital_en_vigor"] == Decimal("10000.00")
    assert payload["kpis"]["inversores_activos"] == 1
    assert payload["kpis"]["inversores_cuota"] == 1
    assert payload["kpis"]["operaciones"] == 2
    assert float(payload["kpis"]["beneficio_total"]) == pytest.approx(1600.0)
    assert float(payload["kpis"]["roi_medio"]) == pytest.approx(1.5)

    assert payload["period"] == {
        "applied": False,
        "fecha_desde": None,
        "fecha_hasta": None,
        "proyecto_id": None,
        "estado": None,
        "project_count": 2,
        "range_days": None,
    }

    state_distribution = {item["estado"]: item for item in payload["charts"]["state_distribution"]}
    assert state_distribution["captacion"]["total"] == 1
    assert state_distribution["captacion"]["pct"] == pytest.approx(50.0)
    assert state_distribution["cerrado"]["total"] == 1
    assert state_distribution["cerrado"]["pct"] == pytest.approx(50.0)
    assert payload["charts"]["benefit_bars"][0]["nombre"] == "Proyecto Cerrado"
    assert payload["charts"]["benefit_bars"][0]["valor_fmt"] == "1.200,00 €"
    assert payload["charts"]["benefit_bars"][0]["pct_fmt"] == "6,00 %"
    assert payload["charts"]["deviation"][0]["project_id"] == dataset["proyectos"]["cerrado"].id
    assert payload["charts"]["deviation"][0]["delta"] == pytest.approx(200.0)

    assert payload["rankings"]["best_roi"][0]["project_id"] == dataset["proyectos"]["cerrado"].id
    assert payload["rankings"]["worst_roi"][0]["project_id"] == dataset["proyectos"]["activo"].id
    assert payload["rankings"]["best_benefit"][0]["project_id"] == dataset["proyectos"]["cerrado"].id
    assert payload["rankings"]["worst_benefit"][0]["project_id"] == dataset["proyectos"]["activo"].id
    assert payload["rankings"]["investment_return"][0]["project_id"] == dataset["proyectos"]["cerrado"].id

    assert payload["alerts"]["operational"]["pendientes"] == 2
    assert payload["alerts"]["operational"]["vencidas"] == 1
    assert payload["alerts"]["operational"]["items"][0]["titulo"] == "Tarea vencida"
    assert payload["alerts"]["financial"]["pending_solicitudes"] == 1
    assert payload["alerts"]["financial"]["negative_roi_projects"][0]["project_id"] == dataset["proyectos"]["activo"].id
    assert payload["alerts"]["financial"]["over_budget_projects"][0]["project_id"] == dataset["proyectos"]["activo"].id
    assert payload["alerts"]["financial"]["missing_facturas"][0]["project_id"] == dataset["proyectos"]["cerrado"].id
    assert (
        payload["alerts"]["financial"]["missing_justificantes"][0]["project_id"] == dataset["proyectos"]["cerrado"].id
    )
    assert payload["alerts"]["summary"] == {"total": 7, "critical": 0, "warning": 4, "info": 1}

    assert payload["series"]["monthly"]["investment"]
    assert payload["series"]["monthly"]["income"]
    assert payload["series"]["monthly"]["expense"]
    assert payload["series"]["monthly"]["performance"]
    assert {item["project_id"] for item in payload["projects"]} == {
        dataset["proyectos"]["cerrado"].id,
        dataset["proyectos"]["activo"].id,
    }


def test_financial_dashboard_cache_key_changes_when_payload_changes():
    dataset = _build_service_dataset()
    service = FinancialDashboardService(dataset["user"])
    project = SimpleNamespace(id=dataset["proyectos"]["activo"].id, estado=dataset["proyectos"]["activo"].estado)

    metrics_a = [{"project_id": project.id, "estado": project.estado, "beneficio_neto": 10.0}]
    metrics_b = [{"project_id": project.id, "estado": project.estado, "beneficio_neto": 20.0}]

    with (
        patch.object(service, "_load_projects", return_value=[project]),
        patch.object(service, "_build_summary", return_value={"kpi": 1}),
        patch.object(service, "_build_period_summary", return_value={"period": "fixed"}),
        patch.object(service, "_build_charts", return_value={"charts": "fixed"}),
        patch.object(service, "_build_series", return_value={"series": "fixed"}),
        patch.object(service, "_build_rankings", return_value={"rankings": "fixed"}),
        patch.object(service, "_build_alerts", return_value={"alerts": "fixed"}),
        patch.object(service, "_build_project_metrics", side_effect=[metrics_a, metrics_b]),
    ):
        payload_a = service.build()
        payload_b = service.build()

    assert payload_a["meta"]["cache_key"].startswith("financial-dashboard:")
    assert payload_b["meta"]["cache_key"].startswith("financial-dashboard:")
    assert payload_a["meta"]["cache_key"] != payload_b["meta"]["cache_key"]


def test_build_project_metric_row_preserves_projection_and_inputs():
    project = SimpleNamespace(
        id=7,
        codigo_proyecto="PR-007",
        nombre="  Proyecto Demo  ",
        estado="captacion",
        datos_economicos=SimpleNamespace(estado_operativo="en marcha"),
        get_estado_display=lambda: "Captación",
    )
    resultado = {
        "beneficio_neto": 420.0,
        "valor_adquisicion": 1200.0,
        "roi": 7.5,
        "beneficio_neto_tras_impuestos": 390.0,
        "ratio_euro": 1.25,
        "margen_neto": 0.2,
        "inversion_total": 3000.0,
        "gastos_real_total": 800.0,
        "gastos_est_total": 900.0,
        "base_memoria_real": False,
    }
    beneficio_memoria = {"beneficio_estimado": 100.0, "beneficio_real": 160.0, "has_movimientos": True}
    operacion = {"beneficio_bruto": 500.0, "beneficio_neto_total": 450.0, "comision_eur": 50.0}
    settlement = {
        "capital_invertido": Decimal("1000.00"),
        "beneficio_neto": Decimal("20.00"),
        "retorno_total": Decimal("1020.00"),
        "roi_bruto_medio": 5.0,
        "roi_neto_medio": 2.5,
        "participaciones": 3,
    }
    resultado_original = dict(resultado)
    beneficio_memoria_original = dict(beneficio_memoria)
    operacion_original = dict(operacion)
    settlement_original = dict(settlement)

    row = _build_project_metric_row(
        project=project,
        resultado=resultado,
        beneficio_memoria=beneficio_memoria,
        operacion=operacion,
        settlement=settlement,
        capital_objetivo=Decimal("25000.00"),
        capital_captado=Decimal("10000.00"),
        capital_pendiente=Decimal("15000.00"),
        participaciones_confirmadas=[SimpleNamespace(), SimpleNamespace(), SimpleNamespace()],
    )

    assert row["project_id"] == 7
    assert row["codigo_proyecto"] == "PR-007"
    assert row["nombre"] == "Proyecto Demo"
    assert row["estado"] == "captacion"
    assert row["estado_label"] == "Captación"
    assert row["estado_operativo"] == "en marcha"
    assert row["capital_objetivo"] == Decimal("25000.00")
    assert row["capital_captado"] == Decimal("10000.00")
    assert row["capital_pendiente"] == Decimal("15000.00")
    assert row["beneficio_estimado"] == pytest.approx(100.0)
    assert row["beneficio_real"] == pytest.approx(160.0)
    assert row["beneficio_neto"] == pytest.approx(420.0)
    assert row["beneficio_bruto_operacion"] == pytest.approx(500.0)
    assert row["beneficio_neto_operacion"] == pytest.approx(450.0)
    assert row["beneficio_inversure"] == pytest.approx(50.0)
    assert row["beneficio_neto_tras_impuestos"] == pytest.approx(390.0)
    assert row["roi"] == pytest.approx(7.5)
    assert row["ratio_euro"] == pytest.approx(1.25)
    assert row["margen_neto"] == pytest.approx(0.2)
    assert row["inversion_total"] == pytest.approx(3000.0)
    assert row["valor_adquisicion"] == pytest.approx(1200.0)
    assert row["gastos_real_total"] == pytest.approx(800.0)
    assert row["gastos_est_total"] == pytest.approx(900.0)
    assert row["deviation"] == {
        "estimado": pytest.approx(100.0),
        "real": pytest.approx(160.0),
        "delta": pytest.approx(60.0),
        "delta_pct": pytest.approx(60.0),
    }
    assert row["investment_return"] is settlement
    assert row["participaciones_confirmadas"] == 3
    assert row["has_movimientos"] is True
    assert row["base_memoria_real"] is False
    assert resultado == resultado_original
    assert beneficio_memoria == beneficio_memoria_original
    assert operacion == operacion_original
    assert settlement == settlement_original


def test_financial_dashboard_service_applies_project_state_and_date_filters():
    dataset = _build_service_dataset()
    today = timezone.localdate()
    start = today.replace(day=1)
    filters = FinancialDashboardFilters.from_mapping(
        {
            "fecha_desde": start.isoformat(),
            "fecha_hasta": today.isoformat(),
            "proyecto_id": dataset["proyectos"]["activo"].id,
            "estado": "captacion",
        }
    )
    fake_core_views = _fake_core_views_factory(dataset)

    with (
        patch("core.services.financial_dashboard._core_views", return_value=fake_core_views),
        patch("core.services.financial_dashboard.calc_inversor_settlement", side_effect=_fake_settlement),
    ):
        payload = FinancialDashboardService(dataset["user"], filters=filters).build()

    assert payload["filters"] == {
        "fecha_desde": start.isoformat(),
        "fecha_hasta": today.isoformat(),
        "proyecto_id": dataset["proyectos"]["activo"].id,
        "estado": "captacion",
    }
    assert payload["scope"] == {
        "project_count": 1,
        "active_project_count": 1,
        "finalized_project_count": 0,
        "has_filters": True,
    }
    assert payload["kpis"]["operaciones"] == 1
    assert payload["kpis"]["capital_actual"] == Decimal("4000.00")
    assert payload["period"]["applied"] is True
    assert payload["period"]["range_days"] == today.day
    assert payload["series"]["monthly"]["investment"]
    assert len(payload["series"]["monthly"]["investment"]) == 1
    assert len(payload["charts"]["state_distribution"]) == 1
    assert payload["charts"]["state_distribution"][0]["estado"] == "captacion"
    assert payload["charts"]["state_distribution"][0]["total"] == 1
    assert payload["charts"]["state_distribution"][0]["pct"] == pytest.approx(100.0)
    assert payload["alerts"]["financial"]["pending_solicitudes"] == 1
    assert payload["alerts"]["operational"]["pendientes"] == 1


@pytest.mark.parametrize(
    "value",
    [
        True,
        False,
        None,
        "",
        " ",
        "\t",
        "\n",
        "abc",
        Decimal("1.25"),
        1,
        1.25,
        "1.25",
        -3.5,
    ],
)
def test_financial_dashboard_decimal_coercion_matches_legacy_helper(value):
    legacy = _legacy_dashboard_to_decimal(value, default=ZERO)
    current = to_decimal(value, default=ZERO)

    assert current == legacy
    assert type(current) is Decimal


def test_verified_direccion_user_can_open_dashboard(verified_client):
    response = verified_client.get(reverse("core:dashboard"))

    assert response.status_code == 200
    assert "Resumen ejecutivo" in response.content.decode("utf-8")
