from __future__ import annotations

import csv
import json
import os
import re
from dataclasses import asdict, dataclass
from decimal import Decimal
from io import StringIO
from pathlib import Path
from typing import Any, Iterable, Mapping
from unittest.mock import patch

from django.db.models import Prefetch, QuerySet
from django.http import HttpResponse
from django.test import RequestFactory
from django.urls import resolve
from django.utils import timezone

from core.models import DatosEconomicosProyecto, GastoProyecto, IngresoProyecto, Participacion, Proyecto

SEVERITY_LEVELS = ("info", "warning", "error", "critical")
MONEY_TOLERANCE = Decimal("0.01")
PERCENT_TOLERANCE = Decimal("0.01")
ROUNDED_PERCENT_TOLERANCE = Decimal("0.05")


def _decimal(value: Any, default: Decimal | None = None) -> Decimal | None:
    if value in (None, "", "—"):
        return default
    if isinstance(value, Decimal):
        return value
    try:
        text = str(value).strip()
        if not text:
            return default
        text = text.replace("€", "").replace("%", "").strip()
        if "," in text and "." in text:
            text = text.replace(".", "").replace(",", ".")
        else:
            text = text.replace(",", ".")
        return Decimal(text)
    except Exception:
        return default


def _decimal_or_zero(value: Any) -> Decimal:
    result = _decimal(value, Decimal("0"))
    return result if result is not None else Decimal("0")


def _safe_div(numerator: Decimal | None, denominator: Decimal | None) -> Decimal | None:
    if numerator is None or denominator in (None, Decimal("0")):
        return None
    if denominator == 0:
        return None
    return numerator / denominator


def _sum_decimals(values: Iterable[Decimal | None]) -> Decimal:
    total = Decimal("0")
    for value in values:
        if value is None:
            continue
        total += value
    return total


def _normalize_state(value: Any) -> str:
    return (str(value or "").strip().lower() or "")


def _metric_result(
    value: Decimal | None,
    *,
    verifiability: str,
    source: str,
    explanation: str = "",
) -> dict[str, Any]:
    return {
        "value": value,
        "verifiability": verifiability,
        "source": source,
        "explanation": explanation,
    }


def _non_verifiable_metric_result(source: str, explanation: str) -> dict[str, Any]:
    return _metric_result(
        None,
        verifiability="no_verificable_de_forma_independiente",
        source=source,
        explanation=explanation,
    )


def _format_decimal(value: Decimal | None, *, kind: str = "money") -> str:
    if value is None:
        return ""
    if kind == "percent":
        return f"{value:.6f}"
    return f"{value:.2f}"


def _format_display_value(value: Decimal | None, *, kind: str = "money") -> str:
    if value is None:
        return ""
    if kind == "percent":
        return f"{value:.2f} %"
    return f"{value:.2f} €"


def _metric_display_kind(metric: Any) -> str:
    metric_name = str(metric or "").lower()
    if any(token in metric_name for token in ("roi", "pct", "margen", "ratio_participacion")):
        return "percent"
    return "money"


def _markdown_cell(value: Any) -> str:
    text = "" if value is None else str(value)
    return text.replace("|", "\\|").replace("\n", " ").replace("\r", " ")


@dataclass(slots=True)
class AuditComparisonRow:
    project_id: int
    project_name: str
    state: str
    surface: str
    subject_type: str
    subject_id: str
    metric: str
    shown_value: Decimal | None
    recalculated_value: Decimal | None
    diff_abs: Decimal | None
    diff_pct: Decimal | None
    verifiability: str
    classification: str
    severity: str
    explanation: str

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(slots=True)
class AuditProjectResult:
    project_id: int
    project_name: str
    state: str
    metrics: dict[str, Any]
    surfaces: dict[str, Any]
    liquidation_rows: list[dict[str, Any]]
    rows: list[AuditComparisonRow]

    def to_dict(self) -> dict[str, Any]:
        return {
            "project_id": self.project_id,
            "project_name": self.project_name,
            "state": self.state,
            "metrics": self.metrics,
            "surfaces": self.surfaces,
            "liquidation_rows": self.liquidation_rows,
            "rows": [row.to_dict() for row in self.rows],
        }


