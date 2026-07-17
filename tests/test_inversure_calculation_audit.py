from __future__ import annotations

import json
from contextlib import contextmanager
from decimal import Decimal
from typing import Any
from unittest.mock import patch

import pytest
from django.core.serializers.json import DjangoJSONEncoder
from django.http import HttpResponse
from django.test import RequestFactory
from django.urls import reverse
from django.utils import timezone

from core.services.financial_dashboard import FinancialDashboardFilters, FinancialDashboardService

from .financial_audit_support import (
    AuditScenario,
    build_audit_portfolio,
    build_closed_profit_scenario,
    build_financed_scenario,
    build_loss_scenario,
    build_partial_contributions_scenario,
    build_rentable_scenario,
    build_zero_investment_scenario,
)

pytestmark = pytest.mark.django_db

TEST_NOW = timezone.datetime(2026, 7, 17, 12, 0, tzinfo=timezone.get_current_timezone())


def _normalized(value: Any) -> Any:
    return json.loads(json.dumps(value, cls=DjangoJSONEncoder))


def _decimal(value: Any) -> Decimal:
    if value is None or value == "":
        return Decimal("0")
    if isinstance(value, Decimal):
        return value
    return Decimal(str(value))


def _assert_money(actual: Any, expected: Any, *, label: str = "") -> None:
    actual_q = _decimal(actual).quantize(Decimal("0.01"))
    expected_q = _decimal(expected).quantize(Decimal("0.01"))
    assert actual_q == expected_q, f"{label} expected {expected_q} but got {actual_q}"


def _assert_pct(actual: Any, expected: Any, *, places: int = 6, label: str = "") -> None:
    tolerance = Decimal("1").scaleb(-places)
    diff = abs(_decimal(actual) - _decimal(expected))
    assert diff <= tolerance, f"{label} expected {expected} but got {actual} (diff {diff})"


def _make_request(path: str, user, query: dict[str, Any] | None = None):
    request = RequestFactory().get(path, query or {})
    request.user = user
    return request


@contextmanager
def _freeze_financial_now():
    with (
        patch("core.views.timezone.now", return_value=TEST_NOW),
        patch("core.services.financial_dashboard.timezone.now", return_value=TEST_NOW),
    ):
        yield


def _capture_render_context(view_func, request, *args, **kwargs):
    captured: dict[str, Any] = {}

    def _fake_render(request, template_name, context=None, *render_args, **render_kwargs):
        captured["template_name"] = template_name
        captured["context"] = context or {}
        return HttpResponse("captured")

    with patch("core.views.render", side_effect=_fake_render):
        response = view_func(request, *args, **kwargs)

    return response, captured.get("template_name"), captured.get("context", {})


def _service_payload(user, *, filters: FinancialDashboardFilters | None = None) -> dict[str, Any]:
    return FinancialDashboardService(user=user, filters=filters).build()


def _dashboard_response(verified_client, query: dict[str, Any] | None = None):
    return verified_client.get(reverse("core:dashboard_data"), query or {})


def _response_context(response, *, must_have: tuple[str, ...] = ()) -> dict[str, Any]:
    context = getattr(response, "context", None)
    if context is None:
        return {}
    if isinstance(context, dict):
        return context
    candidates: list[dict[str, Any]] = []
    try:
        for candidate in context:  # type: ignore[assignment]
            if isinstance(candidate, dict):
                candidates.append(candidate)
                continue
            if hasattr(candidate, "flatten"):
                flattened = candidate.flatten()
                if isinstance(flattened, dict):
                    candidates.append(flattened)
                continue
            try:
                candidates.append(dict(candidate))
            except Exception:
                continue
    except Exception:
        pass
    if must_have:
        def _score(candidate: dict[str, Any]) -> Decimal:
            if "captacion" in candidate and isinstance(candidate.get("captacion"), dict):
                return _decimal(candidate["captacion"].get("capital_objetivo"))
            if "resultado" in candidate and isinstance(candidate.get("resultado"), dict):
                return _decimal(candidate["resultado"].get("capital_objetivo"))
            if "resumen" in candidate and isinstance(candidate.get("resumen"), dict):
                return _decimal(candidate["resumen"].get("ingresos_estimados"))
            return Decimal("0")

        for candidate in candidates:
            if all(key in candidate for key in must_have) and _score(candidate) > 0:
                return candidate
        for candidate in candidates:
            if all(key in candidate for key in must_have):
                return candidate
    if candidates:
        return candidates[0]
    if hasattr(context, "flatten"):
        flattened = context.flatten()
        if isinstance(flattened, dict):
            return flattened
    try:
        return dict(context)
    except Exception:
        return {}


