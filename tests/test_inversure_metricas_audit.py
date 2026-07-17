from __future__ import annotations

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


def _command_write_guards():
    return [
        patch("django.db.models.base.Model.save", side_effect=AssertionError("unexpected save")),
        patch("django.db.models.base.Model.delete", side_effect=AssertionError("unexpected delete")),
        patch("django.db.models.query.QuerySet.update", side_effect=AssertionError("unexpected update")),
        patch("django.db.models.query.QuerySet.bulk_create", side_effect=AssertionError("unexpected bulk_create")),
        patch("django.db.models.query.QuerySet.bulk_update", side_effect=AssertionError("unexpected bulk_update")),
        patch("django.db.models.manager.Manager.create", side_effect=AssertionError("unexpected create")),
        patch("django.db.models.manager.Manager.get_or_create", side_effect=AssertionError("unexpected get_or_create")),
        patch("django.db.models.manager.Manager.update_or_create", side_effect=AssertionError("unexpected update_or_create")),
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
                "beneficio_bruto_real": Decimal("50000.00"),
                "comision_real": Decimal("5000.00"),
                "impuesto_sociedades_sobre_base_real": Decimal("11250.00"),
                "neto_tras_impuestos_real": Decimal("33750.00"),
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


def test_audit_service_processes_full_portfolio(direccion_user):
    build_audit_portfolio()
    service = InversureMetricAuditService(viewer_user=direccion_user)

    report = service.audit()

    assert report["project_count"] == 5
    assert report["summary"]["row_count"] > 0
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
    row = next(
        item
        for item in rows
        if item.surface == "dashboard_json" and item.metric == "capital_objetivo"
    )

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
    assert "project_id;project_name;state;surface" in csv_path.read_text(encoding="utf-8")
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
