from __future__ import annotations

from datetime import date, timedelta
from decimal import Decimal

from django.core.management.base import BaseCommand
from django.db import transaction
from django.db.models import Sum
from django.utils import timezone


class Command(BaseCommand):
    help = "Crea un proyecto demo con movimientos para validar lógicas de KPIs (ROI/participación/plazos)."
    requires_system_checks = []
    requires_migrations_checks = False

    def add_arguments(self, parser):
        parser.add_argument(
            "--name",
            default="DEMO KPI",
            help="Nombre del proyecto demo (por defecto: DEMO KPI).",
        )
        parser.add_argument(
            "--reset",
            action="store_true",
            help="Borra proyectos demo previos con el mismo nombre.",
        )

    @transaction.atomic
    def handle(self, *args, **opts):
        from core.models import Cliente, GastoProyecto, IngresoProyecto, Participacion, Proyecto  # local import
        from core.models import DatosEconomicosProyecto  # local import
        from core.views import (  # type: ignore
            _build_comunicacion_context,
            _get_snapshot_comunicacion,
            _resultado_desde_memoria,
        )

        name = (opts.get("name") or "DEMO KPI").strip()
        reset = bool(opts.get("reset"))

        if reset:
            prev = list(Proyecto.objects.filter(nombre=name).values_list("id", flat=True))
            if prev:
                # `GastoProyecto.proyecto` usa PROTECT; borrar dependencias primero
                GastoProyecto.objects.filter(proyecto_id__in=prev).delete()
                IngresoProyecto.objects.filter(proyecto_id__in=prev).delete()
                Participacion.objects.filter(proyecto_id__in=prev).delete()
                Proyecto.objects.filter(id__in=prev).delete()
            # Limpiar clientes demo (hash único por dni/cif)
            Cliente.objects.filter(dni_cif__startswith="X-DEMO-").delete()

        # --- Proyecto base ---
        hoy = timezone.now().date()
        fecha_compra = hoy - timedelta(days=103)
        proyecto = Proyecto.objects.create(
            nombre=name,
            estado="comercializacion",
            fecha=hoy,
            fecha_compra=fecha_compra,
            precio_compra_inmueble=Decimal("100000.00"),
            precio_propiedad=Decimal("100000.00"),
            meses=4,
        )
        DatosEconomicosProyecto.objects.create(
            proyecto=proyecto,
            estado_operativo="comercializacion",
            fecha_estado=hoy,
            fecha_compra_real=fecha_compra,
            fecha_venta_real=hoy + timedelta(days=30),
        )

        # --- Clientes demo ---
        # Importante: `dni_cif_hash` es único. Si no ponemos DNI/CIF, se queda en "" y rompe por UNIQUE.
        suffix = str(int(timezone.now().timestamp()))
        c1 = Cliente.objects.create(
            nombre="DEMO INVERSOR A",
            dni_cif=f"X-DEMO-A-{suffix}",
            email="demo+a@example.com",
            telefono="000000000",
        )
        c2 = Cliente.objects.create(
            nombre="DEMO INVERSOR B",
            dni_cif=f"X-DEMO-B-{suffix}",
            email="demo+b@example.com",
            telefono="000000001",
        )

        # --- Participaciones confirmadas ---
        p1 = Participacion.objects.create(
            proyecto=proyecto,
            cliente=c1,
            importe_invertido=Decimal("90000.00"),
            estado="confirmada",
        )
        p2 = Participacion.objects.create(
            proyecto=proyecto,
            cliente=c2,
            importe_invertido=Decimal("10000.00"),
            estado="confirmada",
        )

        # --- Gastos: adquisición + reforma + operativos (confirmados) ---
        GastoProyecto.objects.create(
            proyecto=proyecto,
            fecha=fecha_compra,
            categoria="adquisicion",
            concepto="Compraventa inmueble",
            importe=Decimal("100000.00"),
            estado="confirmado",
            imputable_inversores=True,
        )
        GastoProyecto.objects.create(
            proyecto=proyecto,
            fecha=fecha_compra + timedelta(days=7),
            categoria="legales",
            concepto="Notaría y registro",
            importe=Decimal("2500.00"),
            estado="confirmado",
            imputable_inversores=True,
        )
        GastoProyecto.objects.create(
            proyecto=proyecto,
            fecha=fecha_compra + timedelta(days=15),
            categoria="reforma",
            concepto="Reforma (fase 1)",
            importe=Decimal("12000.00"),
            estado="confirmado",
            imputable_inversores=True,
        )
        GastoProyecto.objects.create(
            proyecto=proyecto,
            fecha=fecha_compra + timedelta(days=40),
            categoria="operativos",
            concepto="Suministros y mantenimiento",
            importe=Decimal("800.00"),
            estado="confirmado",
            imputable_inversores=True,
        )

        # --- Ingresos: venta estimada (aún no confirmada) ---
        IngresoProyecto.objects.create(
            proyecto=proyecto,
            fecha=hoy + timedelta(days=30),
            tipo="venta",
            concepto="Venta estimada",
            importe=Decimal("130000.00"),
            estado="estimado",
            imputable_inversores=True,
        )

        # Gastos de venta estimados
        GastoProyecto.objects.create(
            proyecto=proyecto,
            fecha=hoy + timedelta(days=30),
            categoria="venta",
            concepto="Inmobiliaria",
            importe=Decimal("3900.00"),
            estado="estimado",
            imputable_inversores=True,
        )

        # --- Auditoría rápida ---
        snap = _get_snapshot_comunicacion(proyecto)
        resultado = _resultado_desde_memoria(proyecto, snap if isinstance(snap, dict) else {})
        total_proj = (
            Participacion.objects.filter(proyecto=proyecto, estado="confirmada")
            .aggregate(total=Sum("importe_invertido"))
            .get("total")
            or Decimal("0")
        )
        total_proj_f = float(total_proj or 0)

        self.stdout.write(self.style.SUCCESS(f"Proyecto demo creado: id={proyecto.id} nombre={proyecto.nombre!r}"))
        self.stdout.write(
            f"ROI(memoria)={float(resultado.get('roi') or 0):.4f}% | "
            f"beneficio={float(resultado.get('beneficio_neto') or 0):.2f} | "
            f"base_adq={float(resultado.get('valor_adquisicion') or 0):.2f} | "
            f"transmision={float(resultado.get('valor_transmision') or 0):.2f}"
        )

        # Contextos por inversor (lo que usa la carta)
        for part in (p1, p2):
            ctx = _build_comunicacion_context(
                proyecto=proyecto,
                part=part,
                snapshot=snap if isinstance(snap, dict) else {},
                resultado_mem=resultado,
                total_proj=total_proj_f,
            )
            self.stdout.write(
                f"- Cliente={part.cliente_id} inv={part.importe_invertido} "
                f"participacion={ctx.get('participacion_pct')} "
                f"roi_proyecto={ctx.get('rentabilidad_estimada')} "
                f"roi_inv_bruta={ctx.get('rentabilidad_inversor_bruta')} "
                f"roi_inv_neta={ctx.get('rentabilidad_inversor_neta')} "
                f"plazo={ctx.get('plazo_meses')} {ctx.get('plazo_unidad')}"
            )