def _filter_for_project(scenario: AuditScenario) -> dict[str, Any]:
    return {
        "proyecto_id": scenario.project.id,
        "estado": scenario.project.estado,
    }


def _assert_dashboard_payload_matches_endpoint(service_payload: dict[str, Any], response) -> None:
    assert response.status_code == 200
    assert response["Content-Type"].startswith("application/json")
    assert response.json() == _normalized(service_payload)


def _assert_project_metrics(
    scenario: AuditScenario,
    service_payload: dict[str, Any],
    detail_context: dict[str, Any],
    pdf_context: dict[str, Any],
) -> None:
    service_project = service_payload["projects"][0]
    expected_detail = scenario.expected["detail"]
    expected_study = scenario.expected["study"]
    expected_pdf = scenario.expected["pdf"]
    actual_detail = detail_context["resultado"]
    actual_study = detail_context["inv"]
    actual_pdf = pdf_context["resumen"]

    for key in ("beneficio_neto", "beneficio_neto_tras_impuestos"):
        _assert_money(service_project[key], expected_detail[key], label=f"dashboard.{key}")
        _assert_money(actual_detail[key], expected_detail[key], label=f"detalle.{key}")

    _assert_pct(service_project["roi"], expected_detail["roi"], label="dashboard.roi")
    _assert_pct(actual_detail["roi"], expected_detail["roi"], label="detalle.roi")
    _assert_pct(service_project["margen_neto"], expected_detail["margen_neto"], label="dashboard.margen_neto")
    _assert_pct(actual_detail["margen_neto"], expected_detail["margen_neto"], label="detalle.margen_neto")
    _assert_money(service_project["beneficio_inversure"], expected_study["comision_inversure_eur"], label="dashboard.comision")

    _assert_money(detail_context["captacion"]["capital_objetivo"], expected_detail["capital_objetivo"], label="capital objetivo")
    _assert_money(detail_context["captacion"]["capital_captado"], expected_detail["capital_captado"], label="capital captado")
    _assert_money(detail_context["captacion"]["restante"], expected_detail["capital_pendiente"], label="capital pendiente")
    _assert_pct(
        detail_context["captacion"]["pct_captado"],
        (expected_detail["capital_captado"] / expected_detail["capital_objetivo"]) * Decimal("100"),
        label="pct captado",
    )

    _assert_money(actual_study["comision_inversure_eur"], expected_study["comision_inversure_eur"], label="estudio.comision")
    _assert_money(actual_study["beneficio_neto_inversor"], expected_study["beneficio_neto_inversor"], label="estudio.beneficio")
    _assert_money(actual_study["impuesto_sociedades"], expected_study["impuesto_sociedades"], label="estudio.impuesto")
    _assert_money(
        actual_study["beneficio_neto_tras_impuestos"],
        expected_study["beneficio_neto_tras_impuestos"],
        label="estudio.beneficio_tras_impuestos",
    )
    _assert_pct(actual_study["roi_neto_inversor"], expected_study["roi_neto_inversor"], label="estudio.roi_neto")
    _assert_pct(
        actual_study["roi_neto_tras_impuestos"],
        expected_study["roi_neto_tras_impuestos"],
        label="estudio.roi_neto_tras_impuestos",
    )

    _assert_money(actual_pdf["beneficio_real"], expected_pdf["beneficio_real"], label="pdf.beneficio_real")
    _assert_money(actual_pdf["beneficio_neto_real"], expected_pdf["beneficio_neto_real"], label="pdf.beneficio_neto_real")
    _assert_money(actual_pdf["comision_inversure_real"], expected_pdf["comision_inversure_real"], label="pdf.comision")
    _assert_money(actual_pdf["impuesto_sociedades_real"], expected_pdf["impuesto_sociedades_real"], label="pdf.impuesto")
    _assert_money(
        actual_pdf["beneficio_neto_real_tras_impuestos"],
        expected_pdf["beneficio_neto_real_tras_impuestos"],
        label="pdf.beneficio_tras_impuestos",
    )
    _assert_pct(actual_pdf["roi_real"], expected_pdf["roi_real"], label="pdf.roi_real")
    _assert_pct(actual_pdf["roi_real_tras_impuestos"], expected_pdf["roi_real_tras_impuestos"], label="pdf.roi_real_tras_impuestos")

    expected_settlement = scenario.expected["settlement"]
    actual_settlement = service_project["investment_return"]
    capital_total_invertido = sum((part.importe_invertido for part in scenario.participations), Decimal("0"))
    _assert_money(actual_settlement["capital_invertido"], capital_total_invertido, label="dashboard.capital_invertido")
    _assert_money(actual_settlement["beneficio_neto"], expected_settlement["neto_cobrar"], label="dashboard.neto_cobrar")
    _assert_money(actual_settlement["retorno_total"], expected_settlement["total_a_percibir"], label="dashboard.total_a_percibir")
    _assert_pct(actual_settlement["roi_bruto_medio"], expected_settlement["roi_bruto_pct"], label="dashboard.roi_bruto")
    _assert_pct(actual_settlement["roi_neto_medio"], expected_settlement["roi_neto_pct"], label="dashboard.roi_neto")


