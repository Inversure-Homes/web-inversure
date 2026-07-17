from __future__ import annotations

from copy import deepcopy
from decimal import Decimal
from io import StringIO
from unittest.mock import patch

import pytest
from django.core.management import call_command
from django.core.management.base import CommandError

from core.models import DatosEconomicosProyecto
from core.services.inversure_metric_audit import InversureMetricAuditService

from .financial_audit_support import (
    build_audit_portfolio,
    build_closed_profit_scenario,
    build_financed_scenario,
    build_loss_scenario,
    build_partial_contributions_scenario,
    build_rentable_scenario,
    build_zero_investment_scenario,
)

pytestmark = pytest.mark.django_db


def _money(value) -> Decimal:
    return Decimal(str(value)).quantize(Decimal("0.01"))


def _pct(value) -> Decimal:
    return Decimal(str(value)).quantize(Decimal("0.000001"))


def _find_row(rows, *, surface: str, metric: str, subject_type: str = "project", subject_id: str | None = None):
    for row in rows:
        if row.surface != surface or row.metric != metric or row.subject_type != subject_type:
            continue
        if subject_id is not None and row.subject_id != str(subject_id):
            continue
        return row
    raise AssertionError(
        f"Row not found: surface={surface!r}, metric={metric!r}, subject_type={subject_type!r}, subject_id={subject_id!r}"
    )


def _command_write_guards():
    return [
        patch("django.db.models.base.Model.save", side_effect=AssertionError("unexpected save")),
        patch("django.db.models.base.Model.delete", side_effect=AssertionError("unexpected delete")),
        patch("django.db.models.query.QuerySet.update", side_effect=AssertionError("unexpected update")),
        patch("django.db.models.query.QuerySet.bulk_create", side_effect=AssertionError("unexpected bulk_create")),
        patch("django.db.models.query.QuerySet.bulk_update", side_effect=AssertionError("unexpected bulk_update")),
        patch("django.db.models.manager.Manager.create", side_effect=AssertionError("unexpected create")),
        patch("django.db.models.manager.Manager.get_or_create", side_effect=AssertionError("unexpected get_or_create")),
        patch(
            "django.db.models.manager.Manager.update_or_create",
            side_effect=AssertionError("unexpected update_or_create"),
        ),
    ]


def test_audit_service_recalculates_independently_from_existing_helpers(direccion_user):
    scenario = build_rentable_scenario()
    service = InversureMetricAuditService(viewer_user=direccion_user)

    with (
        patch("core.views._resultado_desde_memoria", side_effect=AssertionError("helper must not be used")),
        patch("core.views._capital_objetivo_desde_memoria", side_effect=AssertionError("helper must not be used")),
        patch("core.views._beneficio_estimado_real_memoria", side_effect=AssertionError("helper must not be used")),
    ):
        metrics = service.recalculate_project(scenario.project)

    assert _money(metrics["capital_objetivo"]["value"]) == Decimal("102500.00")
    assert _money(metrics["capital_aportado"]["value"]) == Decimal("100000.00")
    assert _money(metrics["capital_pendiente"]["value"]) == Decimal("2500.00")
    assert _money(metrics["beneficio_bruto_real"]["value"]) == Decimal("37500.00")
    assert _pct(metrics["roi_real"]["value"]) == _pct(Decimal("37500") / Decimal("102500") * Decimal("100"))
    assert metrics["comision_pct"]["verifiability"] == "verificable_independientemente"
    assert metrics["impuesto_sociedades_pct"]["verifiability"] == "verificable_independientemente"
    assert len(metrics["liquidation_rows"]) == 1


def test_audit_service_marks_missing_economic_configuration_as_non_verifiable(direccion_user):
    scenario = build_closed_profit_scenario()
    DatosEconomicosProyecto.objects.filter(proyecto=scenario.project).delete()
    scenario.project.refresh_from_db()
    service = InversureMetricAuditService(viewer_user=direccion_user)

    metrics = service.recalculate_project(scenario.project)

    assert metrics["comision_pct"]["value"] is None
    assert metrics["comision_pct"]["verifiability"] == "no_verificable_de_forma_independiente"
    assert metrics["impuesto_sociedades_pct"]["value"] is None
    assert metrics["impuesto_sociedades_pct"]["verifiability"] == "no_verificable_de_forma_independiente"


