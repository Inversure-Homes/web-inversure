from __future__ import annotations

from pathlib import Path
from typing import Any

from django.contrib.auth import get_user_model
from django.core.management.base import BaseCommand, CommandError

from accounts.models import UserAccess
from core.services.inversure_metric_audit import (
    SEVERITY_LEVELS,
    InversureMetricAuditService,
    render_csv_report,
    render_markdown_report,
)


class Command(BaseCommand):
    help = "Audita métricas financieras de Inversure de forma independiente y en solo lectura."
    requires_system_checks = []
    requires_migrations_checks = False

    def add_arguments(self, parser) -> None:
        parser.add_argument("--project-id", type=int, default=None, help="Auditar un único proyecto por id.")
        parser.add_argument("--limit", type=int, default=0, help="Limitar el número de proyectos analizados.")
        parser.add_argument(
            "--output-dir",
            type=Path,
            default=None,
            help="Directorio donde escribir los reportes CSV y Markdown.",
        )
        parser.add_argument(
            "--format",
            dest="formats",
            action="append",
            choices=("csv", "markdown"),
            help="Formato de salida a generar. Puede repetirse.",
        )
        parser.add_argument(
            "--fail-on-severity",
            choices=SEVERITY_LEVELS,
            default="error",
            help="Falla si la severidad máxima alcanza este umbral.",
        )

    def handle(self, *args: Any, **options: Any) -> None:
        viewer_user = self._resolve_viewer_user()
        service = InversureMetricAuditService(viewer_user=viewer_user)
        report = service.audit(
            project_id=options.get("project_id"),
            limit=options.get("limit"),
        )
        self.last_report = report  # útil para tests sin depender de stdout

        output_dir = options.get("output_dir")
        formats = list(options.get("formats") or ("csv", "markdown"))
        written_files: list[Path] = []
        if output_dir:
            output_path = Path(output_dir)
            output_path.mkdir(parents=True, exist_ok=True)
            if "csv" in formats:
                csv_path = output_path / "audit_inversure_metricas.csv"
                csv_path.write_text(render_csv_report(report["rows"]), encoding="utf-8")
                written_files.append(csv_path)
            if "markdown" in formats:
                markdown_path = output_path / "audit_inversure_metricas.md"
                markdown_path.write_text(render_markdown_report(report), encoding="utf-8")
                written_files.append(markdown_path)

        summary = report.get("summary", {})
        max_severity = str(summary.get("max_severity") or "info")
        row_count = int(summary.get("row_count") or 0)
        project_count = int(report.get("project_count") or 0)

        message = (
            f"Auditoría Inversure completada: {project_count} proyectos, "
            f"{row_count} filas, severidad máxima {max_severity}."
        )
        if written_files:
            message += " Archivos: " + ", ".join(str(path) for path in written_files)
        self.stdout.write(self.style.SUCCESS(message))

        if self._severity_reaches_threshold(max_severity, options["fail_on_severity"]):
            raise CommandError(
                f"Severidad máxima {max_severity} alcanzó el umbral {options['fail_on_severity']}."
            )

    def _resolve_viewer_user(self):
        user_model = get_user_model()
        allowed_roles = {
            UserAccess.ROLE_ADMIN,
            UserAccess.ROLE_DIRECCION,
            UserAccess.ROLE_COMERCIAL,
            UserAccess.ROLE_MARKETING,
            UserAccess.ROLE_MODERATORS,
        }
        user = (
            user_model.objects.filter(is_active=True, user_access__role__in=allowed_roles)
            .select_related("user_access")
            .order_by("id")
            .first()
        )
        if user is None:
            user = user_model.objects.filter(is_active=True, is_superuser=True).order_by("id").first()
        if user is None:
            user = user_model.objects.filter(is_active=True).select_related("user_access").order_by("id").first()
        if user is None:
            raise CommandError("No se encontró ningún usuario para ejecutar la auditoría.")
        return user

    def _severity_reaches_threshold(self, max_severity: str, threshold: str) -> bool:
        try:
            return SEVERITY_LEVELS.index(max_severity) >= SEVERITY_LEVELS.index(threshold)
        except ValueError:
            return False