def _assert_liquidation_matches(
    scenario: AuditScenario,
    liquidation_response,
) -> None:
    expected_liquidation = scenario.expected["liquidation"]
    payload = liquidation_response.json()

    assert liquidation_response.status_code == 200
    assert payload["ok"] is True
    assert payload["gasto_solicitado"] == pytest.approx(0.0)
    assert len(payload["liquidaciones"]) == len(scenario.participations)

    expected_participations = sorted(
        scenario.participations,
        key=lambda part: (
            part.fecha_aportacion.isoformat() if getattr(part, "fecha_aportacion", None) else "",
            part.id or 0,
        ),
    )
    total_invertido = sum((part.importe_invertido for part in expected_participations), Decimal("0"))
    project_benefit = _decimal(expected_liquidation["beneficio_neto_inversor"])
    retencion_pct = (
        _decimal(expected_liquidation["retencion"]) / project_benefit if project_benefit > 0 else Decimal("0")
    )

    for row, part in zip(payload["liquidaciones"], expected_participations, strict=True):
        ratio = (_decimal(part.importe_invertido) / total_invertido) if total_invertido else Decimal("0")
        expected_benefit = project_benefit * ratio
        expected_retencion = max(Decimal("0"), expected_benefit) * retencion_pct
        expected_neto = expected_benefit - expected_retencion
        expected_total = _decimal(part.importe_invertido) + expected_neto
        assert row["estado"] in {"Liquidación prevista", "Liquidación cerrada"}
        _assert_money(row["beneficio_bruto"], expected_benefit, label="liquidación beneficio")
        _assert_money(row["retencion"], expected_retencion, label="liquidación retención")
        _assert_money(row["neto"], expected_neto, label="liquidación neto")
        _assert_money(row["total_a_percibir"], expected_total, label="liquidación total")

    resumen = payload["resumen"]
    _assert_money(resumen["invertido"], total_invertido, label="invertido")
    _assert_money(resumen["bruto"], expected_liquidation["beneficio_neto_inversor"], label="bruto")
    _assert_money(resumen["retencion"], expected_liquidation["retencion"], label="retención")
    _assert_money(resumen["neto"], expected_liquidation["neto_cobrar"], label="neto")
    _assert_money(resumen["total_a_percibir"], expected_liquidation["total_a_percibir"], label="total a percibir")


def _service_query(scenario: AuditScenario) -> dict[str, Any]:
    query = _filter_for_project(scenario)
    return FinancialDashboardFilters.from_mapping(query).to_dict()