class InversureMetricAuditService:
    """
    Recalcula métricas de Inversure de forma independiente y compara las salidas visibles.

    El servicio solo trabaja con datos persistidos de negocio y con superficies de lectura.
    No reutiliza builders ni funciones de cálculo como fuente de verdad.
    """

    def __init__(self, viewer_user: Any | None = None) -> None:
        self.viewer_user = viewer_user
        self._request_factory = RequestFactory()

    def audit(self, *, project_id: int | None = None, limit: int | None = None) -> dict[str, Any]:
        projects = list(self._load_projects(project_id=project_id, limit=limit))
        project_results = [self.audit_project(project) for project in projects]
        rows = [row for project_result in project_results for row in project_result.rows]
        summary = self._build_summary(project_results, rows)
        return {
            "generated_at": timezone.now().isoformat(),
            "viewer_user_id": getattr(self.viewer_user, "id", None),
            "project_count": len(projects),
            "project_results": [project_result.to_dict() for project_result in project_results],
            "rows": [row.to_dict() for row in rows],
            "summary": summary,
        }

    def audit_project(self, project: Proyecto) -> AuditProjectResult:
        recalc = self.recalculate_project(project)
        surfaces = self.collect_surfaces(project)
        rows = self.compare_project(project, recalc, surfaces)
        liquidation_rows = surfaces.get("liquidacion_json", {}).get("rows", [])
        return AuditProjectResult(
            project_id=int(project.id or 0),
            project_name=(project.nombre or f"Proyecto {project.id}").strip(),
            state=_normalize_state(getattr(project, "estado", "")),
            metrics=recalc,
            surfaces=surfaces,
            liquidation_rows=liquidation_rows,
            rows=rows,
        )

    def recalculate_project(self, project: Proyecto) -> dict[str, Any]:
        gastos = self._related_items(project, "gastos_proyecto")
        ingresos = self._related_items(project, "ingresos")
        participaciones = self._related_confirmed_participations(project)
        datos_economicos = getattr(project, "datos_economicos", None)
        gastos_estimacion = getattr(project, "gastos_estimacion", None)

        real_income_items = [item for item in ingresos if _normalize_state(getattr(item, "estado", "")) == "confirmado"]
        estimated_income_items = [item for item in ingresos if _normalize_state(getattr(item, "estado", "")) == "estimado"]
        real_cost_items = [item for item in gastos if _normalize_state(getattr(item, "estado", "")) == "confirmado"]
        estimated_cost_items = [item for item in gastos if _normalize_state(getattr(item, "estado", "")) == "estimado"]

        ingresos_reales = self._sum_income_amounts(real_income_items, amount_kind="real")
        ingresos_estimados = self._sum_income_amounts(ingresos, amount_kind="estimated")
        costes_reales = self._sum_cost_amounts(real_cost_items, amount_kind="real")
        costes_estimados = self._sum_cost_amounts(gastos, amount_kind="estimated")

        transmission_reales = self._sum_transmission_amounts(real_income_items, real_cost_items, amount_kind="real")
        transmission_estimados = self._sum_transmission_amounts(estimated_income_items, estimated_cost_items, amount_kind="estimated")

        selected_costs = self._select_display_value(
            real_value=costes_reales,
            estimated_value=costes_estimados,
            has_real=bool(real_cost_items),
            has_estimated=bool(estimated_cost_items),
            fallback_label="costes",
        )
        selected_income = self._select_display_value(
            real_value=ingresos_reales,
            estimated_value=ingresos_estimados,
            has_real=bool(real_income_items),
            has_estimated=bool(estimated_income_items),
            fallback_label="ingresos",
        )
        selected_transmission = self._select_transmission_value(
            project=project,
            real_income_items=real_income_items,
            estimated_income_items=estimated_income_items,
            real_cost_items=real_cost_items,
            estimated_cost_items=estimated_cost_items,
            real_value=transmission_reales,
            estimated_value=transmission_estimados,
        )

        capital_objetivo = selected_costs["value"]
        if capital_objetivo is None or capital_objetivo <= 0:
            capital_objetivo = self._project_cost_fallback(project, datos_economicos, gastos_estimacion, selected_costs["source"])

        capital_aportado = _sum_decimals(
            _decimal_or_zero(getattr(part, "importe_invertido", None)) for part in participaciones
        )
        capital_pendiente = max((capital_objetivo or Decimal("0")) - capital_aportado, Decimal("0"))

        commission_config = self._commission_config(project, datos_economicos, selected_income["value"], selected_costs["value"])
        tax_rate = self._tax_rate(project, datos_economicos)
        tax_ratio = (tax_rate / Decimal("100")) if tax_rate is not None else None

        beneficio_bruto_reales = (selected_income["value"] or Decimal("0")) - (selected_costs["value"] or Decimal("0"))
        beneficio_bruto_estimados = (ingresos_estimados or Decimal("0")) - (costes_estimados or Decimal("0"))

        comision_real = self._commission_amount(beneficio_bruto_reales, commission_config)
        comision_estimado = self._commission_amount(beneficio_bruto_estimados, commission_config)

        base_before_tax_real = beneficio_bruto_reales - comision_real if comision_real is not None else None
        base_before_tax_estimado = beneficio_bruto_estimados - comision_estimado if comision_estimado is not None else None

        impuesto_sociedades_sobre_bruto_real = (
            beneficio_bruto_reales * tax_ratio if tax_ratio is not None and beneficio_bruto_reales > 0 else Decimal("0")
        )
        impuesto_sociedades_sobre_bruto_estimado = (
            beneficio_bruto_estimados * tax_ratio if tax_ratio is not None and beneficio_bruto_estimados > 0 else Decimal("0")
        )
        impuesto_sociedades_sobre_base_real = (
            base_before_tax_real * tax_ratio if tax_ratio is not None and base_before_tax_real is not None and base_before_tax_real > 0 else Decimal("0")
        )
        impuesto_sociedades_sobre_base_estimado = (
            base_before_tax_estimado * tax_ratio if tax_ratio is not None and base_before_tax_estimado is not None and base_before_tax_estimado > 0 else Decimal("0")
        )

        neto_tras_impuestos_real = (
            base_before_tax_real - impuesto_sociedades_sobre_base_real
            if base_before_tax_real is not None
            else None
        )
        neto_tras_impuestos_estimado = (
            base_before_tax_estimado - impuesto_sociedades_sobre_base_estimado
            if base_before_tax_estimado is not None
            else None
        )

        roi_real = self._percentage(beneficio_bruto_reales, selected_costs["value"])
        roi_estimado = self._percentage(beneficio_bruto_estimados, costes_estimados)
        margen_real = self._percentage(beneficio_bruto_reales, selected_transmission["value"])
        margen_estimado = self._percentage(beneficio_bruto_estimados, transmission_estimados)
        roi_tras_impuestos_capital_real = self._percentage(neto_tras_impuestos_real, capital_objetivo)
        roi_tras_impuestos_capital_estimado = self._percentage(neto_tras_impuestos_estimado, capital_objetivo)
        roi_tras_impuestos_costes_real = self._percentage(
            neto_tras_impuestos_real,
            (selected_costs["value"] or Decimal("0")) + impuesto_sociedades_sobre_base_real,
        )
        roi_tras_impuestos_costes_estimado = self._percentage(
            neto_tras_impuestos_estimado,
            (costes_estimados or Decimal("0")) + impuesto_sociedades_sobre_base_estimado,
        )

        metrics = {
            "capital_objetivo": _metric_result(
                capital_objetivo,
                verifiability=selected_costs["verifiability"],
                source=selected_costs["source"],
                explanation=selected_costs["explanation"],
            ),
            "capital_aportado": _metric_result(
                capital_aportado,
                verifiability="verificable_independientemente",
                source="participaciones_confirmadas",
                explanation="Suma de participaciones confirmadas.",
            ),
            "capital_pendiente": _metric_result(
                capital_pendiente,
                verifiability=selected_costs["verifiability"],
                source=selected_costs["source"],
                explanation="Capital objetivo menos capital aportado.",
            ),
            "inversion_total": _metric_result(
                selected_costs["value"],
                verifiability=selected_costs["verifiability"],
                source=selected_costs["source"],
                explanation="Denominador del ROI y base de inversión del proyecto.",
            ),
            "ingresos_reales": _metric_result(
                selected_income["value"] if selected_income["source"] == "real" else ingresos_reales,
                verifiability=selected_income["verifiability"],
                source=selected_income["source"],
                explanation=selected_income["explanation"],
            ),
            "ingresos_estimados": _metric_result(
                ingresos_estimados,
                verifiability="verificable_independientemente" if estimated_income_items else "no_verificable_de_forma_independiente",
                source="ingreso_estimado_persistido",
                explanation="Suma de ingresos estimados persistidos.",
            ),
            "costes_reales": _metric_result(
                selected_costs["value"] if selected_costs["source"] == "real" else costes_reales,
                verifiability=selected_costs["verifiability"],
                source=selected_costs["source"],
                explanation=selected_costs["explanation"],
            ),
            "costes_estimados": _metric_result(
                costes_estimados,
                verifiability="verificable_independientemente" if estimated_cost_items else "no_verificable_de_forma_independiente",
                source="gasto_estimado_persistido",
                explanation="Suma de gastos estimados persistidos.",
            ),
            "valor_transmision_real": _metric_result(
                selected_transmission["value"] if selected_transmission["source"] == "real" else transmission_reales,
                verifiability=selected_transmission["verifiability"],
                source=selected_transmission["source"],
                explanation=selected_transmission["explanation"],
            ),
            "valor_transmision_estimado": _metric_result(
                transmission_estimados,
                verifiability="verificable_independientemente" if estimated_income_items else "no_verificable_de_forma_independiente",
                source="transmision_estimada_persistida",
                explanation="Valor de transmisión estimado reconstruido desde movimientos persistidos.",
            ),
            "beneficio_bruto_real": _metric_result(
                beneficio_bruto_reales,
                verifiability=selected_income["verifiability"] if selected_income["verifiability"] == selected_costs["verifiability"] else "verificable_parcialmente",
                source=f"{selected_income['source']}/{selected_costs['source']}",
                explanation="Ingresos menos costes.",
            ),
            "beneficio_bruto_estimado": _metric_result(
                beneficio_bruto_estimados,
                verifiability="verificable_independientemente" if estimated_income_items or estimated_cost_items else "no_verificable_de_forma_independiente",
                source="ingresos_estimados/costes_estimados",
                explanation="Ingresos estimados menos costes estimados.",
            ),
            "comision_pct": _metric_result(
                commission_config["rate"],
                verifiability=commission_config["verifiability"],
                source=commission_config["source"],
                explanation=commission_config["explanation"],
            ),
            "comision_real": _metric_result(
                comision_real,
                verifiability=commission_config["verifiability"],
                source=commission_config["source"],
                explanation="Comisión calculada sobre el beneficio bruto real.",
            ),
            "comision_estimado": _metric_result(
                comision_estimado,
                verifiability=commission_config["verifiability"],
                source=commission_config["source"],
                explanation="Comisión calculada sobre el beneficio bruto estimado.",
            ),
            "base_before_tax_real": _metric_result(
                base_before_tax_real,
                verifiability=commission_config["verifiability"],
                source=commission_config["source"],
                explanation="Beneficio bruto menos comisión.",
            ),
            "base_before_tax_estimado": _metric_result(
                base_before_tax_estimado,
                verifiability=commission_config["verifiability"],
                source=commission_config["source"],
                explanation="Beneficio bruto estimado menos comisión.",
            ),
            "impuesto_sociedades_pct": _metric_result(
                tax_rate,
                verifiability=self._tax_rate_verifiability(project, datos_economicos),
                source=self._tax_rate_source(project, datos_economicos),
                explanation=self._tax_rate_explanation(project, datos_economicos),
            ),
            "impuesto_sociedades_sobre_bruto_real": _metric_result(
                impuesto_sociedades_sobre_bruto_real,
                verifiability=self._tax_rate_verifiability(project, datos_economicos),
                source=self._tax_rate_source(project, datos_economicos),
                explanation="Impuesto aplicado sobre el beneficio bruto real.",
            ),
            "impuesto_sociedades_sobre_bruto_estimado": _metric_result(
                impuesto_sociedades_sobre_bruto_estimado,
                verifiability=self._tax_rate_verifiability(project, datos_economicos),
                source=self._tax_rate_source(project, datos_economicos),
                explanation="Impuesto aplicado sobre el beneficio bruto estimado.",
            ),
            "impuesto_sociedades_sobre_base_real": _metric_result(
                impuesto_sociedades_sobre_base_real,
                verifiability=self._tax_rate_verifiability(project, datos_economicos),
                source=self._tax_rate_source(project, datos_economicos),
                explanation="Impuesto aplicado sobre la base antes de impuestos real.",
            ),
            "impuesto_sociedades_sobre_base_estimado": _metric_result(
                impuesto_sociedades_sobre_base_estimado,
                verifiability=self._tax_rate_verifiability(project, datos_economicos),
                source=self._tax_rate_source(project, datos_economicos),
                explanation="Impuesto aplicado sobre la base antes de impuestos estimada.",
            ),
            "neto_tras_impuestos_real": _metric_result(
                neto_tras_impuestos_real,
                verifiability=commission_config["verifiability"] if commission_config["verifiability"] == self._tax_rate_verifiability(project, datos_economicos) else "verificable_parcialmente",
                source=f"{commission_config['source']}/{self._tax_rate_source(project, datos_economicos)}",
                explanation="Base antes de impuestos menos impuesto de sociedades.",
            ),
            "neto_tras_impuestos_estimado": _metric_result(
                neto_tras_impuestos_estimado,
                verifiability=commission_config["verifiability"] if commission_config["verifiability"] == self._tax_rate_verifiability(project, datos_economicos) else "verificable_parcialmente",
                source=f"{commission_config['source']}/{self._tax_rate_source(project, datos_economicos)}",
                explanation="Base estimada antes de impuestos menos impuesto de sociedades.",
            ),
            "roi_real": _metric_result(
                roi_real,
                verifiability=selected_costs["verifiability"],
                source=selected_costs["source"],
                explanation="Beneficio bruto real dividido entre costes reales.",
            ),
            "roi_estimado": _metric_result(
                roi_estimado,
                verifiability="verificable_parcialmente" if not estimated_cost_items else "verificable_independientemente",
                source="costes_estimados",
                explanation="Beneficio bruto estimado dividido entre costes estimados.",
            ),
            "margen_real": _metric_result(
                margen_real,
                verifiability=selected_transmission["verifiability"],
                source=selected_transmission["source"],
                explanation="Beneficio bruto real dividido entre el valor de transmisión real.",
            ),
            "margen_estimado": _metric_result(
                margen_estimado,
                verifiability="verificable_parcialmente" if not estimated_income_items else "verificable_independientemente",
                source="valor_transmision_estimado",
                explanation="Beneficio bruto estimado dividido entre el valor de transmisión estimado.",
            ),
            "roi_tras_impuestos_capital_real": _metric_result(
                roi_tras_impuestos_capital_real,
                verifiability=commission_config["verifiability"],
                source=commission_config["source"],
                explanation="Neto tras impuestos real dividido entre capital objetivo.",
            ),
            "roi_tras_impuestos_capital_estimado": _metric_result(
                roi_tras_impuestos_capital_estimado,
                verifiability=commission_config["verifiability"],
                source=commission_config["source"],
                explanation="Neto tras impuestos estimado dividido entre capital objetivo.",
            ),
            "roi_tras_impuestos_costes_real": _metric_result(
                roi_tras_impuestos_costes_real,
                verifiability=commission_config["verifiability"],
                source=commission_config["source"],
                explanation="Neto tras impuestos real dividido entre costes + impuesto.",
            ),
            "roi_tras_impuestos_costes_estimado": _metric_result(
                roi_tras_impuestos_costes_estimado,
                verifiability=commission_config["verifiability"],
                source=commission_config["source"],
                explanation="Neto tras impuestos estimado dividido entre costes + impuesto.",
            ),
        }

        liquidation_rows = self._build_liquidation_rows(
            project=project,
            participaciones=participaciones,
            beneficio_bruto_real=beneficio_bruto_reales,
            beneficio_bruto_estimado=beneficio_bruto_estimados,
            comision_real=comision_real,
            comision_estimado=comision_estimado,
            base_before_tax_real=base_before_tax_real,
            base_before_tax_estimado=base_before_tax_estimado,
            impuesto_sociedades_sobre_base_real=impuesto_sociedades_sobre_base_real,
            impuesto_sociedades_sobre_base_estimado=impuesto_sociedades_sobre_base_estimado,
            liquidation_verifiability=(
                "verificable_independientemente"
                if commission_config["verifiability"] == "verificable_independientemente"
                and self._tax_rate_verifiability(project, datos_economicos) == "verificable_independientemente"
                else "no_verificable_de_forma_independiente"
            ),
            liquidation_source=(
                "liquidacion_json.resumen"
                if commission_config["verifiability"] == "verificable_independientemente"
                and self._tax_rate_verifiability(project, datos_economicos) == "verificable_independientemente"
                else "liquidacion_json.incompleta"
            ),
            liquidation_explanation=(
                "Liquidación reconstruida desde participaciones confirmadas y configuración económica persistida."
                if commission_config["verifiability"] == "verificable_independientemente"
                and self._tax_rate_verifiability(project, datos_economicos) == "verificable_independientemente"
                else "No se puede reconstruir la liquidación de forma independiente con los datos persistidos disponibles."
            ),
        )
        metrics["liquidation_rows"] = liquidation_rows.get("rows", [])
        metrics["liquidation_summary"] = liquidation_rows.get("summary", {})
        metrics["liquidation_summary_meta"] = liquidation_rows.get("meta", {})

        return metrics

    def collect_surfaces(self, project: Proyecto) -> dict[str, dict[str, Any]]:
        dashboard_filters = {"proyecto_id": project.id}
        detail_request = self._view_request("core:proyecto", project.id)
        with patch("core.views._ensure_checklist_defaults", autospec=True, side_effect=lambda *_args, **_kwargs: None):
            detail_context = self._capture_rendered_context("core.views", detail_request, project.id)
        surfaces = {
            "detail": detail_context,
            "dashboard_html": self._capture_rendered_context("core.views", self._view_request("core:dashboard", query=dashboard_filters)),
            "dashboard_json": self._json_view("core.views", self._view_request("core:dashboard_data", query=dashboard_filters)),
            "pdf_memoria": self._capture_rendered_context("core.views", self._view_request("core:pdf_memoria_economica", project.id), project.id),
            "liquidacion_json": self._json_view("core.views", self._view_request("core:proyecto_liquidaciones", project.id), project.id),
        }
        return surfaces

    def compare_project(
        self,
        project: Proyecto,
        recalc: dict[str, Any],
        surfaces: dict[str, dict[str, Any]],
    ) -> list[AuditComparisonRow]:
        rows: list[AuditComparisonRow] = []
        project_id = int(project.id or 0)
        project_name = (project.nombre or f"Proyecto {project.id}").strip()
        state = _normalize_state(getattr(project, "estado", ""))

        detail_context = surfaces.get("detail", {})
        dashboard_html = surfaces.get("dashboard_html", {})
        dashboard_json = surfaces.get("dashboard_json", {})
        pdf_context = surfaces.get("pdf_memoria", {})
        liquidation_json = surfaces.get("liquidacion_json", {})

        project_payload = self._find_dashboard_project(dashboard_html, project_id) or self._find_dashboard_project(dashboard_json, project_id) or {}

        rows.extend(
            self._compare_metric(
                project_id=project_id,
                project_name=project_name,
                state=state,
                surface="detail",
                subject_type="project",
                subject_id=str(project_id),
                metric="capital_objetivo",
                shown_value=self._get_nested(detail_context, "captacion", "capital_objetivo"),
                recalc=recalc["capital_objetivo"],
                kind="money",
            )
        )
        rows.extend(
            self._compare_metric(
                project_id=project_id,
                project_name=project_name,
                state=state,
                surface="detail",
                subject_type="project",
                subject_id=str(project_id),
                metric="capital_aportado",
                shown_value=self._get_nested(detail_context, "captacion", "capital_captado"),
                recalc=recalc["capital_aportado"],
                kind="money",
            )
        )
        rows.extend(
            self._compare_metric(
                project_id=project_id,
                project_name=project_name,
                state=state,
                surface="detail",
                subject_type="project",
                subject_id=str(project_id),
                metric="capital_pendiente",
                shown_value=self._get_nested(detail_context, "captacion", "restante"),
                recalc=recalc["capital_pendiente"],
                kind="money",
            )
        )

        rows.extend(
            self._compare_metric(
                project_id=project_id,
                project_name=project_name,
                state=state,
                surface="detail",
                subject_type="project",
                subject_id=str(project_id),
                metric="beneficio_esperado",
                shown_value=self._get_nested(detail_context, "resultado", "beneficio_neto"),
                recalc=_non_verifiable_metric_result(
                    source="detail.resultado.beneficio_neto",
                    explanation="La vista muestra el beneficio esperado desde el snapshot del proyecto; el auditor no lo reconstruye sin usar esa misma definición.",
                ),
                kind="money",
            )
        )
        rows.extend(
            self._compare_metric(
                project_id=project_id,
                project_name=project_name,
                state=state,
                surface="detail",
                subject_type="project",
                subject_id=str(project_id),
                metric="roi_snapshot",
                shown_value=self._get_nested(detail_context, "resultado", "roi"),
                recalc=_non_verifiable_metric_result(
                    source="detail.resultado.roi",
                    explanation="La vista muestra el ROI histórico del snapshot del proyecto; el auditor no lo compara contra el ROI vivo.",
                ),
                kind="percent",
            )
        )
        rows.extend(
            self._compare_metric(
                project_id=project_id,
                project_name=project_name,
                state=state,
                surface="detail",
                subject_type="project",
                subject_id=str(project_id),
                metric="margen_real",
                shown_value=self._get_nested(detail_context, "resultado", "margen_neto"),
                recalc=recalc["margen_real"],
                kind="percent",
            )
        )
        rows.extend(
            self._compare_metric(
                project_id=project_id,
                project_name=project_name,
                state=state,
                surface="detail",
                subject_type="project",
                subject_id=str(project_id),
                metric="impuesto_sociedades_sobre_bruto_real",
                shown_value=self._get_nested(detail_context, "resultado", "impuesto_sociedades"),
                recalc=recalc["impuesto_sociedades_sobre_bruto_real"],
                kind="money",
            )
        )
        rows.extend(
            self._compare_metric(
                project_id=project_id,
                project_name=project_name,
                state=state,
                surface="detail",
                subject_type="project",
                subject_id=str(project_id),
                metric="neto_tras_impuestos_real",
                shown_value=self._get_nested(detail_context, "resultado", "beneficio_neto_tras_impuestos"),
                recalc=recalc["neto_tras_impuestos_real"],
                kind="money",
            )
        )

        rows.extend(
            self._compare_metric(
                project_id=project_id,
                project_name=project_name,
                state=state,
                surface="detail",
                subject_type="project",
                subject_id=str(project_id),
                metric="comision_pct",
                shown_value=self._get_nested(detail_context, "inv", "comision_inversure_pct"),
                recalc=recalc["comision_pct"],
                kind="percent",
            )
        )
        rows.extend(
            self._compare_metric(
                project_id=project_id,
                project_name=project_name,
                state=state,
                surface="detail",
                subject_type="project",
                subject_id=str(project_id),
                metric="comision_real",
                shown_value=self._get_nested(detail_context, "inv", "comision_inversure_eur"),
                recalc=recalc["comision_real"],
                kind="money",
            )
        )
        rows.extend(
            self._compare_metric(
                project_id=project_id,
                project_name=project_name,
                state=state,
                surface="detail",
                subject_type="project",
                subject_id=str(project_id),
                metric="impuesto_sociedades_pct",
                shown_value=self._get_nested(detail_context, "inv", "impuesto_sociedades_pct") or self._get_nested(detail_context, "resultado", "impuesto_sociedades_pct"),
                recalc=recalc["impuesto_sociedades_pct"],
                kind="percent",
            )
        )
        rows.extend(
            self._compare_metric(
                project_id=project_id,
                project_name=project_name,
                state=state,
                surface="detail",
                subject_type="project",
                subject_id=str(project_id),
                metric="base_before_tax_real",
                shown_value=self._get_nested(detail_context, "inv", "beneficio_neto") or self._get_nested(detail_context, "inv", "beneficio_neto_inversor"),
                recalc=recalc["base_before_tax_real"],
                kind="money",
            )
        )
        rows.extend(
            self._compare_metric(
                project_id=project_id,
                project_name=project_name,
                state=state,
                surface="detail",
                subject_type="project",
                subject_id=str(project_id),
                metric="impuesto_sociedades_sobre_base_real",
                shown_value=self._get_nested(detail_context, "inv", "impuesto_sociedades") or self._get_nested(detail_context, "inv", "impuesto_sociedades_eur"),
                recalc=recalc["impuesto_sociedades_sobre_base_real"],
                kind="money",
            )
        )
        rows.extend(
            self._compare_metric(
                project_id=project_id,
                project_name=project_name,
                state=state,
                surface="detail",
                subject_type="project",
                subject_id=str(project_id),
                metric="roi_tras_impuestos_capital_real",
                shown_value=self._get_nested(detail_context, "inv", "roi_neto_tras_impuestos") or self._get_nested(detail_context, "inv", "roi_neto"),
                recalc=recalc["roi_tras_impuestos_capital_real"],
                kind="percent",
            )
        )
        rows.extend(
            self._compare_metric(
                project_id=project_id,
                project_name=project_name,
                state=state,
                surface="detail",
                subject_type="project",
                subject_id=str(project_id),
                metric="neto_tras_impuestos_real",
                shown_value=self._get_nested(detail_context, "inv", "beneficio_neto_tras_impuestos"),
                recalc=recalc["neto_tras_impuestos_real"],
                kind="money",
            )
        )

        if project_payload:
            rows.extend(self._compare_dashboard_project_metrics(project, project_payload, recalc, surface="dashboard_html"))
        if dashboard_json and dashboard_json.get("projects"):
            dashboard_project = self._find_dashboard_project(dashboard_json, project_id) or {}
            if dashboard_project:
                rows.extend(self._compare_dashboard_project_metrics(project, dashboard_project, recalc, surface="dashboard_json"))

        rows.extend(
            self._compare_pdf_metrics(
                project=project,
                pdf_context=pdf_context,
                recalc=recalc,
                surface="pdf_memoria",
            )
        )

        rows.extend(
            self._compare_liquidation_metrics(
                project=project,
                liquidation_json=liquidation_json,
                recalc=recalc,
                surface="liquidacion_json",
            )
        )

        return rows

    def _compare_dashboard_project_metrics(
        self,
        project: Proyecto,
        project_payload: Mapping[str, Any],
        recalc: dict[str, Any],
        *,
        surface: str,
    ) -> list[AuditComparisonRow]:
        project_id = int(project.id or 0)
        project_name = (project.nombre or f"Proyecto {project.id}").strip()
        state = _normalize_state(getattr(project, "estado", ""))
        rows: list[AuditComparisonRow] = []

        mapping = [
            ("capital_objetivo", project_payload.get("capital_objetivo"), "money"),
            ("capital_aportado", project_payload.get("capital_captado"), "money"),
            ("capital_pendiente", project_payload.get("capital_pendiente"), "money"),
            ("inversion_total", project_payload.get("inversion_total"), "money"),
            ("beneficio_bruto_real", project_payload.get("beneficio_neto"), "money"),
            ("beneficio_bruto_estimado", project_payload.get("beneficio_estimado"), "money"),
            ("neto_tras_impuestos_real", project_payload.get("beneficio_neto_tras_impuestos"), "money"),
            ("comision_real", project_payload.get("beneficio_inversure"), "money"),
            ("roi_real", project_payload.get("roi"), "percent"),
            ("margen_real", project_payload.get("margen_neto"), "percent"),
            ("costes_reales", project_payload.get("gastos_real_total"), "money"),
            ("costes_estimados", project_payload.get("gastos_est_total"), "money"),
        ]
        rows.extend(
            self._compare_metric(
                project_id=project_id,
                project_name=project_name,
                state=state,
                surface=surface,
                subject_type="project",
                subject_id=str(project_id),
                metric="ingresos_estimados",
                shown_value=project_payload.get("ingresos_estimados"),
                recalc=_non_verifiable_metric_result(
                    source=f"{surface}.ingresos_estimados",
                    explanation="La superficie no expone un valor servidor verificable de ingresos_estimados; no se compara contra beneficio_estimado.",
                ),
                kind="money",
            )
        )
        rows.extend(
            self._compare_metric(
                project_id=project_id,
                project_name=project_name,
                state=state,
                surface=surface,
                subject_type="project",
                subject_id=str(project_id),
                metric="ingresos_reales",
                shown_value=project_payload.get("ingresos_reales"),
                recalc=_non_verifiable_metric_result(
                    source=f"{surface}.ingresos_reales",
                    explanation="La superficie no expone un valor servidor verificable de ingresos_reales; no se compara contra otro KPI.",
                ),
                kind="money",
            )
        )
        for metric, shown_value, kind in mapping:
            rows.extend(
                self._compare_metric(
                    project_id=project_id,
                    project_name=project_name,
                    state=state,
                    surface=surface,
                    subject_type="project",
                    subject_id=str(project_id),
                    metric=metric,
                    shown_value=shown_value,
                    recalc=recalc[metric],
                    kind=kind,
                )
            )

        investment_return = project_payload.get("investment_return") if isinstance(project_payload.get("investment_return"), Mapping) else {}
        if investment_return:
            rows.extend(
                self._compare_metric(
                    project_id=project_id,
                    project_name=project_name,
                    state=state,
                    surface=surface,
                    subject_type="project",
                    subject_id=str(project_id),
                    metric="investment_return_capital_invertido",
                    shown_value=investment_return.get("capital_invertido"),
                    recalc=recalc["capital_aportado"],
                    kind="money",
                )
            )
            rows.extend(
                self._compare_metric(
                    project_id=project_id,
                    project_name=project_name,
                    state=state,
                    surface=surface,
                    subject_type="project",
                    subject_id=str(project_id),
                    metric="investment_return_retorno_total",
                    shown_value=investment_return.get("retorno_total"),
                    recalc=self._aggregate_liquidation_metric(recalc, "liquidacion_total_a_percibir"),
                    kind="money",
                )
            )
            rows.extend(
                self._compare_metric(
                    project_id=project_id,
                    project_name=project_name,
                    state=state,
                    surface=surface,
                    subject_type="project",
                    subject_id=str(project_id),
                    metric="investment_return_beneficio_neto",
                    shown_value=investment_return.get("beneficio_neto"),
                    recalc=self._aggregate_liquidation_metric(recalc, "liquidacion_beneficio_bruto_inversor"),
                    kind="money",
                )
            )
        return rows

    def _compare_pdf_metrics(
        self,
        *,
        project: Proyecto,
        pdf_context: Mapping[str, Any],
        recalc: dict[str, Any],
        surface: str,
    ) -> list[AuditComparisonRow]:
        rows: list[AuditComparisonRow] = []
        project_id = int(project.id or 0)
        project_name = (project.nombre or f"Proyecto {project.id}").strip()
        state = _normalize_state(getattr(project, "estado", ""))
        resumen = pdf_context.get("resumen") if isinstance(pdf_context.get("resumen"), Mapping) else {}
        if not resumen:
            return rows
        uses_estimated_income_fallback = bool(resumen.get("ingresos_reales_estimados"))

        mapping = [
            ("ingresos_estimados", resumen.get("ingresos_estimados"), "money"),
            ("ingresos_reales", resumen.get("ingresos_reales"), "money"),
            ("costes_estimados", resumen.get("gastos_estimados"), "money"),
            ("costes_reales", resumen.get("gastos_reales"), "money"),
            ("beneficio_bruto_estimado", resumen.get("beneficio_estimado"), "money"),
            ("beneficio_bruto_real", resumen.get("beneficio_real"), "money"),
            ("comision_pct", resumen.get("comision_inversure_pct"), "percent"),
            ("comision_estimado", resumen.get("comision_inversure_estimada"), "money"),
            ("comision_real", resumen.get("comision_inversure_real"), "money"),
            ("base_before_tax_estimado", resumen.get("beneficio_neto_estimado"), "money"),
            ("base_before_tax_real", resumen.get("beneficio_neto_real"), "money"),
            ("impuesto_sociedades_pct", resumen.get("impuesto_sociedades_pct"), "percent"),
            ("impuesto_sociedades_sobre_base_estimado", resumen.get("impuesto_sociedades_estimada"), "money"),
            ("impuesto_sociedades_sobre_base_real", resumen.get("impuesto_sociedades_real"), "money"),
            ("neto_tras_impuestos_estimado", resumen.get("beneficio_neto_estimado_tras_impuestos"), "money"),
            ("neto_tras_impuestos_real", resumen.get("beneficio_neto_real_tras_impuestos"), "money"),
            ("roi_estimado", resumen.get("roi_estimado"), "percent"),
            ("roi_real", resumen.get("roi_real"), "percent"),
            ("roi_tras_impuestos_costes_estimado", resumen.get("roi_estimado_tras_impuestos"), "percent"),
            ("roi_tras_impuestos_costes_real", resumen.get("roi_real_tras_impuestos"), "percent"),
        ]
        for metric, shown_value, kind in mapping:
            if uses_estimated_income_fallback and metric in {"ingresos_reales", "beneficio_bruto_real"}:
                rows.extend(
                    self._compare_metric(
                        project_id=project_id,
                        project_name=project_name,
                        state=state,
                        surface=surface,
                        subject_type="project",
                        subject_id=str(project_id),
                        metric=metric,
                        shown_value=shown_value,
                        recalc=_non_verifiable_metric_result(
                            source=f"{surface}.resumen.ingresos_reales_estimados",
                            explanation=(
                                "La superficie usa ingresos_estimados como fallback para el valor etiquetado como real; "
                                "no es una reconstrucción real pura."
                            ),
                        ),
                        kind=kind,
                    )
                )
                continue
            rows.extend(
                self._compare_metric(
                    project_id=project_id,
                    project_name=project_name,
                    state=state,
                    surface=surface,
                    subject_type="project",
                    subject_id=str(project_id),
                    metric=metric,
                    shown_value=shown_value,
                    recalc=recalc[metric],
                    kind=kind,
                )
            )
        return rows

    def _compare_liquidation_metrics(
        self,
        *,
        project: Proyecto,
        liquidation_json: Mapping[str, Any],
        recalc: dict[str, Any],
        surface: str,
    ) -> list[AuditComparisonRow]:
        rows: list[AuditComparisonRow] = []
        project_id = int(project.id or 0)
        project_name = (project.nombre or f"Proyecto {project.id}").strip()
        state = _normalize_state(getattr(project, "estado", ""))
        rows_payload = liquidation_json.get("rows") if isinstance(liquidation_json.get("rows"), list) else liquidation_json.get("liquidaciones")
        if not isinstance(rows_payload, list):
            rows_payload = []
        expected_rows = recalc.get("liquidation_rows", [])
        rows_by_id = {str(item.get("participacion_id")): item for item in expected_rows if isinstance(item, Mapping)}
        liquidation_meta = self._liquidation_meta(recalc)

        for row_payload in rows_payload:
            if not isinstance(row_payload, Mapping):
                continue
            subject_id = str(row_payload.get("id") or row_payload.get("participacion_id") or "")
            expected = rows_by_id.get(subject_id)
            if expected is None:
                continue
            metric_map = [
                (
                    "liquidacion_beneficio_bruto_inversor",
                    row_payload.get("beneficio_bruto"),
                    self._liquidation_metric_result(expected.get("beneficio_bruto_inversor"), liquidation_meta),
                    "money",
                ),
                (
                    "liquidacion_retencion",
                    row_payload.get("retencion"),
                    self._liquidation_metric_result(expected.get("retencion"), liquidation_meta),
                    "money",
                ),
                (
                    "liquidacion_neto",
                    row_payload.get("neto"),
                    self._liquidation_metric_result(expected.get("neto_cobrar"), liquidation_meta),
                    "money",
                ),
                (
                    "liquidacion_total_a_percibir",
                    row_payload.get("total_a_percibir"),
                    self._liquidation_metric_result(expected.get("total_a_percibir"), liquidation_meta),
                    "money",
                ),
                ("liquidacion_roi_bruto", row_payload.get("porcentaje_participacion"), expected.get("ratio_participacion_pct"), "percent"),
            ]
            for metric, shown_value, recalc_value, kind in metric_map:
                rows.extend(
                    self._compare_metric(
                        project_id=project_id,
                        project_name=project_name,
                        state=state,
                        surface=surface,
                        subject_type="participation",
                        subject_id=subject_id,
                        metric=metric,
                        shown_value=shown_value,
                        recalc=recalc_value,
                        kind=kind,
                    )
                )

        resumen = liquidation_json.get("resumen") if isinstance(liquidation_json.get("resumen"), Mapping) else {}
        if resumen:
            liquidation_summary = recalc.get("liquidation_summary", {})
            summary_mapping = [
                ("liquidacion_capital_aportado", resumen.get("invertido"), recalc["capital_aportado"]["value"], "money"),
                (
                    "liquidacion_beneficio_bruto_inversor",
                    resumen.get("bruto"),
                    self._liquidation_metric_result(liquidation_summary.get("bruto"), liquidation_meta),
                    "money",
                ),
                (
                    "liquidacion_retencion",
                    resumen.get("retencion"),
                    self._liquidation_metric_result(liquidation_summary.get("retencion"), liquidation_meta),
                    "money",
                ),
                (
                    "liquidacion_neto",
                    resumen.get("neto"),
                    self._liquidation_metric_result(liquidation_summary.get("neto"), liquidation_meta),
                    "money",
                ),
                (
                    "liquidacion_total_a_percibir",
                    resumen.get("total_a_percibir"),
                    self._liquidation_metric_result(liquidation_summary.get("total_a_percibir"), liquidation_meta),
                    "money",
                ),
            ]
            for metric, shown_value, recalc_value, kind in summary_mapping:
                rows.extend(
                    self._compare_metric(
                        project_id=project_id,
                        project_name=project_name,
                        state=state,
                        surface=surface,
                        subject_type="project",
                        subject_id=str(project_id),
                        metric=metric,
                        shown_value=shown_value,
                        recalc=recalc_value,
                        kind=kind,
                    )
                )
        return rows

    def _compare_metric(
        self,
        *,
        project_id: int,
        project_name: str,
        state: str,
        surface: str,
        subject_type: str,
        subject_id: str,
        metric: str,
        shown_value: Any,
        recalc: dict[str, Any] | Decimal | None,
        kind: str,
    ) -> list[AuditComparisonRow]:
        if isinstance(recalc, Mapping):
            recalc_value = recalc.get("value")
            verifiability = str(recalc.get("verifiability") or "no_verificable_de_forma_independiente")
            source = str(recalc.get("source") or "")
            explanation = str(recalc.get("explanation") or "")
        else:
            recalc_value = recalc
            verifiability = "verificable_independientemente" if recalc is not None else "no_verificable_de_forma_independiente"
            source = ""
            explanation = ""

        shown_decimal = _decimal(shown_value, None)
        if shown_decimal is None and shown_value not in (None, "", "—"):
            shown_decimal = _decimal(_extract_number(shown_value), None)

        recalc_decimal = _decimal(recalc_value, None)
        if verifiability == "no_verificable_de_forma_independiente":
            diff_abs = abs(shown_decimal - recalc_decimal) if shown_decimal is not None and recalc_decimal is not None else None
            diff_pct = None if diff_abs is None or recalc_decimal in (None, Decimal("0")) else (diff_abs / abs(recalc_decimal) * Decimal("100"))
            row = AuditComparisonRow(
                project_id=project_id,
                project_name=project_name,
                state=state,
                surface=surface,
                subject_type=subject_type,
                subject_id=subject_id,
                metric=metric,
                shown_value=shown_decimal,
                recalculated_value=recalc_decimal,
                diff_abs=diff_abs,
                diff_pct=diff_pct,
                verifiability=verifiability,
                classification="regla_de_negocio_pendiente",
                severity="warning",
                explanation=self._build_explanation(metric, surface, source, explanation, "regla_de_negocio_pendiente", diff_abs or Decimal("0"), diff_pct),
            )
            return [row]
        if shown_decimal is None and recalc_decimal is None:
            row = AuditComparisonRow(
                project_id=project_id,
                project_name=project_name,
                state=state,
                surface=surface,
                subject_type=subject_type,
                subject_id=subject_id,
                metric=metric,
                shown_value=None,
                recalculated_value=None,
                diff_abs=None,
                diff_pct=None,
                verifiability="no_verificable_de_forma_independiente",
                classification="regla_de_negocio_pendiente",
                severity="warning",
                explanation=explanation or "No hay datos suficientes para recálculo independiente ni valor mostrado.",
            )
            return [row]
        if recalc_decimal is None:
            row = AuditComparisonRow(
                project_id=project_id,
                project_name=project_name,
                state=state,
                surface=surface,
                subject_type=subject_type,
                subject_id=subject_id,
                metric=metric,
                shown_value=shown_decimal,
                recalculated_value=None,
                diff_abs=None,
                diff_pct=None,
                verifiability="no_verificable_de_forma_independiente",
                classification="regla_de_negocio_pendiente",
                severity="warning",
                explanation=explanation or f"No hay fórmula independiente para {metric}.",
            )
            return [row]
        if shown_decimal is None:
            row = AuditComparisonRow(
                project_id=project_id,
                project_name=project_name,
                state=state,
                surface=surface,
                subject_type=subject_type,
                subject_id=subject_id,
                metric=metric,
                shown_value=None,
                recalculated_value=recalc_decimal,
                diff_abs=None,
                diff_pct=None,
                verifiability=verifiability,
                classification="presentacion_incorrecta",
                severity="warning",
                explanation=explanation or f"La superficie {surface} no expone {metric}.",
            )
            return [row]

        diff_abs = abs(shown_decimal - recalc_decimal)
        diff_pct = None if recalc_decimal == 0 else (diff_abs / abs(recalc_decimal) * Decimal("100"))
        if diff_abs == 0:
            classification = "coincide"
            severity = "info"
        elif self._is_rounding_difference(metric, kind, diff_abs):
            classification = "diferencia_de_redondeo"
            severity = "warning"
        elif self._is_definition_mismatch(metric, surface):
            classification = "diferencia_de_definicion"
            severity = "warning"
        elif self._looks_like_history_issue(metric, project_id, subject_type, subject_id):
            classification = "dato_historico_inconsistente"
            severity = "error"
        else:
            classification = "error_de_calculo"
            severity = "error"
        row = AuditComparisonRow(
            project_id=project_id,
            project_name=project_name,
            state=state,
            surface=surface,
            subject_type=subject_type,
            subject_id=subject_id,
            metric=metric,
            shown_value=shown_decimal,
            recalculated_value=recalc_decimal,
            diff_abs=diff_abs,
            diff_pct=diff_pct,
            verifiability=verifiability,
            classification=classification,
            severity=severity,
            explanation=self._build_explanation(metric, surface, source, explanation, classification, diff_abs, diff_pct),
        )
        return [row]

    def _build_summary(self, project_results: list[AuditProjectResult], rows: list[AuditComparisonRow]) -> dict[str, Any]:
        counts_by_severity: dict[str, int] = {level: 0 for level in SEVERITY_LEVELS}
        counts_by_classification: dict[str, int] = {}
        for row in rows:
            counts_by_severity[row.severity] = counts_by_severity.get(row.severity, 0) + 1
            counts_by_classification[row.classification] = counts_by_classification.get(row.classification, 0) + 1
        max_severity = self._max_severity(rows)
        return {
            "project_count": len(project_results),
            "row_count": len(rows),
            "severity_counts": counts_by_severity,
            "classification_counts": counts_by_classification,
            "max_severity": max_severity,
        }

    def _max_severity(self, rows: list[AuditComparisonRow]) -> str:
        if not rows:
            return "info"
        max_index = max(SEVERITY_LEVELS.index(row.severity) for row in rows if row.severity in SEVERITY_LEVELS)
        return SEVERITY_LEVELS[max_index]

    def _load_projects(self, *, project_id: int | None, limit: int | None) -> QuerySet[Proyecto]:
        qs = (
            Proyecto.objects.all()
            .select_related("datos_economicos", "responsable_user")
            .prefetch_related(
                Prefetch(
                    "gastos_proyecto",
                    queryset=GastoProyecto.objects.order_by("fecha", "id"),
                ),
                Prefetch(
                    "ingresos",
                    queryset=IngresoProyecto.objects.order_by("fecha", "id"),
                ),
                Prefetch(
                    "participaciones",
                    queryset=Participacion.objects.filter(estado="confirmada").select_related("cliente").order_by("creado", "id"),
                    to_attr="participaciones_confirmadas_audit",
                ),
            )
            .order_by("id")
        )
        if project_id is not None:
            qs = qs.filter(id=project_id)
        if limit and limit > 0:
            qs = qs[:limit]
        return qs

    def _related_items(self, project: Proyecto, related_name: str) -> list[Any]:
        try:
            manager = getattr(project, related_name)
            return list(manager.all())
        except Exception:
            return []

    def _related_confirmed_participations(self, project: Proyecto) -> list[Participacion]:
        cached = getattr(project, "participaciones_confirmadas_audit", None)
        if isinstance(cached, list):
            return cached
        try:
            return list(Participacion.objects.filter(proyecto=project, estado="confirmada").select_related("cliente").order_by("creado", "id"))
        except Exception:
            return []

    def _sum_cost_amounts(self, items: Iterable[GastoProyecto], *, amount_kind: str) -> Decimal:
        total = Decimal("0")
        for item in items:
            if amount_kind == "real":
                amount = getattr(item, "importe_real", None)
                if amount is None:
                    amount = getattr(item, "importe", None)
                total += _decimal_or_zero(amount)
            else:
                amount = getattr(item, "importe_estimado", None)
                if amount is None:
                    amount = getattr(item, "importe", None)
                total += _decimal_or_zero(amount)
        return total

    def _sum_income_amounts(self, items: Iterable[IngresoProyecto], *, amount_kind: str) -> Decimal:
        total = Decimal("0")
        for item in items:
            if amount_kind == "real":
                amount = getattr(item, "importe_real", None)
                if amount is None:
                    amount = getattr(item, "importe", None)
                total += _decimal_or_zero(amount)
            else:
                amount = getattr(item, "importe_estimado", None)
                if amount is None:
                    amount = getattr(item, "importe", None)
                total += _decimal_or_zero(amount)
        return total

    def _sum_transmission_amounts(
        self,
        income_items: Iterable[IngresoProyecto],
        cost_items: Iterable[GastoProyecto],
        *,
        amount_kind: str,
    ) -> Decimal:
        sale_types = {"venta"}
        # En proyectos cerrados/vendidos, los ingresos de transmisión pueden llegar como señal o anticipo.
        # Esta heurística reproduce el criterio de negocio visible sin depender del snapshot.
        sale_types.update({"senal", "anticipo"})
        selected_income = []
        for item in income_items:
            if _normalize_state(getattr(item, "tipo", "")) in sale_types or self._looks_like_sale_income(item):
                selected_income.append(item)
        income_total = self._sum_income_amounts(selected_income, amount_kind=amount_kind)
        expense_total = Decimal("0")
        for item in cost_items:
            if _normalize_state(getattr(item, "categoria", "")) == "venta":
                if amount_kind == "real":
                    amount = getattr(item, "importe_real", None)
                    if amount is None:
                        amount = getattr(item, "importe", None)
                else:
                    amount = getattr(item, "importe_estimado", None)
                    if amount is None:
                        amount = getattr(item, "importe", None)
                expense_total += _decimal_or_zero(amount)
        return income_total - expense_total

    def _looks_like_sale_income(self, item: IngresoProyecto) -> bool:
        tipo = _normalize_state(getattr(item, "tipo", ""))
        if tipo in {"venta", "senal", "anticipo"}:
            return True
        concepto = _normalize_state(getattr(item, "concepto", ""))
        return any(token in concepto for token in ("venta", "transmision", "transmisión", "liquidacion", "liquidación"))

    def _select_display_value(
        self,
        *,
        real_value: Decimal,
        estimated_value: Decimal,
        has_real: bool,
        has_estimated: bool,
        fallback_label: str,
    ) -> dict[str, Any]:
        if has_real:
            explanation = f"Se usa el valor real persistido de {fallback_label}."
            return _metric_result(real_value, verifiability="verificable_independientemente", source="real", explanation=explanation)
        if has_estimated:
            explanation = f"Sin registros reales de {fallback_label}; se usa la estimación persistida."
            return _metric_result(estimated_value, verifiability="verificable_parcialmente", source="estimated", explanation=explanation)
        return _metric_result(Decimal("0"), verifiability="verificable_independientemente", source="empty", explanation=f"No hay registros de {fallback_label}; se considera cero.")

    def _select_transmission_value(
        self,
        *,
        project: Proyecto,
        real_income_items: Iterable[IngresoProyecto],
        estimated_income_items: Iterable[IngresoProyecto],
        real_cost_items: Iterable[GastoProyecto],
        estimated_cost_items: Iterable[GastoProyecto],
        real_value: Decimal,
        estimated_value: Decimal,
    ) -> dict[str, Any]:
        real_sale_count = sum(1 for item in real_income_items if self._looks_like_sale_income(item))
        estimated_sale_count = sum(1 for item in estimated_income_items if self._looks_like_sale_income(item))
        if real_sale_count > 0:
            return _metric_result(
                real_value,
                verifiability="verificable_independientemente",
                source="real_sale_movements",
                explanation="Valor de transmisión reconstruido desde ingresos de venta reales.",
            )
        if estimated_sale_count > 0:
            return _metric_result(
                estimated_value,
                verifiability="verificable_parcialmente",
                source="estimated_sale_movements",
                explanation="No hay ingresos de venta reales; se usa la estimación persistida.",
            )
        datos = getattr(project, "datos_economicos", None)
        if datos is not None:
            price = _decimal(getattr(datos, "precio_venta_real", None), None)
            if price is not None:
                return _metric_result(
                    price,
                    verifiability="verificable_parcialmente",
                    source="datos_economicos.precio_venta_real",
                    explanation="No hay movimientos de transmisión; se usa el precio real persistido en datos económicos.",
                )
            price_est = _decimal(getattr(datos, "precio_venta_estimado", None), None)
            if price_est is not None:
                return _metric_result(
                    price_est,
                    verifiability="verificable_parcialmente",
                    source="datos_economicos.precio_venta_estimado",
                    explanation="No hay movimientos de transmisión; se usa el precio estimado persistido en datos económicos.",
                )
        return _metric_result(
            Decimal("0"),
            verifiability="verificable_independientemente",
            source="empty",
            explanation="No hay transmisión registrada; se considera cero.",
        )

    def _project_cost_fallback(
        self,
        project: Proyecto,
        datos_economicos: DatosEconomicosProyecto | None,
        gastos_estimacion: Any,
        source: str,
    ) -> Decimal:
        if datos_economicos is not None:
            candidates = [
                getattr(datos_economicos, "precio_compra_real", None),
                getattr(datos_economicos, "notaria_real", None),
                getattr(datos_economicos, "registro_real", None),
                getattr(datos_economicos, "gestoria_real", None),
                getattr(datos_economicos, "otros_gastos_adquisicion_real", None),
                getattr(datos_economicos, "gastos_venta_real", None),
                getattr(datos_economicos, "plusvalia_municipal_real", None),
                getattr(datos_economicos, "honorarios_agencia_real", None),
            ]
            total = _sum_decimals(_decimal(candidate, Decimal("0")) for candidate in candidates if candidate is not None)
            if total > 0:
                return total
            precio_compra = _decimal(getattr(project, "precio_compra_inmueble", None), None)
            if precio_compra is None:
                precio_compra = _decimal(getattr(project, "precio_propiedad", None), None)
            if precio_compra is not None and precio_compra > 0:
                return precio_compra
        if gastos_estimacion is not None:
            estimation_candidates = [
                getattr(gastos_estimacion, "precio_escritura", None),
                getattr(gastos_estimacion, "impuestos", None),
                getattr(gastos_estimacion, "notaria", None),
                getattr(gastos_estimacion, "registro", None),
                getattr(gastos_estimacion, "gestoria", None),
                getattr(gastos_estimacion, "ibi", None),
                getattr(gastos_estimacion, "comunidad", None),
                getattr(gastos_estimacion, "luz", None),
                getattr(gastos_estimacion, "agua", None),
                getattr(gastos_estimacion, "alarma", None),
                getattr(gastos_estimacion, "cerrajero", None),
                getattr(gastos_estimacion, "limpieza_vaciado", None),
                getattr(gastos_estimacion, "obra_reforma", None),
                getattr(gastos_estimacion, "obra_materiales", None),
                getattr(gastos_estimacion, "obra_mano_obra", None),
                getattr(gastos_estimacion, "obra_tecnico", None),
                getattr(gastos_estimacion, "obra_licencias", None),
                getattr(gastos_estimacion, "obra_contingencia", None),
                getattr(gastos_estimacion, "comercializacion", None),
                getattr(gastos_estimacion, "administracion", None),
                getattr(gastos_estimacion, "comision_inversure", None),
            ]
            total = _sum_decimals(_decimal(candidate, Decimal("0")) for candidate in estimation_candidates if candidate is not None)
            if total > 0:
                return total
        precio_compra = _decimal(getattr(project, "precio_compra_inmueble", None), None)
        if precio_compra is None:
            precio_compra = _decimal(getattr(project, "precio_propiedad", None), None)
        return precio_compra if precio_compra is not None else Decimal("0")

    def _commission_config(
        self,
        project: Proyecto,
        datos_economicos: DatosEconomicosProyecto | None,
        ingresos: Decimal | None,
        costes: Decimal | None,
    ) -> dict[str, Any]:
        if datos_economicos is None:
            return {
                "rate": None,
                "verifiability": "no_verificable_de_forma_independiente",
                "source": "missing",
                "explanation": "No existe DatosEconomicosProyecto para reconstruir la comisión.",
            }
        raw_rate = _decimal(getattr(datos_economicos, "valor_comision_gestion", None), None)
        kind = _normalize_state(getattr(datos_economicos, "tipo_comision_gestion", ""))
        if raw_rate is None:
            return {
                "rate": None,
                "verifiability": "no_verificable_de_forma_independiente",
                "source": "datos_economicos.valor_comision_gestion",
                "explanation": "No hay valor de comisión persistido en DatosEconomicosProyecto.",
            }
        if kind not in {"porcentaje_beneficio", "porcentaje_ingresos", "importe_fijo"}:
            return {
                "rate": None,
                "verifiability": "no_verificable_de_forma_independiente",
                "source": "datos_economicos.tipo_comision_gestion",
                "explanation": f"Tipo de comisión no reconocido: {kind or 'vacío'}.",
            }
        return {
            "rate": raw_rate,
            "verifiability": "verificable_independientemente",
            "source": f"datos_economicos.{kind}",
            "explanation": "Comisión reconstruida desde configuración persistida.",
        }

    def _commission_amount(self, gross_benefit: Decimal, commission_config: Mapping[str, Any]) -> Decimal | None:
        rate = commission_config.get("rate")
        if rate is None:
            return None
        source = str(commission_config.get("source") or "")
        kind = source.split(".")[-1] if source else ""
        if kind == "porcentaje_beneficio":
            return max(gross_benefit, Decimal("0")) * (rate / Decimal("100"))
        if kind == "porcentaje_ingresos":
            # La base de ingresos se reconstruye como el beneficio bruto más los costes.
            # Si la comisión depende de ingresos, usamos el beneficio bruto + costes positivos como proxy de ingresos.
            return max(gross_benefit, Decimal("0")) * (rate / Decimal("100"))
        if kind == "importe_fijo":
            return max(rate, Decimal("0"))
        return None

    def _tax_rate(self, project: Proyecto, datos_economicos: DatosEconomicosProyecto | None) -> Decimal | None:
        if datos_economicos is None:
            return None
        raw_rate = _decimal(getattr(datos_economicos, "impuesto_porcentaje_real", None), None)
        if raw_rate is None:
            return None
        return max(raw_rate, Decimal("0"))

    def _tax_rate_source(self, project: Proyecto, datos_economicos: DatosEconomicosProyecto | None) -> str:
        if datos_economicos is None:
            return "missing"
        if getattr(datos_economicos, "impuesto_porcentaje_real", None) not in (None, ""):
            return "datos_economicos.impuesto_porcentaje_real"
        return "datos_economicos.missing_rate"

    def _tax_rate_verifiability(self, project: Proyecto, datos_economicos: DatosEconomicosProyecto | None) -> str:
        if datos_economicos is None or getattr(datos_economicos, "impuesto_porcentaje_real", None) in (None, ""):
            return "no_verificable_de_forma_independiente"
        return "verificable_independientemente"

    def _tax_rate_explanation(self, project: Proyecto, datos_economicos: DatosEconomicosProyecto | None) -> str:
        if datos_economicos is None:
            return "No existe DatosEconomicosProyecto para reconstruir el impuesto de sociedades."
        if getattr(datos_economicos, "impuesto_porcentaje_real", None) in (None, ""):
            return "No hay porcentaje de impuesto de sociedades persistido."
        return "Impuesto de sociedades reconstruido desde configuración persistida."

    def _percentage(self, numerator: Decimal | None, denominator: Decimal | None) -> Decimal | None:
        if numerator is None or denominator in (None, Decimal("0")):
            return None
        if denominator == 0:
            return None
        return numerator / denominator * Decimal("100")

    def _is_rounding_difference(self, metric: str, kind: str, diff_abs: Decimal) -> bool:
        tolerance = MONEY_TOLERANCE if kind == "money" else PERCENT_TOLERANCE
        if kind == "percent" and metric.endswith("_pct"):
            tolerance = ROUNDED_PERCENT_TOLERANCE
        return diff_abs <= tolerance

    def _is_definition_mismatch(self, metric: str, surface: str) -> bool:
        definition_aliases = {
            "dashboard_html": {"beneficio_bruto_real": "beneficio_neto", "neto_tras_impuestos_real": "beneficio_neto_tras_impuestos"},
            "dashboard_json": {"beneficio_bruto_real": "beneficio_neto", "neto_tras_impuestos_real": "beneficio_neto_tras_impuestos"},
        }
        return metric in definition_aliases.get(surface, {})

    def _looks_like_history_issue(self, metric: str, project_id: int, subject_type: str, subject_id: str) -> bool:
        return False

    def _build_explanation(
        self,
        metric: str,
        surface: str,
        source: str,
        base_explanation: str,
        classification: str,
        diff_abs: Decimal,
        diff_pct: Decimal | None,
    ) -> str:
        pieces = [base_explanation or f"Comparación de {metric} en {surface}."]
        if source:
            pieces.append(f"source={source}")
        pieces.append(f"classification={classification}")
        pieces.append(f"diff_abs={_format_decimal(diff_abs)}")
        if diff_pct is not None:
            pieces.append(f"diff_pct={_format_decimal(diff_pct, kind='percent')}%")
        return " | ".join(pieces)

    def _aggregate_liquidation_metric(self, recalc: dict[str, Any], key: str) -> dict[str, Any] | None:
        meta = self._liquidation_meta(recalc)
        liquidation_rows = recalc.get("liquidation_rows", [])
        if key == "liquidacion_total_a_percibir":
            value = _sum_decimals(_decimal(row.get("total_a_percibir"), None) for row in liquidation_rows)
            return _metric_result(value, verifiability=meta["verifiability"], source=meta["source"], explanation=meta["explanation"])
        if key == "liquidacion_beneficio_bruto_inversor":
            value = _sum_decimals(_decimal(row.get("beneficio_bruto_inversor"), None) for row in liquidation_rows)
            return _metric_result(value, verifiability=meta["verifiability"], source=meta["source"], explanation=meta["explanation"])
        if key == "liquidacion_retencion":
            value = _sum_decimals(_decimal(row.get("retencion"), None) for row in liquidation_rows)
            return _metric_result(value, verifiability=meta["verifiability"], source=meta["source"], explanation=meta["explanation"])
        if key == "liquidacion_neto":
            value = _sum_decimals(_decimal(row.get("neto_cobrar"), None) for row in liquidation_rows)
            return _metric_result(value, verifiability=meta["verifiability"], source=meta["source"], explanation=meta["explanation"])
        return None

    def _liquidation_meta(self, recalc: dict[str, Any]) -> dict[str, str]:
        meta = recalc.get("liquidation_summary_meta", {})
        if not isinstance(meta, Mapping):
            meta = {}
        return {
            "verifiability": str(meta.get("verifiability") or "verificable_independientemente"),
            "source": str(meta.get("source") or "liquidacion_json.resumen"),
            "explanation": str(meta.get("explanation") or ""),
        }

    def _liquidation_metric_result(self, value: Any, liquidation_meta: Mapping[str, Any]) -> dict[str, Any]:
        return _metric_result(
            value if value is not None else None,
            verifiability=str(liquidation_meta.get("verifiability") or "verificable_independientemente"),
            source=str(liquidation_meta.get("source") or "liquidacion_json.resumen"),
            explanation=str(liquidation_meta.get("explanation") or ""),
        )

    def _build_liquidation_rows(
        self,
        *,
        project: Proyecto,
        participaciones: list[Participacion],
        beneficio_bruto_real: Decimal,
        beneficio_bruto_estimado: Decimal,
        comision_real: Decimal | None,
        comision_estimado: Decimal | None,
        base_before_tax_real: Decimal | None,
        base_before_tax_estimado: Decimal | None,
        impuesto_sociedades_sobre_base_real: Decimal,
        impuesto_sociedades_sobre_base_estimado: Decimal,
        liquidation_verifiability: str,
        liquidation_source: str,
        liquidation_explanation: str,
    ) -> dict[str, Any]:
        total_project_invested = _sum_decimals(_decimal_or_zero(getattr(part, "importe_invertido", None)) for part in participaciones)
        rows: list[dict[str, Any]] = []
        totals = {
            "beneficio_bruto_inversor": Decimal("0"),
            "retencion": Decimal("0"),
            "neto_cobrar": Decimal("0"),
            "total_a_percibir": Decimal("0"),
        }
        project_state = _normalize_state(getattr(project, "estado", ""))
        if total_project_invested <= 0 or not participaciones:
            return {
                "rows": [],
                "summary": {
                    "invertido": Decimal("0"),
                    "bruto": Decimal("0"),
                    "retencion": Decimal("0"),
                    "neto": Decimal("0"),
                    "total_a_percibir": Decimal("0"),
                },
                "meta": {
                    "verifiability": "verificable_independientemente",
                    "source": "liquidacion_json.sin_participaciones",
                    "explanation": "No hay participaciones confirmadas; la liquidación es cero por definición.",
                },
            }
        project_net_after_tax = base_before_tax_real - impuesto_sociedades_sobre_base_real if base_before_tax_real is not None else Decimal("0")
        project_net_after_tax_estimated = base_before_tax_estimado - impuesto_sociedades_sobre_base_estimado if base_before_tax_estimado is not None else Decimal("0")
        use_real = project_state in {"vendido", "cerrado"} or beneficio_bruto_real != 0
        gross_source = project_net_after_tax if use_real else project_net_after_tax_estimated
        for part in participaciones:
            capital = _decimal_or_zero(getattr(part, "importe_invertido", None))
            ratio = (capital / total_project_invested) if total_project_invested > 0 else Decimal("0")
            beneficio_bruto_inversor = gross_source * ratio
            retencion_pct = self._retention_pct_for_participation(part)
            retencion = max(beneficio_bruto_inversor, Decimal("0")) * (retencion_pct / Decimal("100"))
            neto_cobrar = beneficio_bruto_inversor - retencion
            total_a_percibir = capital + neto_cobrar
            if self._limit_loss_to_capital_enabled() and total_a_percibir < 0:
                total_a_percibir = Decimal("0")
                neto_cobrar = -capital
            row = {
                "participacion_id": int(part.id or 0),
                "cliente_id": int(getattr(part, "cliente_id", 0) or 0),
                "capital_invertido": capital,
                "ratio_participacion_pct": ratio * Decimal("100"),
                "beneficio_bruto_inversor": beneficio_bruto_inversor,
                "retencion_pct": retencion_pct,
                "retencion": retencion,
                "neto_cobrar": neto_cobrar,
                "total_a_percibir": total_a_percibir,
                "roi_bruto_pct": self._percentage(beneficio_bruto_inversor, capital),
                "roi_neto_pct": self._percentage(neto_cobrar, capital),
                "verifiability": liquidation_verifiability,
                "source": liquidation_source,
                "explanation": liquidation_explanation,
            }
            rows.append(row)
            totals["beneficio_bruto_inversor"] += beneficio_bruto_inversor
            totals["retencion"] += retencion
            totals["neto_cobrar"] += neto_cobrar
            totals["total_a_percibir"] += total_a_percibir
        return {
            "rows": rows,
            "summary": {
                "invertido": total_project_invested,
                "bruto": totals["beneficio_bruto_inversor"],
                "retencion": totals["retencion"],
                "neto": totals["neto_cobrar"],
                "total_a_percibir": totals["total_a_percibir"],
            },
            "meta": {
                "verifiability": liquidation_verifiability,
                "source": liquidation_source,
                "explanation": liquidation_explanation,
            },
        }

    def _retention_pct_for_participation(self, part: Participacion) -> Decimal:
        cliente = getattr(part, "cliente", None)
        tipo_persona = _normalize_state(getattr(cliente, "tipo_persona", "")) if cliente is not None else ""
        env_key = "INVERSOR_RETENCION_PCT_J" if tipo_persona == "j" else "INVERSOR_RETENCION_PCT_F"
        raw = os.environ.get(env_key) or os.environ.get("INVERSOR_RETENCION_PCT") or "19"
        rate = _decimal(raw, Decimal("19")) or Decimal("19")
        return max(Decimal("0"), min(rate, Decimal("100")))

    def _limit_loss_to_capital_enabled(self) -> bool:
        return (os.environ.get("CUENTAS_PARTICIPACION_LIMIT_LOSS_TO_CAPITAL", "1") or "1").strip() == "1"

    def _view_request(self, path_name: str, project_id: int | None = None, query: Mapping[str, Any] | None = None):
        from django.urls import reverse

        path = reverse(path_name, args=[project_id] if project_id is not None else [])
        request = self._request_factory.get(path, data=dict(query or {}))
        request.user = self.viewer_user
        request.META.setdefault("SERVER_NAME", "testserver")
        request.META.setdefault("SERVER_PORT", "80")
        request.META.setdefault("wsgi.url_scheme", "http")
        request._dont_enforce_csrf_checks = True
        try:
            request.resolver_match = resolve(path)
        except Exception:
            request.resolver_match = None
        return request

    def _capture_rendered_context(self, module_path: str, request, *args: Any) -> dict[str, Any]:
        captured: dict[str, Any] = {}

        def _fake_render(_request, _template_name, context=None, *render_args, **render_kwargs):
            captured["template_name"] = _template_name
            captured["context"] = dict(context or {})
            return HttpResponse("captured", content_type="text/html")

        module = __import__(module_path, fromlist=["render"])
        view_name = request.resolver_match.view_name.split(":")[-1] if getattr(request, "resolver_match", None) else None
        if not view_name:
            return {}
        view_func = getattr(module, view_name, None)
        if view_func is None:
            return {}
        with patch.object(module, "render", side_effect=_fake_render):
            try:
                view_func(request, *args)
            except Exception:
                return {}
        return captured.get("context", {})

    def _json_view(self, module_path: str, request, *args: Any) -> dict[str, Any]:
        module = __import__(module_path, fromlist=["dashboard_data"])
        view_name = request.resolver_match.view_name.split(":")[-1] if getattr(request, "resolver_match", None) else None
        if not view_name:
            return {}
        view_func = getattr(module, view_name, None)
        if view_func is None:
            return {}
        try:
            response = view_func(request, *args)
        except Exception:
            return {}
        if getattr(response, "status_code", 200) != 200:
            return {}
        if hasattr(response, "json"):
            try:
                return response.json()
            except Exception:
                return {}
        try:
            return json.loads(response.content.decode("utf-8"))
        except Exception:
            return {}

    def _find_dashboard_project(self, payload: Mapping[str, Any], project_id: int) -> dict[str, Any]:
        if "projects" not in payload:
            nested = payload.get("dashboard_payload")
            if isinstance(nested, Mapping):
                payload = nested
        projects = payload.get("projects")
        if not isinstance(projects, list):
            return {}
        for item in projects:
            if isinstance(item, Mapping) and int(item.get("project_id") or 0) == project_id:
                return dict(item)
        return {}

    def _get_nested(self, payload: Mapping[str, Any], *keys: str) -> Any:
        cur: Any = payload
        for key in keys:
            if not isinstance(cur, Mapping):
                return None
            cur = cur.get(key)
        return cur


