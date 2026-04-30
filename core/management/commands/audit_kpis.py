from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal
from typing import Any

from django.core.management.base import BaseCommand
from django.db import transaction
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


def _deep_set(d: dict, keys: tuple[str, ...], value: Any) -> bool:
    cur: Any = d
    for k in keys[:-1]:
        nxt = cur.get(k)
        if not isinstance(nxt, dict):
            nxt = {}
            cur[k] = nxt
        cur = nxt
    last = keys[-1]
    prev = cur.get(last)
    if prev == value:
        return False
    cur[last] = value
    return True


def _maybe_fix_snapshot_roi(
    *,
    proyecto: Any,
    roi_mem: float,
    beneficio_mem: float,
    snap: dict,
    backup_snapshot: bool,
) -> bool:
    """
    Sincroniza ROI (y campos mínimos relacionados) en:
    - Proyecto.snapshot_datos
    - Proyecto.extra['ultimo_guardado']['payload'] (si existe)
    - Proyecto.extra['payload'] (si existe)
    - snapshot_datos['_overlay'] (fallback legacy)

    Devuelve True si se guardó algún cambio.
    """
    from core.models import ProyectoSnapshot  # local import to avoid import cost in command listing

    changed = False

    base_sd = getattr(proyecto, "snapshot_datos", None)
    if not isinstance(base_sd, dict):
        base_sd = {}

    extra = getattr(proyecto, "extra", None)
    if not isinstance(extra, dict):
        extra = {}

    overlay: dict | None = None
    if isinstance(_deep_get(extra, "ultimo_guardado", "payload"), dict):
        overlay = _deep_get(extra, "ultimo_guardado", "payload")
    elif isinstance(extra.get("payload"), dict):
        overlay = extra.get("payload")  # type: ignore[assignment]

    legacy_overlay: dict | None = None
    if overlay is None:
        lo = base_sd.get("_overlay")
        if isinstance(lo, dict):
            legacy_overlay = lo

    def _backup_now() -> None:
        try:
            ProyectoSnapshot.objects.create(
                proyecto=proyecto,
                fuente="guardado",
                nota="auto-fix: sync ROI snapshot desde memoria",
                datos=snap or {},
            )
        except Exception:
            pass

    roi_round = float(round(float(roi_mem or 0.0), 4))
    beneficio_round = float(round(float(beneficio_mem or 0.0), 4))

    def _apply_to_dict(dst: dict | None) -> bool:
        if not isinstance(dst, dict):
            return False
        local_changed = False
        # Paths típicos leídos por plantillas/front
        local_changed |= _deep_set(dst, ("kpis", "metricas", "roi_estimado"), roi_round)
        local_changed |= _deep_set(dst, ("kpis", "metricas", "roi"), roi_round)
        local_changed |= _deep_set(dst, ("economico", "roi_estimado"), roi_round)
        local_changed |= _deep_set(dst, ("economico", "roi"), roi_round)
        local_changed |= _deep_set(dst, ("resultado", "roi"), roi_round)
        # Campos relacionados (mínimos) para evitar PDFs/cartas incoherentes
        local_changed |= _deep_set(dst, ("resultado", "beneficio_neto"), beneficio_round)
        return local_changed

    base_changed = _apply_to_dict(base_sd)
    overlay_changed = _apply_to_dict(overlay)
    legacy_changed = _apply_to_dict(legacy_overlay)

    if not (base_changed or overlay_changed or legacy_changed):
        return False

    if backup_snapshot:
        _backup_now()

    with transaction.atomic():
        if base_changed:
            try:
                proyecto.snapshot_datos = base_sd
                proyecto.save(update_fields=["snapshot_datos", "actualizado"])
                changed = True
            except Exception:
                pass

        if overlay_changed:
            try:
                if isinstance(_deep_get(extra, "ultimo_guardado", "payload"), dict):
                    extra["ultimo_guardado"]["payload"] = overlay  # type: ignore[index]
                else:
                    extra["payload"] = overlay
                proyecto.extra = extra
                proyecto.save(update_fields=["extra", "actualizado"])
                changed = True
            except Exception:
                pass

        if legacy_changed:
            try:
                base_sd["_overlay"] = legacy_overlay
                proyecto.snapshot_datos = base_sd
                proyecto.save(update_fields=["snapshot_datos", "actualizado"])
                changed = True
            except Exception:
                pass

    return changed


