from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from django.core.management.base import BaseCommand


@dataclass
class _Row:
    proyecto_id: int
    beneficio: float
    beneficio_calc: float
    diff: float
    roi: float
    valor_adquisicion: float
    valor_transmision: float
    base_memoria_real: bool


def _safe_float(x: Any, default: float = 0.0) -> float:
    try:
        if x in (None, "", "—"):
            return default
        return float(x)
    except Exception:
        return default


class Command(BaseCommand):
    help = "Audita coherencia de cálculos económicos (sin imprimir PII)."
    requires_system_checks = []
    requires_migrations_checks = False

    def add_arguments(self, parser):
        parser.add_argument("--project-id", type=int, default=None, help="Auditar solo un proyecto por id.")
        parser.add_argument("--limit", type=int, default=0, help="Limitar número de proyectos.")
        parser.add_argument(
            "--epsilon",
            type=float,
            default=0.01,
            help="Tolerancia (€) para marcar discrepancias de beneficio.",
        )
        parser.add_argument(
            "--only-mismatches",
            action="store_true",
            help="Mostrar solo filas con discrepancias (|diff| > epsilon).",
        )

    def handle(self, *args, **opts):
        from core.models import Proyecto  # local import
        from core.views import _get_snapshot_comunicacion, _resultado_desde_memoria  # type: ignore

        project_id = opts.get("project_id")
        limit = int(opts.get("limit") or 0)
        epsilon = float(opts.get("epsilon") or 0.0)
        only_mismatches = bool(opts.get("only_mismatches"))

        qs = Proyecto.objects.all().order_by("id")
        if project_id:
            qs = qs.filter(id=project_id)
        if limit > 0:
            qs = qs[:limit]

        rows: list[_Row] = []
        bad = 0

        for proyecto in qs:
            snap = _get_snapshot_comunicacion(proyecto)
            res = _resultado_desde_memoria(proyecto, snap if isinstance(snap, dict) else {})

            valor_adq = _safe_float(res.get("valor_adquisicion"), 0.0)
            valor_trans = _safe_float(res.get("valor_transmision"), 0.0)
            beneficio = _safe_float(res.get("beneficio_neto"), 0.0)
            roi = _safe_float(res.get("roi"), 0.0)
            base_memoria_real = bool(res.get("base_memoria_real"))

            beneficio_calc = (valor_trans - valor_adq) if (valor_adq or valor_trans) else 0.0
            diff = beneficio - beneficio_calc

            is_bad = abs(diff) > epsilon
            if is_bad:
                bad += 1

            row = _Row(
                proyecto_id=int(proyecto.id),
                beneficio=beneficio,
                beneficio_calc=beneficio_calc,
                diff=diff,
                roi=roi,
                valor_adquisicion=valor_adq,
                valor_transmision=valor_trans,
                base_memoria_real=base_memoria_real,
            )
            if only_mismatches and not is_bad:
                continue
            rows.append(row)

        self.stdout.write(
            "proyecto_id;beneficio;beneficio_calc;diff;roi;valor_adquisicion;valor_transmision;base_memoria_real"
        )
        for r in rows:
            self.stdout.write(
                f"{r.proyecto_id};"
                f"{r.beneficio:.2f};"
                f"{r.beneficio_calc:.2f};"
                f"{r.diff:.2f};"
                f"{r.roi:.4f};"
                f"{r.valor_adquisicion:.2f};"
                f"{r.valor_transmision:.2f};"
                f"{1 if r.base_memoria_real else 0}"
            )

        self.stdout.write(self.style.WARNING(f"Discrepancias |diff| > {epsilon:.2f}€: {bad}"))
