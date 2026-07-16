from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import date, datetime
from decimal import Decimal
from hashlib import sha256
from typing import Any, Mapping, cast

from django.db.models import Prefetch, Q, Sum
from django.db.models.functions import TruncMonth
from django.utils import timezone

from accounts.utils import (
    is_admin_user,
    is_comercial_user,
    is_direccion_user,
    is_marketing_user,
    is_moderators_user,
    resolve_permissions,
    use_custom_permissions,
)
from core.finance import calc_inversor_settlement, calc_operacion_economica
from core.models import (
    ChecklistItem,
    Cliente,
    FacturaGasto,
    GastoProyecto,
    IngresoProyecto,
    InversorPerfil,
    Participacion,
    Proyecto,
    SolicitudParticipacion,
    JustificanteIngreso,
)

TERMINAL_PROJECT_STATES = {"cerrado", "descartado"}
LEGACY_CLOSED_PROJECT_STATES = {"cerrado"}
ACTIVE_PROJECT_STATES = {"captacion", "comprado", "comercializacion", "reservado", "vendido"}
DATE_INPUT_FORMATS = ("%Y-%m-%d", "%d/%m/%Y", "%d-%m-%Y", "%Y/%m/%d")


def _core_views():
    from core import views as core_views

    return core_views


def _to_decimal(value: Any, default: Decimal = Decimal("0")) -> Decimal:
    if value is None or value == "":
        return default
    if isinstance(value, Decimal):
        return value
    try:
        return Decimal(str(value))
    except Exception:
        return default


def _to_float(value: Any, default: float = 0.0) -> float:
    if value is None or value == "":
        return default
    try:
        return float(value)
    except Exception:
        return default


def _month_floor(value: date | datetime | None) -> date | None:
    if isinstance(value, datetime):
        value = value.date()
    if not isinstance(value, date):
        return None
    return date(value.year, value.month, 1)


def _parse_date_value(value: Any) -> date | None:
    if isinstance(value, datetime):
        return value.date()
    if isinstance(value, date):
        return value
    if value in (None, ""):
        return None
    text = str(value).strip()
    if not text:
        return None
    for fmt in DATE_INPUT_FORMATS:
        try:
            return datetime.strptime(text, fmt).date()
        except ValueError:
            continue
    try:
        return date.fromisoformat(text)
    except ValueError:
        return None


def _month_sequence(start: date, end: date) -> list[date]:
    start = date(start.year, start.month, 1)
    end = date(end.year, end.month, 1)
    current = start
    months: list[date] = []
    while current <= end:
        months.append(current)
        if current.month == 12:
            current = date(current.year + 1, 1, 1)
        else:
            current = date(current.year, current.month + 1, 1)
    return months


def _month_label(value: date) -> str:
    return value.strftime("%Y-%m")


def _sum_monthly_rows(rows: list[dict[str, Any]]) -> dict[date, Decimal]:
    totals: dict[date, Decimal] = {}
    for row in rows:
        month = _month_floor(row.get("month"))
        if month is None:
            continue
        totals[month] = totals.get(month, Decimal("0")) + _to_decimal(row.get("total"))
    return totals


def _fmt_es_number(value: float, decimals: int = 2) -> str:
    text = f"{value:,.{decimals}f}"
    return text.replace(",", "X").replace(".", ",").replace("X", ".")


def _fmt_eur(value: float) -> str:
    return f"{_fmt_es_number(value, 2)} €"


def _fmt_pct(value: float) -> str:
    return f"{_fmt_es_number(value, 2)} %"


@dataclass(frozen=True, slots=True)
class FinancialDashboardFilters:
    """Normalized filters used by the financial dashboard service."""

    fecha_desde: date | None = None
    fecha_hasta: date | None = None
    proyecto_id: int | None = None
    estado: str | None = None

    @classmethod
    def from_mapping(cls, data: Mapping[str, Any] | None) -> FinancialDashboardFilters:
        if not data:
            return cls()

        raw_fecha_desde = data.get("fecha_desde")
        raw_fecha_hasta = data.get("fecha_hasta")
        raw_proyecto = data.get("proyecto_id") or data.get("proyecto")
        raw_estado = str(data.get("estado") or data.get("estado_proyecto") or "").strip().lower()

        fecha_desde = _parse_date_value(raw_fecha_desde)
        fecha_hasta = _parse_date_value(raw_fecha_hasta)
        if fecha_desde and fecha_hasta and fecha_desde > fecha_hasta:
            fecha_desde, fecha_hasta = fecha_hasta, fecha_desde

        proyecto_id: int | None
        try:
            proyecto_id = int(str(raw_proyecto)) if raw_proyecto not in (None, "") else None
        except (TypeError, ValueError):
            proyecto_id = None

        allowed_states = {choice[0] for choice in Proyecto.ESTADO_CHOICES}
        estado = raw_estado if raw_estado in allowed_states else None

        return cls(
            fecha_desde=fecha_desde,
            fecha_hasta=fecha_hasta,
            proyecto_id=proyecto_id,
            estado=estado,
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "fecha_desde": self.fecha_desde.isoformat() if self.fecha_desde else None,
            "fecha_hasta": self.fecha_hasta.isoformat() if self.fecha_hasta else None,
            "proyecto_id": self.proyecto_id,
            "estado": self.estado,
        }

    @property
    def is_empty(self) -> bool:
        return not any((self.fecha_desde, self.fecha_hasta, self.proyecto_id, self.estado))