def test_portfolio_audit_matches_dashboard_summary_and_rankings(verified_client, direccion_user):
    build_audit_portfolio()

    with _freeze_financial_now():
        service_payload = _service_payload(direccion_user)
        response = _dashboard_response(verified_client)

    _assert_dashboard_payload_matches_endpoint(service_payload, response)

    assert service_payload["scope"] == {
        "project_count": 5,
        "active_project_count": 3,
        "finalized_project_count": 2,
        "has_filters": False,
    }
    assert service_payload["kpis"]["capital_total_invertido"] == Decimal("460000.00")
    assert service_payload["kpis"]["capital_actual"] == Decimal("260000.00")
    assert service_payload["kpis"]["capital_en_vigor"] == Decimal("440000.00")
    assert service_payload["kpis"]["capital_pendiente_total"] == Decimal("45000.00")
    assert service_payload["kpis"]["beneficio_total"] == pytest.approx(134000.0)
    assert service_payload["kpis"]["beneficio_estimado_total"] == pytest.approx(144000.0)
    assert service_payload["kpis"]["beneficio_real_total"] == pytest.approx(134000.0)
    assert service_payload["kpis"]["beneficio_cerrado_bruto"] == pytest.approx(50000.0)
    assert service_payload["kpis"]["beneficio_cerrado_neto"] == pytest.approx(45000.0)
    assert service_payload["kpis"]["beneficio_abierto_bruto"] == pytest.approx(95000.0)
    assert service_payload["kpis"]["beneficio_abierto_neto"] == pytest.approx(95000.0)
    assert service_payload["kpis"]["beneficio_inversure"] == pytest.approx(5000.0)
    assert service_payload["kpis"]["roi_medio"] == pytest.approx(26.434146341463415)
    assert service_payload["kpis"]["roi_medio_ponderado"] == pytest.approx(26.534653465346533)

    state_distribution = {item["estado"]: item for item in service_payload["charts"]["state_distribution"]}
    assert state_distribution["comprado"]["total"] == 1
    assert state_distribution["comercializacion"]["total"] == 1
    assert state_distribution["vendido"]["total"] == 1
    assert state_distribution["cerrado"]["total"] == 1
    assert state_distribution["descartado"]["total"] == 1

    assert service_payload["rankings"]["best_roi"][0]["nombre"] == "Cerrado beneficio real"
    assert service_payload["rankings"]["worst_roi"][0]["nombre"] == "Pérdidas descartado"
    assert service_payload["rankings"]["best_benefit"][0]["nombre"] == "Cerrado beneficio real"
    assert service_payload["rankings"]["worst_benefit"][0]["nombre"] == "Pérdidas descartado"
    assert service_payload["rankings"]["investment_return"][-1]["nombre"] == "Aportaciones parciales"


def test_rentable_project_matches_detail_dashboard_pdf_and_liquidation(verified_client, direccion_user):
    scenario = build_rentable_scenario()
    query = _filter_for_project(scenario)
    filters = FinancialDashboardFilters.from_mapping(query)

    with _freeze_financial_now():
        service_payload = _service_payload(direccion_user, filters=filters)
        response = _dashboard_response(verified_client, query)
        detail_response = verified_client.get(reverse("core:proyecto", args=[scenario.project.id]))
        pdf_response = verified_client.get(reverse("core:pdf_memoria_economica", args=[scenario.project.id]))
        detail_context = _response_context(detail_response, must_have=("captacion", "resultado", "inv"))
        pdf_context = _response_context(pdf_response, must_have=("resumen",))
        liquidation_response = verified_client.get(reverse("core:proyecto_liquidaciones", args=[scenario.project.id]))

    _assert_dashboard_payload_matches_endpoint(service_payload, response)
    assert detail_response.status_code == 200
    assert pdf_response.status_code == 200
    _assert_project_metrics(scenario, service_payload, detail_context, pdf_context)
    _assert_liquidation_matches(scenario, liquidation_response)
    _assert_money(service_payload["projects"][0]["beneficio_inversure"], Decimal("0"), label="beneficio inversure")
    assert liquidation_response.json()["liquidaciones"][0]["estado"] == "Liquidación prevista"


