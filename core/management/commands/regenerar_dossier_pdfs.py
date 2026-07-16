from __future__ import annotations

import base64
import os
from dataclasses import dataclass

from django.conf import settings
from django.contrib.staticfiles import finders
from django.core.files.base import ContentFile
from django.core.management.base import BaseCommand
from django.http import QueryDict
from django.templatetags.static import static
from django.utils import timezone
from django.utils.text import slugify


@dataclass
class _Result:
    proyecto_id: int
    created: bool
    error: str | None = None


def _static_data_uri(static_path: str) -> str:
    try:
        abs_path = finders.find(static_path)
        if not abs_path or not os.path.exists(abs_path):
            return ""
        with open(abs_path, "rb") as f:
            data = base64.b64encode(f.read()).decode("ascii")
        low = (static_path or "").lower()
        mime = "image/jpeg" if low.endswith((".jpg", ".jpeg")) else "image/png"
        return f"data:{mime};base64,{data}"
    except Exception:
        return ""


class _FakeRequest:
    def __init__(self, post: QueryDict, base_url: str):
        self.POST = post
        self._base_url = (base_url or "").rstrip("/")

    def build_absolute_uri(self, location: str = "/") -> str:
        loc = (location or "/").strip()
        if loc.startswith(("http://", "https://")):
            return loc
        if not loc.startswith("/"):
            loc = "/" + loc
        return f"{self._base_url}{loc}" if self._base_url else loc


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
            "--deprecate-old",
            action="store_true",
            help="Marcar como obsoletos los PDFs de presentación anteriores del proyecto (no los borra).",
        )
        parser.add_argument(
            "--estilo",
            type=str,
            default="coin",
            help="Estilo de la plantilla de presentación (coin, etc.).",
        )

    def handle(self, *args, **opts):
        from core.models import DocumentoProyecto, Proyecto  # local import
        from core.views import (  # type: ignore
            SafeAccessDict,
            _build_presentacion_context,
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
        deprecate_old = bool(opts.get("deprecate_old"))
        estilo_default = (opts.get("estilo") or "coin").strip().lower()

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

        hero_data_uri = _static_data_uri("landing/assets/hero_investor.jpg")
        base_url = getattr(settings, "WAGTAILADMIN_BASE_URL", "").strip()

        for proyecto in qs.iterator():
            try:
                if only_if_exists:
                    has_dossier = DocumentoProyecto.objects.filter(
                        proyecto=proyecto,
                        categoria="presentacion",
                        archivo__iendswith=".pdf",
                    ).exists()
                    if not has_dossier:
                        skipped += 1
                        results.append(_Result(proyecto_id=proyecto.id, created=False))
                        continue

                # Si existe payload "difusion" guardado, regenerar usando exactamente la misma selección/formato/anexos.
                extra = proyecto.extra if isinstance(proyecto.extra, dict) else {}
                payload = extra.get("difusion") if isinstance(extra.get("difusion"), dict) else None
                pdf_bytes = None
                anexos_docs = []
                estilo = estilo_default
                slug = None
                titulo = None

                if payload:
                    post = QueryDict(mutable=True)
                    post["difusion.estilo"] = str(payload.get("estilo") or estilo_default)
                    post["difusion.titulo"] = str(payload.get("titulo") or proyecto.nombre or "Proyecto")
                    post["difusion.descripcion"] = str(payload.get("descripcion") or "")
                    post["difusion.ubicacion"] = str(payload.get("ubicacion") or "")
                    if payload.get("rentabilidad") not in (None, ""):
                        post["difusion.rentabilidad"] = str(payload.get("rentabilidad"))
                    if payload.get("plazo_meses") not in (None, ""):
                        post["difusion.plazo_meses"] = str(payload.get("plazo_meses"))
                    if payload.get("acceso_minimo") not in (None, ""):
                        post["difusion.acceso_minimo"] = str(payload.get("acceso_minimo"))
                    if payload.get("anio") not in (None, ""):
                        post["difusion.anio"] = str(payload.get("anio"))
                    if payload.get("foto_id") not in (None, ""):
                        post["difusion.foto_id"] = str(payload.get("foto_id"))
                    if payload.get("mapa_id") not in (None, ""):
                        post["difusion.mapa_id"] = str(payload.get("mapa_id"))
                    if payload.get("dossier_id") not in (None, ""):
                        post["difusion.dossier_id"] = str(payload.get("dossier_id"))

                    formatos = payload.get("formatos") if isinstance(payload.get("formatos"), dict) else {}
                    post["difusion.formatos.pdf"] = "on" if formatos.get("pdf", True) else ""
                    post["gen_pdf"] = "on"
                    if formatos.get("feed"):
                        post["difusion.formatos.feed"] = "on"
                    if formatos.get("story"):
                        post["difusion.formatos.story"] = "on"

                    anexos = payload.get("anexos") if isinstance(payload.get("anexos"), dict) else {}
                    for doc_id, enabled in anexos.items():
                        if enabled:
                            post[f"difusion.anexos.{doc_id}"] = "on"

                    request = _FakeRequest(post, base_url=base_url)
                    ctx_payload = _build_presentacion_context(request, proyecto)
                    pdf_context = dict(ctx_payload["context"])
                    pdf_context["formato"] = "pdf"
                    if hero_data_uri:
                        for k in ("foto_url", "descripcion_foto_url"):
                            v = str(pdf_context.get(k) or "")
                            if v.endswith(static("landing/assets/hero_investor.jpg")):
                                pdf_context[k] = hero_data_uri

                    pdf_bytes = _build_presentacion_pdf(request, pdf_context)
                    anexos_docs = list(ctx_payload.get("anexos_docs") or [])
                    if pdf_bytes:
                        pdf_bytes = _merge_pdf_with_documentos(pdf_bytes, anexos_docs, request=request) or pdf_bytes
                    estilo = str(ctx_payload.get("estilo") or estilo_default)
                    slug = str(ctx_payload.get("slug") or "") or None
                    titulo = str(ctx_payload.get("titulo") or "") or None

                if not pdf_bytes:
                    # Fallback genérico (sin payload guardado).
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
                    if not foto_url and hero_data_uri:
                        foto_url = hero_data_uri

                    anexos_docs = list(
                        DocumentoProyecto.objects.filter(
                            proyecto=proyecto,
                            usar_dossier=True,
                        )
                        .exclude(categoria="presentacion")
                        .order_by("-creado", "-id")
                    )

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

                    pdf_bytes = _build_presentacion_pdf(None, context)
                    if pdf_bytes:
                        pdf_bytes = _merge_pdf_with_documentos(pdf_bytes, anexos_docs, request=None) or pdf_bytes

                if not pdf_bytes:
                    errored += 1
                    results.append(_Result(proyecto_id=proyecto.id, created=False, error="No se pudo generar PDF"))
                    continue

                if not apply:
                    results.append(_Result(proyecto_id=proyecto.id, created=False))
                    continue

                if deprecate_old:
                    try:
                        prev_qs = DocumentoProyecto.objects.filter(
                            proyecto=proyecto,
                            categoria="presentacion",
                            archivo__iendswith=".pdf",
                        ).order_by("-creado", "-id")
                        prev = list(prev_qs)
                        to_update = []
                        for doc in prev:
                            t = (doc.titulo or "").strip()
                            if not t:
                                continue
                            if t.startswith("OBSOLETO ·"):
                                continue
                            doc.titulo = f"OBSOLETO · {t}"
                            to_update.append(doc)
                        if to_update:
                            DocumentoProyecto.objects.bulk_update(to_update, ["titulo"])
                    except Exception:
                        pass

                stamp = timezone.now().strftime("%Y%m%d_%H%M%S")
                slug_val = slug or f"proyecto_{proyecto.id}"
                filename = f"presentacion_{slug_val}_{estilo}_regen_{stamp}.pdf"
                titulo_val = titulo or (proyecto.nombre or f"Proyecto {proyecto.id}")
                DocumentoProyecto.objects.create(
                    proyecto=proyecto,
                    tipo="presentacion",
                    categoria="presentacion",
                    titulo=f"Dossier · {titulo_val} (regenerado {today})",
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
