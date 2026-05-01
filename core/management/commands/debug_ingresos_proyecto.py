from __future__ import annotations

from django.core.management.base import BaseCommand, CommandError


class Command(BaseCommand):
    help = "Imprime ingresos de un proyecto (sin PII) para depuración."
    requires_system_checks = []
    requires_migrations_checks = False

    def add_arguments(self, parser):
        parser.add_argument("--project-id", type=int, required=True, help="ID del proyecto.")

    def handle(self, *args, **opts):
        from core.models import Proyecto, IngresoProyecto  # local import

        project_id = int(opts["project_id"])
        proyecto = Proyecto.objects.filter(id=project_id).first()
        if not proyecto:
            raise CommandError("Proyecto no encontrado")

        qs = (
            IngresoProyecto.objects.filter(proyecto_id=project_id)
            .order_by("id")
            .values("id", "fecha", "tipo", "estado", "importe", "importe_real", "imputable_inversores")
        )

        self.stdout.write(f"proyecto_id={project_id} estado={(getattr(proyecto, 'estado', '') or '').strip()}")
        self.stdout.write("id;fecha;tipo;estado;importe;importe_real;imputable_inversores")
        for row in qs:
            self.stdout.write(
                f"{row.get('id')};{row.get('fecha')};{row.get('tipo')};{row.get('estado')};"
                f"{row.get('importe')};{row.get('importe_real')};{1 if row.get('imputable_inversores') else 0}"
            )

