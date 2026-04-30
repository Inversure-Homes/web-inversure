from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Any

from django.core.management.base import BaseCommand
from django.core.files.base import ContentFile
from django.utils import timezone


@dataclass
class _Result:
    proyecto_id: int
    created: bool
    error: str | None = None


class Command(BaseCommand):
    help = "Regenera PDFs guardados tipo 'Dossier' (DocumentoProyecto.categoria='presentacion') con cálculos actuales."
    requires_system_checks = []
    requires_migrations_checks = False

    def add_arguments(self, parser):
        parser.add_argument("--ids", nargs="*", type=int, default=None, help="IDs de proyecto a regenerar.")
        parser.add_argument("--limit", type=int, default=0, help="Limitar número de proyectos.")
        parser.add_argument(
            "--only-if-exists",
            action="store_true",
            help="Solo regenerar si el proyecto ya tiene algún Dossier guardado.",
        )
        parser.add_argument(
            "--apply",
            action="store_true",
            help="Crear nuevos DocumentoProyecto. Si no, solo imprime qué haría (dry-run).",
        )
        parser.add_argument(
            "--estilo",
            type=str,
            default="coin",
            help="Estilo de la plantilla de presentación (coin, etc.).",
        )

    def handle(self, *args, **opts):
        from django.utils.text import slugify

        from core.models import DocumentoProyecto, Proyecto  # local import
        from core.views import (  # type: ignore
            SafeAccessDict,
            _build_presentacion_pdf,
            _catastro_wms_url_from_refcat,
            _documento_url,
            _get_snapshot_comunicacion,
            _logo_data_uri,
            _merge_pdf_with_documentos,
            _resultado_desde_memoria,
            _safe_float,
        )

        ids = opts.get("ids") or None
        limit = int(opts.get("limit") or 0)
        only_if_exists = bool(opts.get("only_if_exists"))
        apply = bool(opts.get("apply"))
        estilo = (opts.get("estilo") or "coin").strip().lower()

        qs = Proyecto.objects.all().order_by("id")
        if ids:
            qs = qs.filter(id__in=ids)
        if limit > 0:
            qs = qs[:limit]

        today = timezone.now().date().isoformat()
        results: list[_Result] = []
        created = 0
        skipped = 0
        errored = 0

        for proyecto in qs.iterator():
            try:
                if only_if_exists:
                    has_dossier = DocumentoProyecto.objects.filter(
                        proyecto=proyecto,
                        categoria="presentacion",
                        titulo__startswith="Dossier ·",
                        archivo__iendswith=".pdf",
                    ).exists()
                    if not has_dossier:
                        skipped += 1
                        results.append(_Result(proyecto_id=proyecto.id, created=False))
                        continue

                snapshot = _get_snapshot_comunicacion(proyecto)
                inmueble_raw = snapshot.get("inmueble") if isinstance(snapshot.get("inmueble"), dict) else {}
                inmueble = SafeAccessDict(inmueble_raw if isinstance(inmueble_raw, dict) else {})
                inmueble["dormitorios"] = (
                    inmueble.get("dormitorios")
                    or inmueble.get("habitaciones")
                    or inmueble.get("num_dormitorios")
                )
                inmueble["banos"] = (
                    inmueble.get("banos")
                    or inmueble.get("baños")
                    or inmueble.get("num_banos")
                    or inmueble.get("num_baños")
                )

                resultado = _resultado_desde_memoria(proyecto, snapshot if isinstance(snapshot, dict) else {})

                titulo = (getattr(proyecto, "nombre", "") or "").strip() or f"Proyecto {proyecto.id}"
                slug = slugify(titulo) or f"proyecto_{proyecto.id}"

                # Foto: preferir principal / primera fotografía.
                foto_doc = (
                    DocumentoProyecto.objects.filter(
                        proyecto=proyecto,
                        categoria="fotografias",
                        usar_pdf=True,
                    )
                    .order_by("-creado", "-id")
                    .first()
                )
                if not foto_doc:
                    foto_doc = (
                        DocumentoProyecto.objects.filter(
                            proyecto=proyecto,
                            categoria="fotografias",
                            es_principal=True,
                        )
                        .order_by("-creado", "-id")
                        .first()
                    )
                if not foto_doc:
                    foto_doc = (
                        DocumentoProyecto.objects.filter(
                            proyecto=proyecto,
                            categoria="fotografias",
                        )
                        .order_by("-es_principal", "-creado", "-id")
                        .first()
                    )
                foto_url = _documento_url(None, foto_doc) if foto_doc else ""

                # Anexos: documentos marcados para dossier (excepto presentaciones).
                anexos_docs = list(
                    DocumentoProyecto.objects.filter(
                        proyecto=proyecto,
                        usar_dossier=True,
                    )
                    .exclude(categoria="presentacion")
                    .order_by("-creado", "-id")
                )

                # Mapa: WMS Catastro si hay ref catastral.
                ref_catastral = (
                    inmueble.get("ref_catastral")
                    or inmueble.get("referencia_catastral")
                    or getattr(proyecto, "ref_catastral", None)
                    or getattr(proyecto, "referencia_catastral", None)
                    or ""
                )
                mapa_url = _catastro_wms_url_from_refcat(str(ref_catastral or "")) if ref_catastral else ""

                roi_val = _safe_float(resultado.get("roi"), 0.0)
                if roi_val >= 15:
                    semaforo_estado = "verde"
                    semaforo_label = "Operación sólida"
                elif roi_val >= 10:
                    semaforo_estado = "amarillo"
                    semaforo_label = "Operación viable"
                else:
                    semaforo_estado = "rojo"
                    semaforo_label = "Revisar operación"
                roi_bar = max(0.0, min(roi_val, 30.0)) / 30.0 * 100.0

                context = {
                    "proyecto": proyecto,
                    "titulo": titulo,
                    "descripcion": "",
                    "ubicacion": "",
                    "rentabilidad": resultado.get("roi"),
                    "plazo_meses": None,
                    "acceso_minimo": None,
                    "anio": timezone.now().year,
                    "estilo": estilo,
                    "formato": "pdf",
                    "foto_url": foto_url,
                    "descripcion_foto_url": foto_url,
                    "logo_data_uri": _logo_data_uri("core/logo_inversure_blanco.png"),
                    "inmueble": inmueble,
                    "resultado": resultado,
                    "mapa_url": mapa_url,
                    "dossier_url": mapa_url,
                    "fotos_urls": [foto_url] if foto_url else [],
                    "semaforo_estado": semaforo_estado,
                    "semaforo_label": semaforo_label,
                    "roi_bar": roi_bar,
                }

                if not apply:
                    results.append(_Result(proyecto_id=proyecto.id, created=False))
                    continue

                pdf_bytes = _build_presentacion_pdf(None, context)
                if not pdf_bytes:
                    errored += 1
                    results.append(_Result(proyecto_id=proyecto.id, created=False, error="No se pudo generar PDF"))
                    continue

                pdf_bytes = _merge_pdf_with_documentos(pdf_bytes, anexos_docs, request=None) or pdf_bytes

                stamp = timezone.now().strftime("%Y%m%d_%H%M%S")
                filename = f"presentacion_{slug}_{estilo}_regen_{stamp}.pdf"
                DocumentoProyecto.objects.create(
                    proyecto=proyecto,
                    tipo="presentacion",
                    categoria="presentacion",
                    titulo=f"Dossier · {titulo} (regenerado {today})",
                    archivo=ContentFile(pdf_bytes, name=filename),
                )
                created += 1
                results.append(_Result(proyecto_id=proyecto.id, created=True))
            except Exception as e:
                errored += 1
                results.append(_Result(proyecto_id=proyecto.id, created=False, error=str(e)))

        mode = "APPLY" if apply else "DRY-RUN"
        self.stdout.write(f"{mode}: created={created} skipped={skipped} errored={errored}")
        for r in results:
            if r.error:
                self.stdout.write(f"{r.proyecto_id};ERROR;{r.error}")
            else:
                self.stdout.write(f"{r.proyecto_id};{'CREATED' if r.created else 'OK'};")