@pytest.mark.parametrize(
    "builder, assertions",
    [
        (
            build_zero_investment_scenario,
            {
                "capital_aportado": Decimal("0.00"),
                "capital_pendiente": Decimal("102500.00"),
                "beneficio_bruto_real": Decimal("37500.00"),
                "liquidation_rows": 0,
            },
        ),
        (
            build_loss_scenario,
            {
                "capital_aportado": Decimal("100000.00"),
                "capital_pendiente": Decimal("0.00"),
                "beneficio_bruto_real": Decimal("-11000.00"),
                "roi_real": Decimal("-11.000000"),
                "margen_real": Decimal("-12.222222"),
            },
        ),
        (
            build_partial_contributions_scenario,
            {
                "capital_aportado": Decimal("60000.00"),
                "capital_pendiente": Decimal("40000.00"),
                "liquidation_rows": 3,
            },
        ),
        (
            build_closed_profit_scenario,
            {
                "capital_aportado": Decimal("100000.00"),
                "capital_pendiente": Decimal("0.00"),
                "ingresos_estimados": Decimal("160000.00"),
                "costes_estimados": Decimal("100000.00"),
                "beneficio_bruto_estimado": Decimal("60000.00"),
                "beneficio_bruto_real": Decimal("50000.00"),
                "comision_real": Decimal("5000.00"),
                "impuesto_sociedades_sobre_base_real": Decimal("11250.00"),
                "neto_tras_impuestos_real": Decimal("33750.00"),
                "roi_estimado": Decimal("60.000000"),
            },
        ),
        (
            build_financed_scenario,
            {
                "capital_aportado": Decimal("100000.00"),
                "capital_pendiente": Decimal("2500.00"),
                "beneficio_bruto_real": Decimal("37500.00"),
                "comision_pct": Decimal("0.00"),
            },
        ),
    ],
)
def test_audit_service_handles_reference_scenarios(builder, assertions, direccion_user):
    scenario = builder()
    service = InversureMetricAuditService(viewer_user=direccion_user)
    metrics = service.recalculate_project(scenario.project)

    for key, expected in assertions.items():
        if key == "liquidation_rows":
            assert len(metrics[key]) == expected
        elif "roi" in key or "margen" in key:
            assert _pct(metrics[key]["value"]) == _pct(expected)
        elif key == "comision_pct":
            assert _money(metrics[key]["value"]) == _money(expected)
        else:
            assert _money(metrics[key]["value"]) == _money(expected)


def test_audit_service_recalculates_liquidation_summary_rows(direccion_user):
    scenario = build_closed_profit_scenario()
    service = InversureMetricAuditService(viewer_user=direccion_user)

    recalc = service.recalculate_project(scenario.project)
    surfaces = service.collect_surfaces(scenario.project)
    rows = service.compare_project(scenario.project, recalc, surfaces)

    summary_row = next(
        row
        for row in rows
        if row.surface == "liquidacion_json"
        and row.subject_type == "project"
        and row.metric == "liquidacion_total_a_percibir"
    )

    assert summary_row.recalculated_value is not None
    assert summary_row.classification != "regla_de_negocio_pendiente"


def test_audit_service_marks_dashboard_ingresos_reales_non_verifiable(direccion_user):
    scenario = build_rentable_scenario()
    service = InversureMetricAuditService(viewer_user=direccion_user)

    recalc = service.recalculate_project(scenario.project)
    surfaces = service.collect_surfaces(scenario.project)
    rows = service.compare_project(scenario.project, recalc, surfaces)

    html_row = _find_row(rows, surface="dashboard_html", metric="ingresos_reales", subject_id=str(scenario.project.id))
    json_row = _find_row(rows, surface="dashboard_json", metric="ingresos_reales", subject_id=str(scenario.project.id))

    for row in (html_row, json_row):
        assert row.verifiability == "no_verificable_de_forma_independiente"
        assert row.classification == "regla_de_negocio_pendiente"
        assert row.severity == "warning"
        assert row.recalculated_value is None


