from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal
from typing import Any

from django.core.management.base import BaseCommand
from django.db.models import Sum


@dataclass
class _AuditRow:
    proyecto_id: int
    proyecto_nombre: str
    estado: str
    roi_mem: float
    roi_snapshot: float | None
    roi_model: float | None
    total_invertido: float
    n_participaciones: int
    pct_participacion_max_diff: float | None


def _safe_float(x: Any) -> float | None:
    try:
        if x in (None, "", "—"):
            return None
        return float(x)
    except Exception:
        return None


def _deep_get(d: dict, *keys: str) -> Any:
    cur: Any = d
    for k in keys:
        if not isinstance(cur, dict):
            return None
        cur = cur.get(k)
    return cur


class Command(BaseCommand):
    help = "Audita KPIs (ROI y % participación) recalculando desde movimientos."

    def add_arguments(self, parser):
        parser.add_argument("--project-id", type=int, default=None, help="Auditar solo un proyecto por id.")
        parser.add_argument("--limit", type=int, default=0, help="Limitar número de proyectos.")
        parser.add_argument(
            "--threshold",
            type=float,
            default=0.05,
            help="Umbral (en puntos porcentuales) para marcar discrepancias de ROI.",
        )
        parser.add_argument(
            "--fix-participacion",
            action="store_true",
            help="Actualizar Participacion.porcentaje_participacion para confirmadas.",
        )
        parser.add_argument(
            "--fix-proyecto-roi",
            action="store_true",
            help="Actualizar Proyecto.roi y Proyecto.beneficio_neto con el cálculo de memoria.",
        )

    def handle(self, *args, **opts):
        from core.models import Participacion, Proyecto  # local import
        from core.views import _get_snapshot_comunicacion, _resultado_desde_memoria  # type: ignore

        project_id = opts["project_id"]
        limit = int(opts["limit"] or 0)
        threshold = float(opts["threshold"] or 0.0)
        fix_participacion = bool(opts["fix_participacion"])
        fix_proyecto_roi = bool(opts["fix_proyecto_roi"])

        qs = Proyecto.objects.all().order_by("id")
        if project_id:
            qs = qs.filter(id=project_id)
        if limit > 0:
            qs = qs[:limit]

        rows: list[_AuditRow] = []
        bad_roi = 0
        bad_pct = 0

        for proyecto in qs:
            snap = _get_snapshot_comunicacion(proyecto)
            resultado = _resultado_desde_memoria(proyecto, snap if isinstance(snap, dict) else {})
            roi_mem = float(resultado.get("roi") or 0.0)
            beneficio_mem = float(resultado.get("beneficio_neto") or 0.0)

            roi_snapshot = _safe_float(_deep_get(snap, "kpis", "metricas", "roi_estimado"))
            if roi_snapshot is None:
                roi_snapshot = _safe_float(_deep_get(snap, "kpis", "metricas", "roi"))
            if roi_snapshot is None:
                roi_snapshot = _safe_float(_deep_get(snap, "economico", "roi_estimado"))
            if roi_snapshot is None:
                roi_snapshot = _safe_float(_deep_get(snap, "economico", "roi"))

            roi_model = _safe_float(getattr(proyecto, "roi", None))

            parts = list(
                Participacion.objects.filter(proyecto=proyecto, estado="confirmada").order_by("id")
            )
            total_invertido = float(
                Participacion.objects.filter(proyecto=proyecto, estado="confirmada")
                .aggregate(total=Sum("importe_invertido"))
                .get("total")
                or 0
            )
            pct_max_diff: float | None = None
            if total_invertido > 0:
                diffs = []
                for p in parts:
                    calc = float(Decimal(str(p.importe_invertido or 0)) / Decimal(str(total_invertido)) * Decimal("100"))
                    stored = _safe_float(getattr(p, "porcentaje_participacion", None))
                    if stored is None:
                        diffs.append(None)
                    else:
                        diffs.append(abs(calc - stored))
                    if fix_participacion:
                        try:
                            p.porcentaje_participacion = Decimal(str(round(calc, 2)))
                        except Exception:
                            pass
                # max diff ignoring None
                diffs_num = [d for d in diffs if isinstance(d, (int, float))]
                pct_max_diff = max(diffs_num) if diffs_num else None
                if fix_participacion:
                    Participacion.objects.bulk_update(parts, ["porcentaje_participacion"])
            else:
                pct_max_diff = None

            if fix_proyecto_roi:
                try:
                    proyecto.roi = Decimal(str(round(roi_mem, 2)))
                    proyecto.beneficio_neto = Decimal(str(round(beneficio_mem, 2)))
                    proyecto.save(update_fields=["roi", "beneficio_neto", "actualizado"])
                except Exception:
                    pass

            if roi_snapshot is not None and abs(roi_mem - roi_snapshot) >= threshold:
                bad_roi += 1
            if pct_max_diff is not None and pct_max_diff >= 0.1:
                bad_pct += 1

            rows.append(
                _AuditRow(
                    proyecto_id=proyecto.id,
                    proyecto_nombre=(proyecto.nombre or "").strip() or f"Proyecto {proyecto.id}",
                    estado=(proyecto.estado or "").strip(),
                    roi_mem=roi_mem,
                    roi_snapshot=roi_snapshot,
                    roi_model=roi_model,
                    total_invertido=total_invertido,
                    n_participaciones=len(parts),
                    pct_participacion_max_diff=pct_max_diff,
                )
            )

        self.stdout.write("proyecto_id;proyecto;estado;roi_mem;roi_snapshot;roi_model;total_invertido;n_parts;pct_participacion_max_diff")
        for r in rows:
            self.stdout.write(
                f"{r.proyecto_id};{r.proyecto_nombre};{r.estado};"
                f"{r.roi_mem:.4f};"
                f"{'' if r.roi_snapshot is None else f'{r.roi_snapshot:.4f}'};"
                f"{'' if r.roi_model is None else f'{r.roi_model:.4f}'};"
                f"{r.total_invertido:.2f};{r.n_participaciones};"
                f"{'' if r.pct_participacion_max_diff is None else f'{r.pct_participacion_max_diff:.4f}'}"
            )

        self.stdout.write(self.style.WARNING(f"Discrepancias ROI >= {threshold:.2f}pp: {bad_roi}"))
        self.stdout.write(self.style.WARNING(f"Discrepancias % participación >= 0.10pp: {bad_pct}"))