class FinancialDashboardService:
    """Builds structured portfolio data for the executive financial dashboard."""

    def __init__(self, user, filters: FinancialDashboardFilters | None = None) -> None:
        self.user = user
        self.filters = filters or FinancialDashboardFilters()
        self.permissions = resolve_permissions(user)

    def build(self) -> dict[str, Any]:
        """Return a structured, template-agnostic dashboard payload."""

        projects = list(self._load_projects())
        project_metrics = self._build_project_metrics(projects)
        summary = self._build_summary(projects, project_metrics)
        period = self._build_period_summary(projects)
        charts = self._build_charts(project_metrics)
        series = self._build_series(projects)
        rankings = self._build_rankings(project_metrics)
        alerts = self._build_alerts(projects, project_metrics)
        active_project_count = sum(1 for project in projects if (project.estado or "") in ACTIVE_PROJECT_STATES)
        finalized_project_count = sum(1 for project in projects if (project.estado or "") in TERMINAL_PROJECT_STATES)

        return {
            "meta": self._build_meta(projects),
            "filters": self.filters.to_dict(),
            "permissions": dict(self.permissions),
            "scope": {
                "project_count": len(projects),
                "active_project_count": active_project_count,
                "finalized_project_count": finalized_project_count,
                "has_filters": not self.filters.is_empty,
            },
            "kpis": summary,
            "period": period,
            "series": series,
            "charts": charts,
            "rankings": rankings,
            "alerts": alerts,
            "projects": project_metrics,
        }

    def _build_meta(self, projects: list[Proyecto]) -> dict[str, Any]:
        project_signature = sorted(
            ((project.id or 0, project.estado or "") for project in projects),
            key=lambda item: item[0],
        )
        scope_signature = {
            "role": self._role_scope(),
            "filters": self.filters.to_dict(),
            "project_signature": project_signature,
            "version": 1,
        }
        cache_key = sha256(json.dumps(scope_signature, sort_keys=True, default=str).encode("utf-8")).hexdigest()
        return {
            "generated_at": timezone.now().isoformat(),
            "cache_key": f"financial-dashboard:{cache_key}",
            "cache_ready": True,
            "scope": self._role_scope(),
        }

    def _role_scope(self) -> str:
        if is_admin_user(self.user):
            return "administracion"
        if is_direccion_user(self.user):
            return "direccion"
        if is_comercial_user(self.user):
            return "comercial"
        if is_marketing_user(self.user):
            return "marketing"
        if is_moderators_user(self.user):
            return "moderators"
        if use_custom_permissions(self.user):
            return "custom"
        return "anonymous"

    def _load_projects(self):
        project_qs = (
            Proyecto.objects.all()
            .select_related("responsable_user", "origen_estudio", "origen_snapshot", "datos_economicos")
            .prefetch_related(
                Prefetch(
                    "gastos_proyecto",
                    queryset=GastoProyecto.objects.select_related("proyecto").order_by("fecha", "id"),
                ),
                Prefetch(
                    "ingresos",
                    queryset=IngresoProyecto.objects.select_related("proyecto").order_by("fecha", "id"),
                ),
                Prefetch(
                    "participaciones",
                    queryset=Participacion.objects.filter(estado="confirmada")
                    .select_related("cliente")
                    .order_by("creado", "id"),
                    to_attr="participaciones_confirmadas",
                ),
                Prefetch(
                    "checklist_items",
                    queryset=ChecklistItem.objects.select_related("proyecto", "responsable_user").order_by(
                        "fase",
                        "fecha_objetivo",
                        "id",
                    ),
                    to_attr="checklist_items_dashboard",
                ),
            )
        )
        if self.filters.proyecto_id is not None:
            project_qs = project_qs.filter(id=self.filters.proyecto_id)
        if self.filters.estado:
            project_qs = project_qs.filter(estado=self.filters.estado)
        return project_qs

    def _build_project_metrics(self, projects: list[Proyecto]) -> list[dict[str, Any]]:
        core_views = _core_views()
        metrics: list[dict[str, Any]] = []
        for project in projects:
            snapshot = core_views._get_snapshot_comunicacion(project)
            resultado = core_views._resultado_desde_memoria(project, snapshot)
            beneficio_memoria = core_views._beneficio_estimado_real_memoria(project)
            capital_objetivo = _to_decimal(core_views._capital_objetivo_desde_memoria(project, snapshot))
            participaciones_confirmadas = list(getattr(project, "participaciones_confirmadas", []))
            capital_captado = sum((_to_decimal(part.importe_invertido) for part in participaciones_confirmadas), Decimal("0"))
            capital_pendiente = max(capital_objetivo - capital_captado, Decimal("0"))

            operacion = self._build_operacion_summary(project, snapshot, resultado)
            settlement = self._build_investment_return_summary(
                project=project,
                snapshot=snapshot,
                operation=operacion,
                confirmed_participations=participaciones_confirmadas,
                capital_captado=capital_captado,
            )

            beneficio_neto = _to_float(resultado.get("beneficio_neto"))
            valor_adquisicion = _to_float(resultado.get("valor_adquisicion"))
            roi = _to_float(resultado.get("roi"))
            beneficio_estimado = _to_float(beneficio_memoria.get("beneficio_estimado"))
            beneficio_real = _to_float(beneficio_memoria.get("beneficio_real"))
            delta = beneficio_real - beneficio_estimado
            delta_pct = (delta / abs(beneficio_estimado) * 100.0) if beneficio_estimado else None

            metrics.append(
                {
                    "project_id": project.id,
                    "codigo_proyecto": project.codigo_proyecto,
                    "nombre": (project.nombre or f"Proyecto {project.id}").strip(),
                    "estado": project.estado or "",
                    "estado_label": project.get_estado_display() if hasattr(project, "get_estado_display") else (project.estado or ""),
                    "estado_operativo": getattr(getattr(project, "datos_economicos", None), "estado_operativo", "") or "",
                    "capital_objetivo": capital_objetivo,
                    "capital_captado": capital_captado,
                    "capital_pendiente": capital_pendiente,
                    "beneficio_estimado": beneficio_estimado,
                    "beneficio_real": beneficio_real,
                    "beneficio_neto": beneficio_neto,
                    "beneficio_bruto_operacion": _to_float(operacion["beneficio_bruto"]),
                    "beneficio_neto_operacion": _to_float(operacion["beneficio_neto_total"]),
                    "beneficio_inversure": _to_float(operacion["comision_eur"]),
                    "beneficio_neto_tras_impuestos": _to_float(resultado.get("beneficio_neto_tras_impuestos")),
                    "roi": roi,
                    "ratio_euro": _to_float(resultado.get("ratio_euro")),
                    "margen_neto": _to_float(resultado.get("margen_neto")),
                    "inversion_total": _to_float(resultado.get("inversion_total")),
                    "valor_adquisicion": valor_adquisicion,
                    "gastos_real_total": _to_float(resultado.get("gastos_real_total")),
                    "gastos_est_total": _to_float(resultado.get("gastos_est_total")),
                    "deviation": {
                        "estimado": beneficio_estimado,
                        "real": beneficio_real,
                        "delta": delta,
                        "delta_pct": delta_pct,
                    },
                    "investment_return": settlement,
                    "participaciones_confirmadas": len(participaciones_confirmadas),
                    "has_movimientos": bool(beneficio_memoria.get("has_movimientos")),
                    "base_memoria_real": bool(resultado.get("base_memoria_real")),
                }
            )
        return metrics

    def _build_operacion_summary(
        self,
        project: Proyecto,
        snapshot: dict[str, Any],
        resultado: dict[str, Any],
    ) -> dict[str, float]:
        extra = project.extra if isinstance(project.extra, dict) else {}
        override = extra.get("beneficio_operacion_override")
        override_dict = override if isinstance(override, dict) else {}
        commission_pct = self._commission_pct(snapshot)
        operation = calc_operacion_economica(
            beneficio_bruto=_to_float(resultado.get("beneficio_neto")),
            comision_pct=commission_pct,
            override_bruto=_to_float(override_dict.get("beneficio_bruto"), default=_to_float(resultado.get("beneficio_neto"))),
            override_comision_eur=_to_float(override_dict.get("comision_eur"), default=0.0) if override_dict.get("comision_eur") not in (None, "") else None,
            override_beneficio_neto_total=_to_float(override_dict.get("beneficio_neto_total"), default=0.0) if override_dict.get("beneficio_neto_total") not in (None, "") else None,
        )
        return {
            "beneficio_bruto": float(operation.beneficio_bruto),
            "comision_eur": float(operation.comision_eur),
            "beneficio_neto_total": float(operation.beneficio_neto_total),
            "comision_pct": commission_pct,
        }

    def _commission_pct(self, snapshot: dict[str, Any]) -> float:
        top_level = snapshot if isinstance(snapshot, dict) else {}
        inv_raw = top_level.get("inversor") if isinstance(top_level, dict) else None
        inv_section = inv_raw if isinstance(inv_raw, dict) else {}
        candidates = (
            inv_section.get("comision_inversure_pct"),
            inv_section.get("inversure_comision_pct"),
            inv_section.get("comision_pct"),
            top_level.get("comision_inversure_pct"),
            top_level.get("inversure_comision_pct"),
            top_level.get("comision_pct"),
        )
        for value in candidates:
            pct = _to_float(value, default=float("nan"))
            if pct == pct:
                return max(0.0, min(100.0, pct))
        return 0.0

    def _build_investment_return_summary(
        self,
        *,
        project: Proyecto,
        snapshot: dict[str, Any],
        operation: dict[str, float],
        confirmed_participations: list[Participacion],
        capital_captado: Decimal,
    ) -> dict[str, Any]:
        total_retorno = Decimal("0")
        total_beneficio = Decimal("0")
        roi_bruto_vals: list[float] = []
        roi_neto_vals: list[float] = []
        if capital_captado > 0 and confirmed_participations:
            operation_override = {
                "beneficio_bruto": operation["beneficio_bruto"],
                "comision_eur": operation["comision_eur"],
                "beneficio_neto_total": operation["beneficio_neto_total"],
            }
            for part in confirmed_participations:
                override_data = part.beneficio_override_data if isinstance(part.beneficio_override_data, dict) else {}
                inversor_override: dict[str, Any] = dict(override_data)
                if part.beneficio_neto_override is not None and "beneficio_inversor" not in inversor_override:
                    inversor_override["beneficio_inversor"] = float(part.beneficio_neto_override)
                settlement = calc_inversor_settlement(
                    capital_invertido=float(part.importe_invertido or 0),
                    total_proyecto_invertido=float(capital_captado or 0),
                    beneficio_bruto_operacion=operation["beneficio_bruto"],
                    comision_pct=operation["comision_pct"],
                    operacion_override=operation_override,
                    inversor_override=inversor_override,
                )
                total_retorno += _to_decimal(settlement.get("total_a_percibir"))
                total_beneficio += _to_decimal(settlement.get("neto_cobrar"))
                roi_bruto_vals.append(_to_float(settlement.get("roi_bruto_pct")))
                roi_neto_vals.append(_to_float(settlement.get("roi_neto_pct")))
        return {
            "capital_invertido": capital_captado,
            "beneficio_neto": total_beneficio,
            "retorno_total": total_retorno,
            "roi_bruto_medio": sum(roi_bruto_vals) / len(roi_bruto_vals) if roi_bruto_vals else 0.0,
            "roi_neto_medio": sum(roi_neto_vals) / len(roi_neto_vals) if roi_neto_vals else 0.0,
            "participaciones": len(confirmed_participations),
        }

    def _build_summary(self, projects: list[Proyecto], project_metrics: list[dict[str, Any]]) -> dict[str, Any]:
        project_ids = [project.id for project in projects if project.id is not None]
        active_project_ids = [project.id for project in projects if (project.estado or "") in ACTIVE_PROJECT_STATES and project.id is not None]

        capital_acumulado = (
            Participacion.objects.filter(estado="confirmada", proyecto_id__in=project_ids)
            .aggregate(total=Sum("importe_invertido"))
            .get("total")
            or Decimal("0")
        )
        capital_actual = (
            Participacion.objects.filter(estado="confirmada", proyecto_id__in=active_project_ids)
            .aggregate(total=Sum("importe_invertido"))
            .get("total")
            or Decimal("0")
        )
        inversores_con_cuota = (
            Cliente.objects.filter(
                participaciones__estado="confirmada",
                participaciones__proyecto_id__in=project_ids,
                cuota_abonada=True,
            )
            .distinct()
            .count()
        )
        inversores_activos = (
            Participacion.objects.filter(estado="confirmada", proyecto_id__in=active_project_ids)
            .values_list("cliente_id", flat=True)
            .distinct()
            .count()
        )

        confirmed_parts = list(
            Participacion.objects.filter(estado="confirmada", proyecto_id__in=project_ids)
            .select_related("cliente")
            .order_by("cliente_id", "creado", "id")
        )
        perfil_map = {
            perfil.cliente_id: perfil
            for perfil in InversorPerfil.objects.filter(cliente_id__in=[part.cliente_id for part in confirmed_parts]).select_related("cliente")
        }
        aportacion_por_cliente: dict[int, Decimal] = {}
        for part in confirmed_parts:
            if part.cliente_id in aportacion_por_cliente:
                continue
            perfil = perfil_map.get(part.cliente_id)
            override = getattr(perfil, "aportacion_inicial_override", None) if perfil else None
            if override not in (None, ""):
                aportacion_por_cliente[part.cliente_id] = _to_decimal(override)
            else:
                aportacion_por_cliente[part.cliente_id] = _to_decimal(part.importe_invertido)
        capital_en_vigor = sum(aportacion_por_cliente.values(), Decimal("0"))

        active_projects = [metric for metric in project_metrics if metric["estado"] in ACTIVE_PROJECT_STATES]
        closed_projects = [metric for metric in project_metrics if metric["estado"] in LEGACY_CLOSED_PROJECT_STATES]
        finalized_projects = [metric for metric in project_metrics if metric["estado"] in TERMINAL_PROJECT_STATES]

        total_beneficio = sum((_to_float(metric["beneficio_neto"]) for metric in project_metrics), 0.0)
        beneficio_medio = total_beneficio / len(project_metrics) if project_metrics else 0.0

        closed_bruto = sum((_to_float(metric["beneficio_bruto_operacion"]) for metric in closed_projects), 0.0)
        closed_neto = sum((_to_float(metric["beneficio_neto_operacion"]) for metric in closed_projects), 0.0)
        open_bruto = sum((_to_float(metric["beneficio_bruto_operacion"]) for metric in active_projects if metric["estado"] in ACTIVE_PROJECT_STATES), 0.0)
        open_neto = sum((_to_float(metric["beneficio_neto_operacion"]) for metric in active_projects if metric["estado"] in ACTIVE_PROJECT_STATES), 0.0)
        closed_inversion_total = sum((_to_float(metric["investment_return"]["capital_invertido"]) for metric in closed_projects if _to_float(metric["investment_return"]["capital_invertido"]) > 0), 0.0)
        closed_roi_bruto = [metric["investment_return"]["roi_bruto_medio"] for metric in closed_projects if _to_float(metric["investment_return"]["capital_invertido"]) > 0]
        closed_roi_neto = [metric["investment_return"]["roi_neto_medio"] for metric in closed_projects if _to_float(metric["investment_return"]["capital_invertido"]) > 0]
        closed_roi_bruto_total = (closed_bruto / closed_inversion_total * 100.0) if closed_inversion_total else 0.0
        closed_roi_neto_total = (closed_neto / closed_inversion_total * 100.0) if closed_inversion_total else 0.0
        closed_roi_bruto_medio = sum(closed_roi_bruto) / len(closed_roi_bruto) if closed_roi_bruto else 0.0
        closed_roi_neto_medio = sum(closed_roi_neto) / len(closed_roi_neto) if closed_roi_neto else 0.0
        closed_bruto_medio = closed_bruto / len(closed_roi_bruto) if closed_roi_bruto else 0.0
        closed_neto_medio = closed_neto / len(closed_roi_neto) if closed_roi_neto else 0.0

        return {
            "inversores_activos": inversores_activos,
            "inversores_cuota": inversores_con_cuota,
            "capital_en_vigor": capital_en_vigor,
            "capital_actual": capital_actual,
            "capital_acumulado": capital_acumulado,
            "capital_total_invertido": capital_acumulado,
            "capital_total_invertido_activo": capital_actual,
            "capital_pendiente": sum((metric["capital_pendiente"] for metric in active_projects), Decimal("0")),
            "capital_pendiente_total": sum((metric["capital_pendiente"] for metric in active_projects), Decimal("0")),
            "operaciones": len(project_metrics),
            "proyectos_activos": len(active_projects),
            "proyectos_finalizados": len(finalized_projects),
            "beneficio_total": total_beneficio,
            "beneficio_medio": beneficio_medio,
            "beneficio_estimado_total": sum((metric["beneficio_estimado"] for metric in project_metrics), 0.0),
            "beneficio_real_total": sum((metric["beneficio_real"] for metric in project_metrics), 0.0),
            "roi_medio": sum((metric["roi"] for metric in project_metrics), 0.0) / len(project_metrics) if project_metrics else 0.0,
            "roi_medio_ponderado": (
                sum((metric["beneficio_neto"] for metric in project_metrics), 0.0)
                / sum((metric["inversion_total"] for metric in project_metrics if metric["inversion_total"] > 0), 0.0)
                * 100.0
                if any(metric["inversion_total"] > 0 for metric in project_metrics)
                else 0.0
            ),
            "beneficio_cerrado_bruto": closed_bruto,
            "beneficio_cerrado_neto": closed_neto,
            "beneficio_cerrado_bruto_medio": closed_bruto_medio,
            "beneficio_cerrado_neto_medio": closed_neto_medio,
            "beneficio_abierto_bruto": open_bruto,
            "beneficio_abierto_neto": open_neto,
            "beneficio_cerrado_roi_bruto_total": closed_roi_bruto_total,
            "beneficio_cerrado_roi_neto_total": closed_roi_neto_total,
            "beneficio_cerrado_roi_bruto_medio": closed_roi_bruto_medio,
            "beneficio_cerrado_roi_neto_medio": closed_roi_neto_medio,
            "beneficio_inversure": sum((metric["beneficio_inversure"] for metric in project_metrics), 0.0),
        }

    def _build_period_summary(self, projects: list[Proyecto]) -> dict[str, Any]:
        fecha_desde = self.filters.fecha_desde
        fecha_hasta = self.filters.fecha_hasta
        range_days = ((fecha_hasta - fecha_desde).days + 1) if fecha_desde and fecha_hasta else None
        return {
            "applied": not self.filters.is_empty,
            "fecha_desde": fecha_desde.isoformat() if fecha_desde else None,
            "fecha_hasta": fecha_hasta.isoformat() if fecha_hasta else None,
            "proyecto_id": self.filters.proyecto_id,
            "estado": self.filters.estado,
            "project_count": len(projects),
            "range_days": range_days,
        }

    def _build_monthly_rows(
        self,
        *,
        project_ids: list[int],
        start: date | None,
        end: date | None,
    ) -> dict[str, list[dict[str, Any]]]:
        investment_rows = self._monthly_investment_rows(project_ids=project_ids, start=start, end=end)
        income_rows = self._monthly_money_rows(
            model=IngresoProyecto,
            project_ids=project_ids,
            start=start,
            end=end,
            amount_field="importe_real",
            fallback_field="importe",
        )
        expense_rows = self._monthly_money_rows(
            model=GastoProyecto,
            project_ids=project_ids,
            start=start,
            end=end,
            amount_field="importe_real",
            fallback_field="importe",
        )
        months = set(investment_rows) | set(income_rows) | set(expense_rows)
        if start and end:
            start_month = _month_floor(start)
            end_month = _month_floor(end)
            if start_month and end_month:
                months = set(_month_sequence(start_month, end_month))
        if not months:
            return {"investment": [], "income": [], "expense": [], "performance": []}
        ordered_months = sorted(months)
        investment_series = []
        income_series = []
        expense_series = []
        performance_series = []
        for month in ordered_months:
            capital = investment_rows.get(month, Decimal("0"))
            income = income_rows.get(month, Decimal("0"))
            expense = expense_rows.get(month, Decimal("0"))
            benefit = income - expense
            month_label = _month_label(month)
            base_point = {
                "month": month.isoformat(),
                "label": month_label,
            }
            investment_series.append({**base_point, "total": capital})
            income_series.append({**base_point, "total": income})
            expense_series.append({**base_point, "total": expense})
            performance_series.append({**base_point, "beneficio": benefit, "retorno": benefit})
        return {
            "investment": investment_series,
            "income": income_series,
            "expense": expense_series,
            "performance": performance_series,
        }

    def _monthly_investment_rows(
        self,
        *,
        project_ids: list[int],
        start: date | None,
        end: date | None,
    ) -> dict[date, Decimal]:
        rows: list[dict[str, Any]] = []
        participaciones_qs = Participacion.objects.filter(estado="confirmada", proyecto_id__in=project_ids)
        if start:
            participaciones_qs = participaciones_qs.filter(
                Q(fecha_aportacion__gte=start) | Q(fecha_aportacion__isnull=True, creado__date__gte=start)
            )
        if end:
            participaciones_qs = participaciones_qs.filter(
                Q(fecha_aportacion__lte=end) | Q(fecha_aportacion__isnull=True, creado__date__lte=end)
            )
        rows.extend(
            participaciones_qs.filter(fecha_aportacion__isnull=False)
            .annotate(month=TruncMonth("fecha_aportacion"))
            .values("month")
            .annotate(total=Sum("importe_invertido"))
            .order_by("month")
        )
        rows.extend(
            participaciones_qs.filter(fecha_aportacion__isnull=True)
            .annotate(month=TruncMonth("creado"))
            .values("month")
            .annotate(total=Sum("importe_invertido"))
            .order_by("month")
        )
        return _sum_monthly_rows(rows)

    def _monthly_money_rows(
        self,
        *,
        model,
        project_ids: list[int],
        start: date | None,
        end: date | None,
        amount_field: str,
        fallback_field: str,
    ) -> dict[date, Decimal]:
        qs = model.objects.filter(proyecto_id__in=project_ids)
        if start:
            qs = qs.filter(fecha__gte=start)
        if end:
            qs = qs.filter(fecha__lte=end)
        rows = list(qs.annotate(month=TruncMonth("fecha")).values("month", amount_field, fallback_field).order_by("month"))
        totals: dict[date, Decimal] = {}
        for row in rows:
            month = _month_floor(row.get("month"))
            if month is None:
                continue
            amount = row.get(amount_field)
            if amount in (None, ""):
                amount = row.get(fallback_field)
            totals[month] = totals.get(month, Decimal("0")) + _to_decimal(amount)
        return totals

    def _build_series(self, projects: list[Proyecto]) -> dict[str, Any]:
        project_ids = [project.id for project in projects if project.id is not None]
        if not project_ids:
            return {"monthly": {"investment": [], "income": [], "expense": [], "performance": []}}
        monthly = self._build_monthly_rows(
            project_ids=project_ids,
            start=self.filters.fecha_desde,
            end=self.filters.fecha_hasta,
        )
        return {"monthly": monthly}

    def _build_charts(self, project_metrics: list[dict[str, Any]]) -> dict[str, Any]:
        state_labels = dict(Proyecto.ESTADO_CHOICES)
        ordered_states = [state for state, _ in Proyecto.ESTADO_CHOICES]
        total_projects = len(project_metrics)
        state_counts: dict[str, int] = {}
        for metric in project_metrics:
            state = metric["estado"] or ""
            state_counts[state] = state_counts.get(state, 0) + 1
        state_distribution = [
            {
                "estado": state,
                "estado_label": state_labels.get(state, state),
                "total": total,
                "pct": (total / total_projects * 100.0) if total_projects else 0.0,
            }
            for state in ordered_states
            if (total := state_counts.get(state)) is not None
        ]
        for state, total in sorted(state_counts.items(), key=lambda item: item[0]):
            if state in ordered_states:
                continue
            state_distribution.append(
                {
                    "estado": state,
                    "estado_label": state_labels.get(state, state),
                    "total": total,
                    "pct": (total / total_projects * 100.0) if total_projects else 0.0,
                }
            )

        max_benefit = max((_to_float(metric["beneficio_neto"]) for metric in project_metrics), default=0.0)
        benefit_bars = []
        for metric in sorted(project_metrics, key=lambda item: _to_float(item["beneficio_neto"]), reverse=True):
            benefit = _to_float(metric["beneficio_neto"])
            valor_adquisicion = _to_float(metric["valor_adquisicion"])
            pct_relacion = (benefit / valor_adquisicion * 100.0) if valor_adquisicion else 0.0
            benefit_bars.append(
                {
                    "project_id": metric["project_id"],
                    "nombre": metric["nombre"],
                    "estado": metric["estado"],
                    "estado_label": metric["estado_label"],
                    "valor": benefit,
                    "valor_fmt": _fmt_eur(benefit),
                    "pct": (benefit / max_benefit * 100.0) if max_benefit else 0.0,
                    "pct_fmt": _fmt_pct(pct_relacion),
                    "color": self._state_color(metric["estado"]),
                }
            )

        deviation = [
            {
                "project_id": metric["project_id"],
                "nombre": metric["nombre"],
                "estado": metric["estado"],
                "estado_label": metric["estado_label"],
                "estimado": metric["deviation"]["estimado"],
                "real": metric["deviation"]["real"],
                "delta": metric["deviation"]["delta"],
                "delta_pct": metric["deviation"]["delta_pct"],
            }
            for metric in project_metrics
            if metric.get("has_movimientos")
        ]

        return {
            "state_distribution": state_distribution,
            "benefit_bars": benefit_bars,
            "deviation": deviation,
        }

    def _build_rankings(self, project_metrics: list[dict[str, Any]]) -> dict[str, Any]:
        ranked_by_roi = sorted(project_metrics, key=lambda item: _to_float(item["roi"]), reverse=True)
        ranked_by_benefit = sorted(project_metrics, key=lambda item: _to_float(item["beneficio_neto"]), reverse=True)
        comparison = sorted(project_metrics, key=lambda item: _to_float(item["capital_captado"]), reverse=True)
        return {
            "best_roi": [self._ranking_projection(item) for item in ranked_by_roi[:5]],
            "worst_roi": [self._ranking_projection(item) for item in list(reversed(ranked_by_roi[-5:]))],
            "best_benefit": [self._ranking_projection(item) for item in ranked_by_benefit[:5]],
            "worst_benefit": [self._ranking_projection(item) for item in list(reversed(ranked_by_benefit[-5:]))],
            "investment_return": [self._comparison_projection(item) for item in comparison],
        }

    def _ranking_projection(self, metric: dict[str, Any]) -> dict[str, Any]:
        return {
            "project_id": metric["project_id"],
            "codigo_proyecto": metric["codigo_proyecto"],
            "nombre": metric["nombre"],
            "estado": metric["estado"],
            "estado_label": metric["estado_label"],
            "capital_objetivo": metric["capital_objetivo"],
            "capital_captado": metric["capital_captado"],
            "capital_pendiente": metric["capital_pendiente"],
            "beneficio_neto": metric["beneficio_neto"],
            "roi": metric["roi"],
            "beneficio_inversure": metric["beneficio_inversure"],
        }

    def _comparison_projection(self, metric: dict[str, Any]) -> dict[str, Any]:
        return {
            "project_id": metric["project_id"],
            "nombre": metric["nombre"],
            "estado": metric["estado"],
            "capital_invertido": metric["investment_return"]["capital_invertido"],
            "retorno_total": metric["investment_return"]["retorno_total"],
            "beneficio_neto": metric["investment_return"]["beneficio_neto"],
            "roi_bruto_medio": metric["investment_return"]["roi_bruto_medio"],
            "roi_neto_medio": metric["investment_return"]["roi_neto_medio"],
        }

    def _build_alerts(self, projects: list[Proyecto], project_metrics: list[dict[str, Any]]) -> dict[str, Any]:
        project_ids = [project.id for project in projects if project.id is not None]
        today = timezone.now().date()
        checklist_items = [
            item
            for project in projects
            for item in getattr(project, "checklist_items_dashboard", [])
            if item.estado != "hecho"
        ]
        if is_comercial_user(self.user) and not is_admin_user(self.user) and not is_direccion_user(self.user):
            checklist_items = [item for item in checklist_items if item.responsable_user_id == self.user.id]
        checklist_items.sort(
            key=lambda item: (
                item.fecha_objetivo is not None,
                item.fecha_objetivo or date.min,
                item.id or 0,
            )
        )
        checklist_overdue_count = sum(1 for item in checklist_items if item.fecha_objetivo and item.fecha_objetivo < today)
        operational_items = []
        for item in checklist_items[:6]:
            overdue = bool(item.fecha_objetivo and item.fecha_objetivo < today)
            dias_retraso = (today - item.fecha_objetivo).days if overdue and item.fecha_objetivo else 0
            operational_items.append(
                {
                    "proyecto": item.proyecto.nombre if item.proyecto else "",
                    "fase": item.get_fase_display(),
                    "titulo": item.titulo,
                    "responsable": item.responsable or "",
                    "fecha_objetivo": item.fecha_objetivo,
                    "overdue": overdue,
                    "dias_retraso": dias_retraso,
                }
            )

        pending_solicitudes = (
            SolicitudParticipacion.objects.filter(proyecto_id__in=project_ids, estado="pendiente").count()
            if project_ids
            else 0
        )
        negative_roi_projects = [
            self._ranking_projection(metric)
            for metric in project_metrics
            if _to_float(metric["roi"]) < 0
        ][:5]
        over_budget_projects = [
            {
                "project_id": metric["project_id"],
                "nombre": metric["nombre"],
                "estado": metric["estado"],
                "estado_label": metric["estado_label"],
                "gastos_real_total": metric["gastos_real_total"],
                "gastos_est_total": metric["gastos_est_total"],
                "sobrecoste": metric["gastos_real_total"] - metric["gastos_est_total"],
            }
            for metric in project_metrics
            if metric["gastos_real_total"] > metric["gastos_est_total"] > 0
        ][:5]

        factura_ids = set(
            FacturaGasto.objects.filter(gasto__proyecto_id__in=project_ids).values_list("gasto_id", flat=True)
        )
        justificante_ids = set(
            JustificanteIngreso.objects.filter(ingreso__proyecto_id__in=project_ids).values_list(
                "ingreso_id", flat=True
            )
        )
        missing_facturas: list[dict[str, Any]] = []
        missing_justificantes: list[dict[str, Any]] = []
        for project in projects:
            gastos_confirmados = [gasto for gasto in project.gastos_proyecto.all() if gasto.estado == "confirmado"]
            ingresos_confirmados = [ingreso for ingreso in project.ingresos.all() if ingreso.estado == "confirmado"]
            missing_gastos = [gasto for gasto in gastos_confirmados if gasto.id not in factura_ids]
            missing_ingresos = [ingreso for ingreso in ingresos_confirmados if ingreso.id not in justificante_ids]
            if missing_gastos:
                missing_facturas.append(
                    {
                        "project_id": project.id,
                        "nombre": project.nombre or f"Proyecto {project.id}",
                        "count": len(missing_gastos),
                    }
                )
            if missing_ingresos:
                missing_justificantes.append(
                    {
                        "project_id": project.id,
                        "nombre": project.nombre or f"Proyecto {project.id}",
                        "count": len(missing_ingresos),
                    }
                )

        items = []
        for alert in negative_roi_projects:
            items.append(
                {
                    "severity": "warning",
                    "category": "roi_negativo",
                    "project_id": alert["project_id"],
                    "title": f"ROI negativo en {alert['nombre']}",
                    "detail": f"ROI actual: {alert['roi']:.2f}%",
                }
            )
        for alert in over_budget_projects:
            items.append(
                {
                    "severity": "warning",
                    "category": "sobrecoste",
                    "project_id": alert["project_id"],
                    "title": f"Sobrecoste en {alert['nombre']}",
                    "detail": f"Desviación: {alert['sobrecoste']:.2f} €",
                }
            )
        if pending_solicitudes:
            items.append(
                {
                    "severity": "info",
                    "category": "solicitudes_pendientes",
                    "title": "Solicitudes de participación pendientes",
                    "detail": f"{pending_solicitudes} solicitudes por revisar",
                }
            )
        if missing_facturas:
            missing_facturas_count = sum(cast(int, item.get("count", 0) or 0) for item in missing_facturas)
            items.append(
                {
                    "severity": "warning",
                    "category": "facturas_faltantes",
                    "title": "Gastos confirmados sin factura",
                    "detail": f"{missing_facturas_count} líneas sin factura",
                }
            )
        if missing_justificantes:
            missing_justificantes_count = sum(cast(int, item.get("count", 0) or 0) for item in missing_justificantes)
            items.append(
                {
                    "severity": "warning",
                    "category": "justificantes_faltantes",
                    "title": "Ingresos confirmados sin justificante",
                    "detail": f"{missing_justificantes_count} líneas sin justificante",
                }
            )
        return {
            "operational": {
                "pendientes": len(checklist_items),
                "vencidas": checklist_overdue_count,
                "items": operational_items,
            },
            "financial": {
                "pending_solicitudes": pending_solicitudes,
                "negative_roi_projects": negative_roi_projects,
                "over_budget_projects": over_budget_projects,
                "missing_facturas": missing_facturas,
                "missing_justificantes": missing_justificantes,
                "items": items,
            },
            "summary": {
                "total": len(items) + len(checklist_items),
                "critical": sum(1 for alert in items if str(alert.get("severity", "")) == "critical"),
                "warning": sum(1 for alert in items if str(alert.get("severity", "")) == "warning"),
                "info": sum(1 for alert in items if str(alert.get("severity", "")) == "info"),
            },
        }

    def _state_color(self, state: str) -> str:
        return {
            "captacion": "#f59e0b",
            "comprado": "#0ea5e9",
            "comercializacion": "#6366f1",
            "reservado": "#22c55e",
            "vendido": "#10b981",
            "cerrado": "#14b8a6",
            "descartado": "#94a3b8",
        }.get(state, "#f2b53b")


def build_financial_dashboard_data(user, filters: FinancialDashboardFilters | None = None) -> dict[str, Any]:
    """Convenience wrapper for API views, widgets and the dashboard page."""

    return FinancialDashboardService(user=user, filters=filters).build()