@pytest.mark.parametrize(
    "project_name, income_estimado, cost_estimado, beneficio_estimado",
    [
        (
            "CAMINO SUAREZ",
            Decimal("180000.00"),
            Decimal("157250.00"),
            Decimal("22750.00"),
        ),
        (
            "Las Navas",
            Decimal("230000.00"),
            Decimal("204610.00"),
            Decimal("25390.00"),
        ),
    ],
)
def test_audit_service_keeps_dashboard_income_estimates_separate_from_benefit(
    project_name,
    income_estimado,
    cost_estimado,
    beneficio_estimado,
    direccion_user,
):
    scenario = build_closed_profit_scenario()
    scenario.project.nombre = project_name
    scenario.project.save(update_fields=["nombre"])

    income = scenario.project.ingresos.first()
    cost = scenario.project.gastos_proyecto.first()
    assert income is not None
    assert cost is not None

    income.importe_real = income_estimado - Decimal("27500.00")
    income.importe_estimado = income_estimado
    income.estado = "confirmado"
    income.save(update_fields=["importe_real", "importe_estimado", "estado"])

    cost.importe_real = cost_estimado - Decimal("12345.00")
    cost.importe_estimado = cost_estimado
    cost.estado = "confirmado"
    cost.save(update_fields=["importe_real", "importe_estimado", "estado"])

    scenario.project.refresh_from_db()
    service = InversureMetricAuditService(viewer_user=direccion_user)

    recalc = service.recalculate_project(scenario.project)
    surfaces = service.collect_surfaces(scenario.project)
    for surface_name in ("dashboard_html", "dashboard_json"):
        surface_payload = surfaces.get(surface_name, {})
        candidate_payloads = [surface_payload]
        if surface_name == "dashboard_html":
            nested_payload = surface_payload.get("dashboard_payload") if isinstance(surface_payload, dict) else None
            if isinstance(nested_payload, dict):
                candidate_payloads.insert(0, nested_payload)

        mutated = False
        for payload in candidate_payloads:
            projects = payload.get("projects") if isinstance(payload, dict) else None
            if isinstance(projects, list) and projects:
                projects[0]["ingresos_estimados"] = income_estimado
                projects[0]["beneficio_estimado"] = beneficio_estimado
                mutated = True
                break
        assert mutated
    rows = service.compare_project(scenario.project, recalc, surfaces)

    assert _money(recalc["ingresos_estimados"]["value"]) == _money(income_estimado)
    assert _money(recalc["costes_estimados"]["value"]) == _money(cost_estimado)
    assert _money(recalc["beneficio_bruto_estimado"]["value"]) == _money(beneficio_estimado)

    for surface in ("dashboard_html", "dashboard_json"):
        income_row = _find_row(rows, surface=surface, metric="ingresos_estimados", subject_id=str(scenario.project.id))
        benefit_row = _find_row(
            rows,
            surface=surface,
            metric="beneficio_bruto_estimado",
            subject_id=str(scenario.project.id),
        )

        assert _money(income_row.shown_value) == _money(income_estimado)
        assert income_row.recalculated_value is None
        assert income_row.verifiability == "no_verificable_de_forma_independiente"
        assert income_row.classification == "regla_de_negocio_pendiente"
        assert income_row.severity == "warning"

        assert _money(benefit_row.shown_value) == _money(beneficio_estimado)
        assert _money(benefit_row.recalculated_value) == _money(beneficio_estimado)
        assert benefit_row.verifiability == "no_verificable_de_forma_independiente"
        assert benefit_row.classification == "regla_de_negocio_pendiente"
        assert benefit_row.severity == "warning"