def test_loss_project_preserves_negative_profit_and_descartado_state(verified_client, direccion_user):
    scenario = build_loss_scenario()
    query = _filter_for_project(scenario)
    filters = FinancialDashboardFilters.from_mapping(query)

    with _freeze_financial_now():
        service_payload = _service_payload(direccion_user, filters=filters)
        response = _dashboard_response(verified_client, query)
        detail_response = verified_client.get(reverse("core:proyecto", args=[scenario.project.id]))
        pdf_response = verified_client.get(reverse("core:pdf_memoria_economica", args=[scenario.project.id]))
        detail_context = _response_context(detail_response, must_have=("captacion", "resultado", "inv"))
        pdf_context = _response_context(pdf_response, must_have=("resumen",))
        liquidation_response = verified_client.get(reverse("core:proyecto_liquidaciones", args=[scenario.project.id]))

    _assert_dashboard_payload_matches_endpoint(service_payload, response)
    _assert_project_metrics(scenario, service_payload, detail_context, pdf_context)
    _assert_liquidation_matches(scenario, liquidation_response)
    assert service_payload["scope"] == {
        "project_count": 1,
        "active_project_count": 0,
        "finalized_project_count": 1,
        "has_filters": True,
    }
    _assert_pct(service_payload["projects"][0]["roi"], Decimal("-11.0"), label="loss.roi")
    _assert_money(service_payload["projects"][0]["beneficio_neto"], Decimal("-11000.0"), label="loss.beneficio_neto")
    assert liquidation_response.json()["liquidaciones"][0]["estado"] == "Liquidación prevista"


def test_financing_pct_is_metadata_only(verified_client, direccion_user):
    rentable = build_rentable_scenario()
    financed = build_financed_scenario()
    rentable_query = _filter_for_project(rentable)
    financed_query = _filter_for_project(financed)

    with _freeze_financial_now():
        rentable_service = _service_payload(direccion_user, filters=FinancialDashboardFilters.from_mapping(rentable_query))
        financed_service = _service_payload(direccion_user, filters=FinancialDashboardFilters.from_mapping(financed_query))
        rentable_detail = _response_context(
            verified_client.get(reverse("core:proyecto", args=[rentable.project.id])),
            must_have=("captacion", "resultado", "inv"),
        )
        financed_detail = _response_context(
            verified_client.get(reverse("core:proyecto", args=[financed.project.id])),
            must_have=("captacion", "resultado", "inv"),
        )
        rentable_pdf = _response_context(
            verified_client.get(reverse("core:pdf_memoria_economica", args=[rentable.project.id])),
            must_have=("resumen",),
        )
        financed_pdf = _response_context(
            verified_client.get(reverse("core:pdf_memoria_economica", args=[financed.project.id])),
            must_have=("resumen",),
        )
        rentable_liq = verified_client.get(reverse("core:proyecto_liquidaciones", args=[rentable.project.id]))
        financed_liq = verified_client.get(reverse("core:proyecto_liquidaciones", args=[financed.project.id]))

    rentable_project = rentable_service["projects"][0]
    financed_project = financed_service["projects"][0]
    for key in ("capital_objetivo", "capital_captado", "capital_pendiente", "beneficio_neto", "beneficio_neto_tras_impuestos", "beneficio_inversure"):
        _assert_money(rentable_project[key], financed_project[key], label=f"financing.{key}")
    for key in ("roi", "margen_neto"):
        _assert_pct(rentable_project[key], financed_project[key], label=f"financing.{key}")

    assert financed.project.snapshot_datos["economico"]["financiacion_pct"] == 70.0
    for key in ("capital_objetivo", "capital_captado", "capital_pendiente", "beneficio_neto", "beneficio_neto_tras_impuestos"):
        _assert_money(rentable_detail["resultado"][key], financed_detail["resultado"][key], label=f"detalle.financing.{key}")
    for key in ("roi", "margen_neto"):
        _assert_pct(rentable_detail["resultado"][key], financed_detail["resultado"][key], label=f"detalle.financing.{key}")

    pdf_key_map = {
        "comision_inversure_eur": "comision_inversure_real",
        "beneficio_neto_inversor": "beneficio_neto_real",
        "impuesto_sociedades": "impuesto_sociedades_real",
        "beneficio_neto_tras_impuestos": "beneficio_neto_real_tras_impuestos",
    }
    for key in ("comision_inversure_eur", "beneficio_neto_inversor", "impuesto_sociedades", "beneficio_neto_tras_impuestos"):
        _assert_money(rentable_detail["inv"][key], financed_detail["inv"][key], label=f"estudio.financing.{key}")
        _assert_money(rentable_pdf["resumen"][pdf_key_map[key]], financed_pdf["resumen"][pdf_key_map[key]], label=f"pdf.financing.{key}")

    _assert_money(
        rentable_liq.json()["liquidaciones"][0]["total_a_percibir"],
        financed_liq.json()["liquidaciones"][0]["total_a_percibir"],
        label="liquidation.financing.total_a_percibir",
    )


