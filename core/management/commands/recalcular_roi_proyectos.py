from decimal import Decimal

from django.core.management.base import BaseCommand

from core.models import Proyecto
from core import views as core_views


class Command(BaseCommand):
    help = "Recalcula y persiste beneficio_neto/roi en Proyecto para todas las operaciones (fuente: movimientos)."

    def add_arguments(self, parser):
        parser.add_argument(
            "--dry-run",
            action="store_true",
            help="Calcula pero no guarda cambios.",
        )
        parser.add_argument(
            "--ids",
            nargs="*",
            type=int,
            default=None,
            help="IDs de proyecto a recalcular (si se omite, recalcula todos).",
        )

    def handle(self, *args, **options):
        dry_run = bool(options.get("dry_run"))
        ids = options.get("ids") or None

        qs = Proyecto.objects.all().order_by("id")
        if ids:
            qs = qs.filter(id__in=ids)

        total = 0
        updated = 0
        for proyecto in qs.iterator():
            total += 1
            try:
                snap = core_views._get_snapshot_comunicacion(proyecto)
                res = core_views._resultado_desde_memoria(proyecto, snap if isinstance(snap, dict) else {})
                beneficio = res.get("beneficio_neto")
                roi = res.get("roi")
                if beneficio is None or roi is None:
                    continue

                beneficio_dec = Decimal(str(float(beneficio)))
                roi_dec = Decimal(str(float(roi)))

                changed = (
                    (proyecto.beneficio_neto is None or Decimal(proyecto.beneficio_neto) != beneficio_dec)
                    or (proyecto.roi is None or Decimal(proyecto.roi) != roi_dec)
                )
                if not changed:
                    continue

                if not dry_run:
                    proyecto.beneficio_neto = beneficio_dec
                    proyecto.roi = roi_dec
                    proyecto.save(update_fields=["beneficio_neto", "roi"])
                updated += 1
            except Exception as e:
                self.stderr.write(f"[{proyecto.id}] error: {e}")

        mode = "DRY-RUN" if dry_run else "OK"
        self.stdout.write(f"{mode}: proyectos={total} actualizados={updated}")