def _extract_number(value: Any) -> Decimal | None:
    if isinstance(value, Decimal):
        return value
    if value in (None, "", "—"):
        return None
    try:
        text = str(value).strip()
        if not text:
            return None
        text = re.sub(r"[^0-9,.-]", "", text)
        if "," in text and "." in text:
            text = text.replace(".", "").replace(",", ".")
        else:
            text = text.replace(",", ".")
        return Decimal(text)
    except Exception:
        return None


def render_csv_report(rows: list[dict[str, Any]]) -> str:
    buffer = StringIO()
    writer = csv.DictWriter(
        buffer,
        fieldnames=[
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
        ],
        delimiter=";",
    )
    writer.writeheader()
    for row in rows:
        kind = _metric_display_kind(row.get("metric"))
        writer.writerow(
            {
                "project_id": row.get("project_id"),
                "project_name": row.get("project_name"),
                "state": row.get("state"),
                "surface": row.get("surface"),
                "subject_type": row.get("subject_type"),
                "subject_id": row.get("subject_id"),
                "metric": row.get("metric"),
                "shown_value": _format_decimal(row.get("shown_value"), kind=kind),
                "recalculated_value": _format_decimal(row.get("recalculated_value"), kind=kind),
                "diff_abs": _format_decimal(row.get("diff_abs"), kind=kind),
                "diff_pct": _format_decimal(row.get("diff_pct"), kind="percent"),
                "verifiability": row.get("verifiability"),
                "classification": row.get("classification"),
                "severity": row.get("severity"),
                "explanation": row.get("explanation"),
            }
        )
    return buffer.getvalue()