class Command(BaseCommand):
    help = "Audita KPIs (ROI y % participación) recalculando desde movimientos."
    requires_system_checks = []
    requires_migrations_checks = False

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
        parser.add_argument(
            "--fix-snapshot-roi",
            action="store_true",
            help="Sincronizar ROI en snapshot_datos/extra.payload para que no quede desfasado.",
        )
        parser.add_argument(
            "--no-backup-snapshot",
            action="store_true",
            help="No crear ProyectoSnapshot de backup al tocar snapshots.",
        )
        parser.add_argument(
            "--only-mismatches",
            action="store_true",
            help="Imprimir solo filas con discrepancias (ROI o % participación).",
        )

    def handle(self, *args, **opts):
        from core.models import Participacion, Proyecto  # local import
        from core.views import _get_snapshot_comunicacion, _resultado_desde_memoria, _capital_objetivo_desde_memoria  # type: ignore

        project_id = opts["project_id"]
        limit = int(opts["limit"] or 0)
        threshold = float(opts["threshold"] or 0.0)
        fix_participacion = bool(opts["fix_participacion"])
        fix_proyecto_roi = bool(opts["fix_proyecto_roi"])
        fix_snapshot_roi = bool(opts["fix_snapshot_roi"])
        backup_snapshot = not bool(opts["no_backup_snapshot"])
        only_mismatches = bool(opts["only_mismatches"])

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
            capital_objetivo = 0.0
            try:
                capital_objetivo = float(_capital_objetivo_desde_memoria(proyecto, snap if isinstance(snap, dict) else {}) or 0.0)
            except Exception:
                capital_objetivo = 0.0
            pct_max_diff: float | None = None
            if capital_objetivo > 0 or total_invertido > 0:
                diffs = []
                for p in parts:
                    denom = capital_objetivo if capital_objetivo > 0 else total_invertido
                    calc = float(Decimal(str(p.importe_invertido or 0)) / Decimal(str(denom)) * Decimal("100")) if denom else 0.0
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

            roi_bad = False
            if roi_snapshot is None:
                roi_bad = abs(roi_mem) >= threshold  # si no hay snapshot, discrepancia si hay ROI no-trivial
            else:
                roi_bad = abs(roi_mem - roi_snapshot) >= threshold
            if roi_bad:
                bad_roi += 1
            pct_bad = pct_max_diff is not None and pct_max_diff >= 0.1
            if pct_bad:
                bad_pct += 1

            if fix_snapshot_roi and (roi_bad or roi_snapshot is None):
                try:
                    _maybe_fix_snapshot_roi(
                        proyecto=proyecto,
                        roi_mem=roi_mem,
                        beneficio_mem=beneficio_mem,
                        snap=snap if isinstance(snap, dict) else {},
                        backup_snapshot=backup_snapshot,
                    )
                except Exception:
                    pass

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

        self.stdout.write(
            "proyecto_id;proyecto;estado;roi_mem;roi_snapshot;roi_model;total_invertido;n_parts;pct_participacion_max_diff"
        )
        for r in rows:
            roi_bad_row = (
                (r.roi_snapshot is None and abs(r.roi_mem) >= threshold)
                or (r.roi_snapshot is not None and abs(r.roi_mem - r.roi_snapshot) >= threshold)
            )
            pct_bad_row = (
                r.pct_participacion_max_diff is not None and r.pct_participacion_max_diff >= 0.1
            )
            if only_mismatches and not (roi_bad_row or pct_bad_row):
                continue
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