def test_partial_contributions_keep_same_client_movements_and_date_filtered_series(verified_client, direccion_user):
    scenario = build_partial_contributions_scenario()
    filters = FinancialDashboardFilters.from_mapping(
        {
            "fecha_desde": "2026-03-01",
            "fecha_hasta": "2026-04-30",
            "proyecto_id": scenario.project.id,
            "estado": scenario.project.estado,
        },
    )

    with _freeze_financial_now():
        service_payload = _service_payload(direccion_user, filters=filters)
        response = _dashboard_response(
            verified_client,
            {
                "fecha_desde": "2026-03-01",
                "fecha_hasta": "2026-04-30",
                "proyecto_id": scenario.project.id,
                "estado": scenario.project.estado,
            },
        )
        detail_context = _response_context(
            verified_client.get(reverse("core:proyecto", args=[scenario.project.id])),
            must_have=("captacion", "resultado", "inv"),
        )
        liquidation_response = verified_client.get(reverse("core:proyecto_liquidaciones", args=[scenario.project.id]))

    _assert_dashboard_payload_matches_endpoint(service_payload, response)
    assert service_payload["period"] == {
        "applied": True,
        "fecha_desde": "2026-03-01",
        "fecha_hasta": "2026-04-30",
        "proyecto_id": scenario.project.id,
        "estado": scenario.project.estado,
        "project_count": 1,
        "range_days": 61,
    }
    investment_rows = service_payload["series"]["monthly"]["investment"]
    assert [row["month"] for row in investment_rows] == ["2026-03-01", "2026-04-01"]
    assert [row["label"] for row in investment_rows] == ["2026-03", "2026-04"]
    _assert_money(investment_rows[0]["total"], Decimal("50000.00"), label="investment.march")
    _assert_money(investment_rows[1]["total"], Decimal("10000.00"), label="investment.april")

    income_rows = service_payload["series"]["monthly"]["income"]
    expense_rows = service_payload["series"]["monthly"]["expense"]
    assert [row["month"] for row in income_rows] == ["2026-03-01", "2026-04-01"]
    assert [row["month"] for row in expense_rows] == ["2026-03-01", "2026-04-01"]
    _assert_money(income_rows[0]["total"], Decimal("0"), label="income.march")
    _assert_money(income_rows[1]["total"], Decimal("0"), label="income.april")
    _assert_money(expense_rows[0]["total"], Decimal("0"), label="expense.march")
    _assert_money(expense_rows[1]["total"], Decimal("0"), label="expense.april")
    assert [row["beneficio"] for row in service_payload["series"]["monthly"]["performance"]] == [Decimal("0"), Decimal("0")]

    participaciones = detail_context["participaciones"]
    assert len(participaciones) == 3
    assert len({part.cliente_id for part in participaciones}) == 2
    assert sum(1 for part in participaciones if part.cliente_id == participaciones[1].cliente_id) == 2
    _assert_money(detail_context["captacion"]["capital_objetivo"], Decimal("100000.00"), label="capital objetivo")
    _assert_money(detail_context["captacion"]["capital_captado"], Decimal("60000.00"), label="capital captado")
    _assert_money(detail_context["captacion"]["restante"], Decimal("40000.00"), label="capital pendiente")
    _assert_pct(detail_context["captacion"]["pct_captado"], Decimal("60.0"), label="pct captado")

    _assert_liquidation_matches(scenario, liquidation_response)
    liquidation_rows = liquidation_response.json()["liquidaciones"]
    assert len(liquidation_rows) == 3
    assert liquidation_rows[0]["fecha"] == "2026-03-05"
    assert liquidation_rows[1]["fecha"] == "2026-03-20"
    assert liquidation_rows[2]["fecha"] == "2026-04-10"
    assert [row["estado"] for row in liquidation_rows] == ["Liquidación prevista"] * 3