def test_audit_service_uses_importe_estimado_for_confirmed_rows(direccion_user):
    scenario = build_closed_profit_scenario()
    income = scenario.project.ingresos.first()
    cost = scenario.project.gastos_proyecto.first()
    assert income is not None
    assert cost is not None

    income.importe_real = Decimal("150000.00")
    income.importe_estimado = Decimal("180000.00")
    income.estado = "confirmado"
    income.save(update_fields=["importe_real", "importe_estimado", "estado"])

    cost.importe_real = Decimal("140000.00")
    cost.importe_estimado = Decimal("157250.00")
    cost.estado = "confirmado"
    cost.save(update_fields=["importe_real", "importe_estimado", "estado"])

    scenario.project.refresh_from_db()
    service = InversureMetricAuditService(viewer_user=direccion_user)

    metrics = service.recalculate_project(scenario.project)

    assert _money(metrics["ingresos_estimados"]["value"]) == Decimal("180000.00")
    assert _money(metrics["costes_estimados"]["value"]) == Decimal("157250.00")
    assert _money(metrics["beneficio_bruto_estimado"]["value"]) == Decimal("22750.00")
    assert _pct(metrics["roi_estimado"]["value"]) == _pct(Decimal("22750.00") / Decimal("157250.00") * Decimal("100"))


def test_audit_service_uses_detail_beneficio_esperado_definition(direccion_user):
    scenario = build_closed_profit_scenario()
    service = InversureMetricAuditService(viewer_user=direccion_user)

    recalc = service.recalculate_project(scenario.project)
    surfaces = service.collect_surfaces(scenario.project)
    rows = service.compare_project(scenario.project, recalc, surfaces)

    detail_row = _find_row(rows, surface="detail", metric="beneficio_esperado", subject_id=str(scenario.project.id))

    assert detail_row.shown_value is not None
    assert detail_row.verifiability == "no_verificable_de_forma_independiente"
    assert detail_row.classification == "regla_de_negocio_pendiente"
    assert not any(row.surface == "detail" and row.metric == "beneficio_bruto_real" for row in rows)


def test_audit_service_treats_detail_roi_as_snapshot_when_it_differs_from_live(direccion_user):
    scenario = build_closed_profit_scenario()
    snapshot = deepcopy(scenario.project.snapshot_datos or {})
    snapshot.setdefault("resultado", {})["roi"] = 16.3729
    snapshot["resultado"]["beneficio_neto"] = 26019.30
    snapshot.setdefault("economico", {})["roi"] = 16.3729
    snapshot.setdefault("kpis", {}).setdefault("metricas", {})["roi"] = 16.3729
    scenario.project.snapshot_datos = snapshot
    scenario.project.save(update_fields=["snapshot_datos"])

    service = InversureMetricAuditService(viewer_user=direccion_user)
    recalc = service.recalculate_project(scenario.project)
    surfaces = service.collect_surfaces(scenario.project)
    rows = service.compare_project(scenario.project, recalc, surfaces)

    snapshot_row = _find_row(rows, surface="detail", metric="roi_snapshot", subject_id=str(scenario.project.id))
    dashboard_row = _find_row(rows, surface="dashboard_html", metric="roi_real", subject_id=str(scenario.project.id))
    dashboard_json_row = _find_row(
        rows, surface="dashboard_json", metric="roi_real", subject_id=str(scenario.project.id)
    )
    pdf_row = _find_row(
        rows,
        surface="pdf_memoria",
        metric="roi_tras_impuestos_costes_real",
        subject_id=str(scenario.project.id),
    )

    assert _pct(recalc["roi_real"]["value"]) != _pct(Decimal("16.3729"))
    assert snapshot_row.shown_value is not None
    assert snapshot_row.verifiability == "no_verificable_de_forma_independiente"
    assert snapshot_row.classification == "regla_de_negocio_pendiente"
    assert snapshot_row.severity == "warning"
    assert snapshot_row.recalculated_value is None
    assert not any(row.surface == "detail" and row.metric == "roi_real" for row in rows)
    assert not any(row.surface == "pdf_memoria" and row.metric == "roi_real" for row in rows)

    for row in (dashboard_row, dashboard_json_row, pdf_row):
        assert row.verifiability == "verificable_independientemente"
        assert row.classification in {"coincide", "diferencia_de_redondeo"}
        assert row.severity in {"info", "warning"}