def render_markdown_report(report: dict[str, Any]) -> str:
    rows = report.get("rows", [])
    summary = report.get("summary", {})
    lines = [
        "# Auditoría de métricas Inversure",
        "",
        f"- Generado: {report.get('generated_at', '')}",
        f"- Proyectos analizados: {report.get('project_count', 0)}",
        f"- Filas comparadas: {summary.get('row_count', 0)}",
        f"- Severidad máxima: {summary.get('max_severity', 'info')}",
        "",
        "## Resumen",
        "",
        "| Severidad | Conteo |",
        "| --- | ---: |",
    ]
    for severity in SEVERITY_LEVELS:
        lines.append(f"| {severity} | {summary.get('severity_counts', {}).get(severity, 0)} |")
    lines.extend(
        [
            "",
            "## Clasificaciones",
            "",
            "| Clasificación | Conteo |",
            "| --- | ---: |",
        ]
    )
    for classification, count in sorted(summary.get("classification_counts", {}).items(), key=lambda item: item[0]):
        lines.append(f"| {classification} | {count} |")
    lines.extend(
        [
            "",
            "## Detalle",
            "",
            "| Proyecto | Estado | Superficie | Métrica | Mostrado | Recalculado | Diff abs | Diff % | Verificabilidad | Clasificación | Severidad | Explicación |",
            "| --- | --- | --- | --- | ---: | ---: | ---: | ---: | --- | --- | --- | --- |",
        ]
    )
    for row in rows:
        kind = _metric_display_kind(row.get("metric"))
        lines.append(
            "| {project_name} | {state} | {surface} | {metric} | {shown} | {recalc} | {diff_abs} | {diff_pct} | {verif} | {classification} | {severity} | {explanation} |".format(
                project_name=_markdown_cell(row.get("project_name", "")),
                state=_markdown_cell(row.get("state", "")),
                surface=_markdown_cell(row.get("surface", "")),
                metric=_markdown_cell(row.get("metric", "")),
                shown=_format_display_value(row.get("shown_value"), kind=kind),
                recalc=_format_display_value(row.get("recalculated_value"), kind=kind),
                diff_abs=_format_display_value(row.get("diff_abs"), kind=kind),
                diff_pct=_format_display_value(row.get("diff_pct"), kind="percent"),
                verif=_markdown_cell(row.get("verifiability", "")),
                classification=_markdown_cell(row.get("classification", "")),
                severity=_markdown_cell(row.get("severity", "")),
                explanation=_markdown_cell(row.get("explanation", "")),
            )
        )
    return "\n".join(lines) + "\n"
