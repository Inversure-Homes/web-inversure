from __future__ import annotations

from dataclasses import dataclass

from django.core.management.base import BaseCommand
from django.db.models import Count, Q


@dataclass
class _Row:
    proyecto_id: int
    estado: str
    ingresos_confirmados: int
    ingresos_confirmados_no_venta: int
    ingresos_estimados: int


class Command(BaseCommand):
    help = "Audita integridad de datos (tipado de ingresos/estados) para evitar PDFs/KPIs incoherentes."
    requires_system_checks = []
    requires_migrations_checks = False

    def add_arguments(self, parser):
        parser.add_argument("--project-id", type=int, default=None, help="Auditar solo un proyecto por id.")
        parser.add_argument("--limit", type=int, default=0, help="Limitar número de proyectos.")
        parser.add_argument(
            "--only-warnings",
            action="store_true",
            help="Mostrar solo proyectos con señales de datos incoherentes.",
        )
        parser.add_argument(
            "--fix",
            action="store_true",
            help="Arreglar tipado de ingresos confirmados en proyectos 'vendido/cerrado' (modo seguro).",
        )
        parser.add_argument(
            "--apply",
            action="store_true",
            help="Aplicar cambios en BD. Si no, solo imprime qué cambiaría (dry-run).",
        )

    def handle(self, *args, **opts):
        from core.models import IngresoProyecto, Proyecto  # local import

        project_id = opts.get("project_id")
        limit = int(opts.get("limit") or 0)
        only_warnings = bool(opts.get("only_warnings"))
        fix = bool(opts.get("fix"))
        apply = bool(opts.get("apply"))

        qs = Proyecto.objects.all().order_by("id")
        if project_id:
            qs = qs.filter(id=project_id)
        if limit > 0:
            qs = qs[:limit]

        estados_cierre = {"vendido", "cerrado"}
        tipos_venta = {"venta", "senal", "anticipo"}
        tipos_candidatos_retipar = {"otro"}  # modo seguro: solo retipar "otro"

        rows: list[_Row] = []
        warnings = 0
        fixed = 0
        would_fix = 0

        for p in qs.iterator():
            estado = (getattr(p, "estado", "") or "").strip().lower()
            ingresos_qs = IngresoProyecto.objects.filter(proyecto=p)
            agg = ingresos_qs.aggregate(
                confirmados=Count("id", filter=Q(estado="confirmado")),
                estimados=Count("id", filter=Q(estado="estimado")),
                confirmados_no_venta=Count(
                    "id",
                    filter=Q(estado="confirmado") & ~Q(tipo__in=list(tipos_venta)),
                ),
            )
            confirmados = int(agg.get("confirmados") or 0)
            estimados = int(agg.get("estimados") or 0)
            confirmados_no_venta = int(agg.get("confirmados_no_venta") or 0)

            is_warning = False
            if estado in estados_cierre and confirmados > 0 and confirmados_no_venta > 0:
                # En estados de cierre, suele esperarse que el cobro de transmisión esté tipado como venta/señal/anticipo.
                is_warning = True

            # Fix seguro: si el proyecto está vendido/cerrado y NO hay ningún ingreso confirmado de venta/señal/anticipo,
            # pero sí hay ingresos confirmados "otro" positivos, tipar el mayor como "venta".
            if fix and estado in estados_cierre:
                try:
                    has_venta = ingresos_qs.filter(estado="confirmado", tipo__in=list(tipos_venta)).exists()
                    if not has_venta:
                        # Modo seguro:
                        # - Si el proyecto tiene exactamente 1 ingreso confirmado positivo total
                        # - y su tipo es "otro"
                        # => retiparlo como "venta".
                        confirmed_pos = ingresos_qs.filter(estado="confirmado").filter(
                            Q(importe__gt=0) | Q(importe_real__gt=0)
                        )
                        if confirmed_pos.count() == 1:
                            target = confirmed_pos.first()
                            if (
                                target is not None
                                and (getattr(target, "tipo", "") or "").strip().lower() in tipos_candidatos_retipar
                            ):
                                would_fix += 1
                                if apply:
                                    target.tipo = "venta"
                                    target.save(update_fields=["tipo", "actualizado"])
                                    fixed += 1
                except Exception:
                    pass

            if only_warnings and not is_warning:
                continue
            if is_warning:
                warnings += 1

            rows.append(
                _Row(
                    proyecto_id=int(p.id),
                    estado=estado,
                    ingresos_confirmados=confirmados,
                    ingresos_confirmados_no_venta=confirmados_no_venta,
                    ingresos_estimados=estimados,
                )
            )

        self.stdout.write(
            "proyecto_id;estado;ingresos_confirmados;ingresos_confirmados_no_venta;ingresos_estimados"
        )
        for r in rows:
            self.stdout.write(
                f"{r.proyecto_id};{r.estado};{r.ingresos_confirmados};{r.ingresos_confirmados_no_venta};{r.ingresos_estimados}"
            )
        self.stdout.write(self.style.WARNING(f"Warnings: {warnings}"))
        if fix:
            mode = "APPLY" if apply else "DRY-RUN"
            self.stdout.write(self.style.WARNING(f"{mode}: would_fix={would_fix} fixed={fixed}"))