@pytest.mark.parametrize(
    "project_name, income_estimado, beneficio_estimado",
    [
        (
            "CAMINO SUAREZ",
            Decimal("180000.00"),
            Decimal("22750.00"),
        ),
        (
            "Las Navas",
            Decimal("230000.00"),
            Decimal("25390.00"),
        ),
    ],
)
def test_audit_service_marks_pdf_fallback_real_values_non_verifiable(
    project_name,
    income_estimado,
    beneficio_estimado,
    direccion_user,
):
    scenario = build_closed_profit_scenario()
    scenario.project.nombre = project_name
    scenario.project.save(update_fields=["nombre"])

    income = scenario.project.ingresos.first()
    cost = scenario.project.gastos_proyecto.first()
    assert income is not None
    assert cost is not None

    cost_estimado = income_estimado - beneficio_estimado
    income.importe_real = income_estimado - Decimal("27500.00")
    income.importe_estimado = income_estimado
    income.estado = "confirmado"
    income.save(update_fields=["importe_real", "importe_estimado", "estado"])

    cost.importe_real = cost_estimado - Decimal("12345.00")
    cost.importe_estimado = cost_estimado
    cost.estado = "confirmado"
    cost.save(update_fields=["importe_real", "importe_estimado", "estado"])

    scenario.project.refresh_from_db()
    service = InversureMetricAuditService(viewer_user=direccion_user)

    recalc = service.recalculate_project(scenario.project)
    surfaces = service.collect_surfaces(scenario.project)
    resumen = surfaces["pdf_memoria"]["resumen"]
    resumen["ingresos_reales_estimados"] = True
    resumen["ingresos_reales"] = income_estimado
    resumen["beneficio_real"] = beneficio_estimado
    resumen["roi_real_tras_impuestos"] = None

    rows = service.compare_project(scenario.project, recalc, surfaces)

    income_row = _find_row(rows, surface="pdf_memoria", metric="ingresos_reales", subject_id=str(scenario.project.id))
    benefit_row = _find_row(
        rows,
        surface="pdf_memoria",
        metric="beneficio_bruto_real",
        subject_id=str(scenario.project.id),
    )
    roi_row = _find_row(
        rows,
        surface="pdf_memoria",
        metric="roi_tras_impuestos_costes_real",
        subject_id=str(scenario.project.id),
    )

    assert _money(recalc["beneficio_bruto_estimado"]["value"]) == _money(beneficio_estimado)
    for row in (income_row, benefit_row):
        assert row.verifiability == "no_verificable_de_forma_independiente"
        assert row.classification == "regla_de_negocio_pendiente"
        assert row.severity == "warning"
        assert row.recalculated_value is None
        assert "fallback" in row.explanation.lower()
    assert _money(income_row.shown_value) == _money(income_estimado)
    assert _money(benefit_row.shown_value) == _money(beneficio_estimado)
    assert roi_row.shown_value is None
    assert roi_row.recalculated_value is None
    assert roi_row.verifiability == "no_verificable_de_forma_independiente"
    assert roi_row.classification == "regla_de_negocio_pendiente"
    assert roi_row.severity == "warning"
    assert "ROI tras impuestos" in roi_row.explanation
    assert not any(row.surface == "pdf_memoria" and row.metric == "roi_real" for row in rows)