def test_closed_project_distinguishes_project_pdf_and_liquidation_tax_bases(verified_client, direccion_user):
    scenario = build_closed_profit_scenario()
    query = _filter_for_project(scenario)
    filters = FinancialDashboardFilters.from_mapping(query)

    with _freeze_financial_now():
        service_payload = _service_payload(direccion_user, filters=filters)
        response = _dashboard_response(verified_client, query)
        detail_context = _response_context(
            verified_client.get(reverse("core:proyecto", args=[scenario.project.id])),
            must_have=("captacion", "resultado", "inv"),
        )
        pdf_context = _response_context(
            verified_client.get(reverse("core:pdf_memoria_economica", args=[scenario.project.id])),
            must_have=("resumen",),
        )
        liquidation_response = verified_client.get(reverse("core:proyecto_liquidaciones", args=[scenario.project.id]))

    _assert_dashboard_payload_matches_endpoint(service_payload, response)
    _assert_project_metrics(scenario, service_payload, detail_context, pdf_context)
    _assert_liquidation_matches(scenario, liquidation_response)

    project_metrics = service_payload["projects"][0]
    _assert_money(project_metrics["beneficio_inversure"], Decimal("5000.00"), label="beneficio inversure")
    _assert_money(detail_context["resultado"]["impuesto_sociedades"], Decimal("12500.00"), label="detalle.impuesto")
    _assert_money(detail_context["inv"]["impuesto_sociedades"], Decimal("11250.00"), label="estudio.impuesto")
    _assert_money(pdf_context["resumen"]["impuesto_sociedades_real"], Decimal("11250.00"), label="pdf.impuesto")
    _assert_pct(detail_context["inv"]["roi_neto_tras_impuestos"], Decimal("33.75"), label="estudio.roi_neto_tras_impuestos")
    _assert_pct(pdf_context["resumen"]["roi_real_tras_impuestos"], Decimal("30.33707865168539"), label="pdf.roi_real_tras_impuestos")
    _assert_money(project_metrics["investment_return"]["retorno_total"], Decimal("136450.00"), label="dashboard.total_a_percibir")
    _assert_money(liquidation_response.json()["resumen"]["total_a_percibir"], Decimal("127337.50"), label="liquidation.total_a_percibir")
    assert liquidation_response.json()["liquidaciones"][0]["estado"] == "Liquidación cerrada"


def test_zero_investment_project_keeps_settlement_and_liquidation_safe(verified_client, direccion_user):
    scenario = build_zero_investment_scenario()
    query = _filter_for_project(scenario)
    filters = FinancialDashboardFilters.from_mapping(query)

    with _freeze_financial_now():
        service_payload = _service_payload(direccion_user, filters=filters)
        response = _dashboard_response(verified_client, query)
        detail_context = _response_context(
            verified_client.get(reverse("core:proyecto", args=[scenario.project.id])),
            must_have=("captacion", "resultado", "inv"),
        )
        liquidation_response = verified_client.get(reverse("core:proyecto_liquidaciones", args=[scenario.project.id]))

    _assert_dashboard_payload_matches_endpoint(service_payload, response)
    investment_return = service_payload["projects"][0]["investment_return"]
    _assert_money(investment_return["capital_invertido"], Decimal("0"), label="investment.capital_invertido")
    _assert_money(investment_return["beneficio_neto"], Decimal("0"), label="investment.beneficio_neto")
    _assert_money(investment_return["retorno_total"], Decimal("0"), label="investment.retorno_total")
    _assert_pct(investment_return["roi_bruto_medio"], Decimal("0"), label="investment.roi_bruto")
    _assert_pct(investment_return["roi_neto_medio"], Decimal("0"), label="investment.roi_neto")
    assert investment_return["participaciones"] == 0
    _assert_money(detail_context["captacion"]["capital_captado"], Decimal("0"), label="capital captado")
    _assert_money(detail_context["captacion"]["pct_captado"], Decimal("0"), label="pct captado")
    assert liquidation_response.json()["liquidaciones"] == []
    for key in ("invertido", "bruto", "retencion", "neto", "total_a_percibir"):
        _assert_money(liquidation_response.json()["resumen"][key], Decimal("0"), label=f"liquidation.{key}")