def test_audit_service_reads_liquidacion_json_resumen_and_keeps_flat_schema(direccion_user):
    scenario = build_closed_profit_scenario()
    service = InversureMetricAuditService(viewer_user=direccion_user)

    surfaces = service.collect_surfaces(scenario.project)
    liquidation_json = surfaces["liquidacion_json"]

    assert set(liquidation_json) >= {"ok", "liquidaciones", "resumen"}
    assert isinstance(liquidation_json["liquidaciones"], list)
    assert isinstance(liquidation_json["resumen"], dict)
    assert set(liquidation_json["resumen"]) == {"invertido", "bruto", "retencion", "neto", "total_a_percibir"}
    assert all(not isinstance(value, (dict, list)) for value in liquidation_json["resumen"].values())
    assert liquidation_json["liquidaciones"]
    first_row = liquidation_json["liquidaciones"][0]
    assert set(first_row) >= {
        "id",
        "cliente_nombre",
        "fecha_aportacion",
        "fecha",
        "importe_invertido",
        "porcentaje_participacion",
        "beneficio_bruto",
        "retencion",
        "neto",
        "total_a_percibir",
        "estado",
    }
    assert all(not isinstance(value, dict) for value in first_row.values())


def test_audit_service_uses_liquidacion_resumen_values(direccion_user):
    scenario = build_closed_profit_scenario()
    service = InversureMetricAuditService(viewer_user=direccion_user)
    recalc = service.recalculate_project(scenario.project)
    surfaces = service.collect_surfaces(scenario.project)
    surfaces["liquidacion_json"]["resumen"]["bruto"] = 999.99

    rows = service.compare_project(scenario.project, recalc, surfaces)
    summary_row = _find_row(
        rows,
        surface="liquidacion_json",
        metric="liquidacion_beneficio_bruto_inversor",
        subject_type="project",
        subject_id=str(scenario.project.id),
    )

    assert _money(summary_row.shown_value) == Decimal("999.99")


def test_audit_service_marks_liquidations_non_verifiable_without_economic_configuration(direccion_user):
    scenario = build_closed_profit_scenario()
    DatosEconomicosProyecto.objects.filter(proyecto=scenario.project).delete()
    scenario.project.refresh_from_db()
    service = InversureMetricAuditService(viewer_user=direccion_user)

    recalc = service.recalculate_project(scenario.project)
    surfaces = service.collect_surfaces(scenario.project)
    rows = service.compare_project(scenario.project, recalc, surfaces)

    liquidation_row = _find_row(
        rows,
        surface="liquidacion_json",
        metric="liquidacion_total_a_percibir",
        subject_type="project",
        subject_id=str(scenario.project.id),
    )

    assert liquidation_row.verifiability == "no_verificable_de_forma_independiente"
    assert liquidation_row.classification == "regla_de_negocio_pendiente"
    assert liquidation_row.severity == "warning"

    participation_row = _find_row(
        rows,
        surface="liquidacion_json",
        metric="liquidacion_beneficio_bruto_inversor",
        subject_type="participation",
        subject_id=str(scenario.participations[0].id),
    )
    assert participation_row.verifiability == "no_verificable_de_forma_independiente"
    assert participation_row.classification == "regla_de_negocio_pendiente"
    assert participation_row.severity == "warning"


def test_audit_service_marks_investment_return_metrics_non_verifiable_without_economic_configuration(direccion_user):
    scenario = build_closed_profit_scenario()
    DatosEconomicosProyecto.objects.filter(proyecto=scenario.project).delete()
    scenario.project.refresh_from_db()
    service = InversureMetricAuditService(viewer_user=direccion_user)

    recalc = service.recalculate_project(scenario.project)
    surfaces = service.collect_surfaces(scenario.project)
    rows = service.compare_project(scenario.project, recalc, surfaces)

    retorno_row = _find_row(
        rows,
        surface="dashboard_html",
        metric="investment_return_retorno_total",
        subject_id=str(scenario.project.id),
    )
    neto_row = _find_row(
        rows,
        surface="dashboard_html",
        metric="investment_return_beneficio_neto",
        subject_id=str(scenario.project.id),
    )

    for row in (retorno_row, neto_row):
        assert row.verifiability == "no_verificable_de_forma_independiente"
        assert row.classification == "regla_de_negocio_pendiente"
        assert row.severity == "warning"


def test_audit_service_processes_full_portfolio(direccion_user):
    build_audit_portfolio()
    service = InversureMetricAuditService(viewer_user=direccion_user)

    report = service.audit()

    assert report["project_count"] == 5
    assert report["summary"]["row_count"] > 0
    assert report["summary"]["severity_counts"]["critical"] == 0
    assert len(report["project_results"]) == 5
    assert {result["state"] for result in report["project_results"]} >= {
        "vendido",
        "descartado",
        "comprado",
        "comercializacion",
        "cerrado",
    }


def test_audit_service_classifies_rounding_differences_separately(direccion_user):
    scenario = build_rentable_scenario()
    service = InversureMetricAuditService(viewer_user=direccion_user)

    recalc = service.recalculate_project(scenario.project)
    surfaces = service.collect_surfaces(scenario.project)
    dashboard_projects = surfaces["dashboard_json"]["projects"]
    dashboard_projects[0]["capital_objetivo"] = float(recalc["capital_objetivo"]["value"]) + 0.004

    rows = service.compare_project(scenario.project, recalc, surfaces)
    row = next(item for item in rows if item.surface == "dashboard_json" and item.metric == "capital_objetivo")

    assert row.classification == "diferencia_de_redondeo"
    assert row.severity == "warning"


def test_audit_command_writes_csv_and_markdown_without_database_writes(tmp_path, direccion_user):
    scenario = build_rentable_scenario()
    stdout = StringIO()

    guards = _command_write_guards()
    with (
        guards[0],
        guards[1],
        guards[2],
        guards[3],
        guards[4],
        guards[5],
        guards[6],
        guards[7],
    ):
        call_command(
            "audit_inversure_metricas",
            project_id=scenario.project.id,
            output_dir=tmp_path,
            formats=["csv", "markdown"],
            fail_on_severity="critical",
            stdout=stdout,
        )

    csv_path = tmp_path / "audit_inversure_metricas.csv"
    markdown_path = tmp_path / "audit_inversure_metricas.md"
    assert csv_path.exists()
    assert markdown_path.exists()
    assert csv_path.read_text(encoding="utf-8").splitlines()[0].split(";") == [
        "project_id",
        "project_name",
        "state",
        "surface",
        "subject_type",
        "subject_id",
        "metric",
        "shown_value",
        "recalculated_value",
        "diff_abs",
        "diff_pct",
        "verifiability",
        "classification",
        "severity",
        "explanation",
    ]
    markdown_text = markdown_path.read_text(encoding="utf-8")
    assert "# Auditoría de métricas Inversure" in markdown_text
    assert "Explicación" in markdown_text
    assert "classification=" in markdown_text
    assert "Auditoría Inversure completada" in stdout.getvalue()


def test_audit_command_detects_discrepancy_and_fails_on_threshold(tmp_path, direccion_user):
    scenario = build_rentable_scenario()
    stdout = StringIO()
    original_collect_surfaces = InversureMetricAuditService.collect_surfaces

    def _mutated_collect_surfaces(self, project):
        surfaces = original_collect_surfaces(self, project)
        dashboard_json = surfaces.get("dashboard_json", {})
        projects = dashboard_json.get("projects") if isinstance(dashboard_json, dict) else None
        if projects:
            projects[0]["capital_objetivo"] = float(projects[0]["capital_objetivo"]) + 10.0
        return surfaces

    with patch.object(InversureMetricAuditService, "collect_surfaces", new=_mutated_collect_surfaces):
        with pytest.raises(CommandError):
            call_command(
                "audit_inversure_metricas",
                project_id=scenario.project.id,
                output_dir=tmp_path,
                formats=["csv", "markdown"],
                fail_on_severity="warning",
                stdout=stdout,
            )

    assert (tmp_path / "audit_inversure_metricas.csv").exists()
    assert (tmp_path / "audit_inversure_metricas.md").exists()
