from __future__ import annotations

import logging

from django.shortcuts import render, get_object_or_404, redirect
from django.contrib import messages
from django.http import JsonResponse, HttpResponse
from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.csrf import ensure_csrf_cookie
from django.urls import reverse
from django.utils.http import urlencode
from django.db import transaction
from django.db.models import Sum, Count, Max, Prefetch, Min, OuterRef, Subquery
from django.core.paginator import Paginator
from django.utils import timezone
from django.conf import settings
from django.core.mail import send_mail, EmailMultiAlternatives
from django.core.files.base import ContentFile
from django.template.loader import render_to_string
from django.templatetags.static import static
from django.utils.safestring import mark_safe
from django.contrib.staticfiles import finders
from django.utils.text import slugify

from copy import deepcopy
from types import SimpleNamespace

import json
import os
import shutil
import boto3
import base64
import mimetypes
from decimal import Decimal
from datetime import date, datetime


from .models import Estudio, Proyecto
from .models import EstudioSnapshot, ProyectoSnapshot
from .models import GastoProyecto, IngresoProyecto, ChecklistItem
from .models import Cliente, Participacion, InversorPerfil, SolicitudParticipacion, ComunicacionInversor, DocumentoProyecto, DocumentoInversor, FacturaGasto
from accounts.utils import is_admin_user, is_comercial_user, is_marketing_user, resolve_permissions, use_custom_permissions

# --- SafeAccessDict helper and _safe_template_obj ---
class SafeAccessDict(dict):
    """Dict seguro para plantillas Django: nunca lanza KeyError y permite acceso por atributo."""

    def __getitem__(self, key):
        return dict.get(self, key, "")

    def __getattr__(self, item):
        # permite `proyecto.campo` en plantillas
        return dict.get(self, item, "")

    def get(self, key, default=""):
        return dict.get(self, key, default)


def _s3_presigned_url(key: str, expires_seconds: int = 300) -> str:
    if not key:
        return ""
    bucket = getattr(settings, "AWS_STORAGE_BUCKET_NAME", None)
    access_key = getattr(settings, "AWS_ACCESS_KEY_ID", None)
    secret_key = getattr(settings, "AWS_SECRET_ACCESS_KEY", None)
    region = getattr(settings, "AWS_S3_REGION_NAME", None)
    if not bucket or not access_key or not secret_key:
        return ""
    try:
        client = boto3.client(
            "s3",
            region_name=region,
            aws_access_key_id=access_key,
            aws_secret_access_key=secret_key,
        )
        return client.generate_presigned_url(
            "get_object",
            Params={"Bucket": bucket, "Key": key},
            ExpiresIn=expires_seconds,
        )
    except Exception:
        return ""



def _safe_template_obj(obj):
    """Convierte dicts anidados en SafeAccessDict para evitar VariableDoesNotExist en plantillas."""
    if isinstance(obj, SafeAccessDict):
        return obj
    if isinstance(obj, dict):
        return SafeAccessDict({k: _safe_template_obj(v) for k, v in obj.items()})
    if isinstance(obj, (list, tuple)):
        return [_safe_template_obj(v) for v in obj]
    return obj


def _notificar_inversores_habilitado(proyecto: Proyecto, snapshot: dict | None = None) -> bool:
    try:
        extra = getattr(proyecto, "extra", None)
        if isinstance(extra, dict) and "notificar_inversores" in extra:
            return bool(extra.get("notificar_inversores"))
    except Exception:
        pass
    try:
        if isinstance(snapshot, dict):
            sec = snapshot.get("proyecto") if isinstance(snapshot.get("proyecto"), dict) else {}
            if "notificar_inversores" in sec:
                return bool(sec.get("notificar_inversores"))
    except Exception:
        pass
    return True


def _send_inversor_email(request, perfil: InversorPerfil, titulo: str, mensaje: str, attachments=None) -> bool:
    to_email = getattr(perfil.cliente, "email", "") or ""
    if not to_email:
        return False
    from_email = getattr(settings, "DEFAULT_FROM_EMAIL", "") or getattr(settings, "EMAIL_HOST_USER", "") or ""
    portal_url = ""
    logo_url = ""
    web_url = "https://inversurehomes.es"
    instagram_url = "https://www.instagram.com/inversure_homes/"
    facebook_url = "https://www.facebook.com/profile.php?id=61570884605730"
    linkedin_url = "https://www.linkedin.com/company/106364434"
    instagram_icon_url = ""
    facebook_icon_url = ""
    linkedin_icon_url = ""
    try:
        if request is not None:
            portal_url = request.build_absolute_uri(reverse("core:inversor_portal", args=[perfil.token]))
            logo_url = request.build_absolute_uri(static("core/logo_inversure.png"))
            instagram_icon_url = request.build_absolute_uri(static("core/logo_instagram.jpg.avif"))
            facebook_icon_url = request.build_absolute_uri(static("core/logo_facebook.jpg.avif"))
            linkedin_icon_url = request.build_absolute_uri(static("core/logo_linkedn.png"))
    except Exception:
        portal_url = ""
        logo_url = ""
    if portal_url:
        cuerpo = f"{mensaje}\n\nAcceso al portal del inversor:\n{portal_url}"
    else:
        cuerpo = mensaje
    firma_txt = (
        "\n\nMiguel Ángel Pérez Rodríguez\n"
        "comunicacion@inversurehomes.es\n\n"
        "Aviso legal: Este mensaje y los archivos adjuntos son confidenciales y están dirigidos exclusivamente a su destinatario. "
        "Si usted no es el destinatario, por favor notifíquelo al remitente y elimine el mensaje. Queda prohibida su reproducción "
        "o distribución sin autorización expresa.\n\n"
        "Protección de datos (RGPD): Los datos personales incluidos en esta comunicación se tratarán conforme al Reglamento (UE) 2016/679 "
        "(RGPD) y la normativa europea y nacional vigente en materia de protección de datos. Puede ejercer sus derechos de acceso, rectificación, "
        "supresión y otros dirigiéndose a mximenez@inversurehomes.es."
    )
    cuerpo = f"{cuerpo}{firma_txt}"
    logo_html = f'<img src="{logo_url}" alt="Inversure" style="height:40px;">' if logo_url else "<strong>Inversure</strong>"
    portal_html = (
        f'<p style="margin:12px 0 0;">Acceso al portal del inversor: '
        f'<a href="{portal_url}" style="color:#0b3a67;">{portal_url}</a></p>'
        if portal_url
        else ""
    )
    if instagram_icon_url or facebook_icon_url or linkedin_icon_url:
        social_html = '<div style="margin-top:12px;display:flex;gap:12px;align-items:center;">'
        if instagram_icon_url:
            social_html += (
                f'<a href="{instagram_url}" style="display:inline-block;"><img src="{instagram_icon_url}" alt="Instagram" '
                f'style="height:20px;width:auto;"></a>'
            )
        if facebook_icon_url:
            social_html += (
                f'<a href="{facebook_url}" style="display:inline-block;"><img src="{facebook_icon_url}" alt="Facebook" '
                f'style="height:20px;width:auto;"></a>'
            )
        if linkedin_icon_url:
            social_html += (
                f'<a href="{linkedin_url}" style="display:inline-block;"><img src="{linkedin_icon_url}" alt="LinkedIn" '
                f'style="height:20px;width:auto;"></a>'
            )
        social_html += "</div>"
    else:
        social_html = (
            f'<div style="margin-top:12px;display:flex;gap:12px;align-items:center;">'
            f'<a href="{instagram_url}" style="text-decoration:none;color:#0b3a67;">Instagram</a>'
            f'<a href="{facebook_url}" style="text-decoration:none;color:#0b3a67;">Facebook</a>'
            f'<a href="{linkedin_url}" style="text-decoration:none;color:#0b3a67;">LinkedIn</a>'
            f'<a href="{web_url}" style="text-decoration:none;color:#0b3a67;">Web</a>'
            f'</div>'
        )

    mensaje_html = (mensaje or "").replace("**INVERSURE**", "<strong>INVERSURE</strong>")
    html_message = f"""
    <div style="font-family:Arial, sans-serif; color:#0f172a; line-height:1.5;">
      <p>{mensaje_html}</p>
      {portal_html}
      <hr style="border:none;border-top:1px solid #e2e8f0;margin:20px 0;">
      <div style="display:flex;align-items:center;gap:14px;">
        {logo_html}
        <div>
          <div style="font-weight:600;">Miguel Ángel Pérez Rodríguez</div>
          <div><a href="mailto:comunicacion@inversurehomes.es" style="color:#0b3a67;">comunicacion@inversurehomes.es</a></div>
        </div>
      </div>
      {social_html}
      <p style="font-size:12px;color:#64748b;margin-top:16px;">
        Aviso legal: Este mensaje y los archivos adjuntos son confidenciales y están dirigidos exclusivamente a su destinatario.
        Si usted no es el destinatario, por favor notifíquelo al remitente y elimine el mensaje. Queda prohibida su reproducción
        o distribución sin autorización expresa.
      </p>
      <p style="font-size:12px;color:#64748b;">
        Protección de datos (RGPD): Los datos personales incluidos en esta comunicación se tratarán conforme al Reglamento (UE) 2016/679 (RGPD)
        y la normativa europea y nacional vigente en materia de protección de datos. Puede ejercer sus derechos de acceso, rectificación,
        supresión y otros dirigiéndose a mximenez@inversurehomes.es.
      </p>
    </div>
    """
    try:
        if attachments:
            email = EmailMultiAlternatives(
                titulo,
                cuerpo,
                from_email,
                [to_email],
            )
            email.attach_alternative(html_message, "text/html")
            for filename, content, mime in attachments:
                try:
                    email.attach(filename, content, mime)
                except Exception:
                    pass
            email.send(fail_silently=True)
        else:
            send_mail(
                titulo,
                cuerpo,
                from_email,
                [to_email],
                html_message=html_message,
                fail_silently=True,
            )
        return True
    except Exception:
        return False


def _crear_comunicacion(request, perfil: InversorPerfil, proyecto: Proyecto | None, titulo: str, mensaje: str, attachments=None):
    comunicacion = ComunicacionInversor.objects.create(
        inversor=perfil,
        proyecto=proyecto,
        titulo=titulo,
        mensaje=mensaje,
    )
    _send_inversor_email(request, perfil, titulo, mensaje, attachments=attachments)
    return comunicacion


def _estado_label(estado: str) -> str:
    return {
        "captacion": "Captación",
        "comprado": "Comprado",
        "comercializacion": "Comercialización",
        "reservado": "Reservado",
        "vendido": "Vendido",
        "cerrado": "Cerrado",
        "descartado": "Descartado",
    }.get((estado or "").lower(), estado or "")


def _comunicacion_templates() -> dict:
    return {
        "bienvenida": {
            "label": "Carta de bienvenida",
            "titulo": "Bienvenido a INVERSURE",
            "mensaje": (
                "Estimado/a {inversor_nombre},\n\n"
                "Bienvenido/a a **INVERSURE**. Somos una firma especializada en inversión inmobiliaria que "
                "combina análisis riguroso, control operativo y trazabilidad documental para proteger el "
                "capital y maximizar el retorno en un plazo mínimo de tiempo.\n\n"
                "Le damos acceso a su espacio virtual, donde podrá seguir el estado de sus inversiones, "
                "recibir comunicaciones y visualizar documentación (memoria económica, certificado de retención, "
                "contrato o cualquier comunicación).\n\n"
                "Le agradecemos la confianza depositada en nosotros y esperamos que la información recibida "
                "sea de su agrado. A continuación le facilitamos el enlace a su espacio.\n\n"
                "{portal_link}\n\n"
                "El equipo de INVERSURE"
            ),
        },
        "presentacion": {
            "label": "Presentación del proyecto",
            "titulo": "Presentación del proyecto {proyecto_nombre}",
            "mensaje": (
                "Estimado/a {inversor_nombre},\n\n"
                "Te presentamos el proyecto {proyecto_nombre}. A continuación encontrarás la descripción del inmueble y "
                "los principales datos de referencia.\n\n"
                "Recuerda que en tu espacio inversor podrás consultar la documentación asociada, la evolución económica "
                "y las comunicaciones oficiales del proyecto en todo momento.\n\n"
                "Descripción del inmueble:\n"
                "- Dirección: {inmueble_direccion}\n"
                "- Tipología: {inmueble_tipologia}\n"
                "- Superficie: {inmueble_superficie}\n"
                "- Estado: {inmueble_estado}\n"
                "- Situación: {inmueble_situacion}\n"
                "- Valor de referencia: {valor_referencia}\n\n"
                "Escenarios previstos:\n{escenarios}\n\n"
                "Desde tu portal podrás seguir la evolución económica y operativa en tiempo real.\n\n"
                "Atentamente,\nEquipo INVERSURE"
            ),
        },
        "estado": {
            "label": "Estado del proyecto",
            "titulo": "Actualización del estado del proyecto",
            "mensaje": (
                "Estimado/a {inversor_nombre},\n\n"
                "El proyecto {proyecto_nombre} ha pasado al estado: {proyecto_estado}.\n"
                "Estado del inmueble: {inmueble_estado}.\n\n"
                "Seguiremos informándote de cualquier avance relevante.\n\n"
                "Atentamente,\nEquipo INVERSURE"
            ),
        },
        "adquisicion": {
            "label": "Carta de adquisición",
            "titulo": "Adquisición completada",
            "mensaje": (
                "Estimado/a {inversor_nombre},\n\n"
                "Te informamos de que se ha completado la adquisición del proyecto {proyecto_nombre}.\n"
                "Fecha de adquisición: {fecha_compra}.\n"
                "Valor de adquisición: {valor_adquisicion}.\n\n"
                "Seguiremos informando de los siguientes hitos.\n\n"
                "Atentamente,\nEquipo INVERSURE"
            ),
        },
        "transmision": {
            "label": "Carta de transmisión",
            "titulo": "Transmisión completada",
            "mensaje": (
                "Estimado/a {inversor_nombre},\n\n"
                "Te informamos de que se ha completado la transmisión del proyecto {proyecto_nombre}.\n"
                "Fecha de transmisión: {fecha_transmision}.\n"
                "Valor de transmisión: {valor_transmision}.\n\n"
                "En breve recibirás el cierre con el detalle económico.\n\n"
                "Atentamente,\nEquipo INVERSURE"
            ),
        },
        "cierre": {
            "label": "Carta de cierre con beneficio",
            "titulo": "Cierre de la operación y beneficio",
            "mensaje": (
                "Estimado/a {inversor_nombre},\n\n"
                "El proyecto {proyecto_nombre} ha finalizado. Este es el resumen económico de tu inversión:\n"
                "Beneficio neto: {beneficio_neto_inversor}\n"
                "Retención (19%): {retencion}\n"
                "Neto a cobrar: {neto_cobrar}\n\n"
                "Gracias por tu confianza.\n\n"
                "Atentamente,\nEquipo INVERSURE"
            ),
        },
    }


class _SafeFormatDict(dict):
    def __missing__(self, key):
        return ""


def _render_comunicacion_template(key: str, context: dict) -> tuple[str, str] | tuple[None, None]:
    tmpl = _comunicacion_templates().get(key)
    if not tmpl:
        return None, None
    safe_ctx = _SafeFormatDict(context)
    titulo = (tmpl.get("titulo") or "").format_map(safe_ctx)
    mensaje = (tmpl.get("mensaje") or "").format_map(safe_ctx)
    return titulo, mensaje


def _get_snapshot_comunicacion(proyecto: Proyecto) -> dict:
    snap = getattr(proyecto, "snapshot_datos", None)
    if not isinstance(snap, dict):
        snap = {}
    if snap:
        base = dict(snap)
    else:
        base = {}

    extra = getattr(proyecto, "extra", None)
    overlay = {}
    if isinstance(extra, dict):
        ultimo = extra.get("ultimo_guardado")
        if isinstance(ultimo, dict) and isinstance(ultimo.get("payload"), dict):
            overlay = ultimo.get("payload") or {}
        elif isinstance(extra.get("payload"), dict):
            overlay = extra.get("payload") or {}

    if overlay:
        base = _deep_merge_dict(base, overlay) if base else dict(overlay)
    if base:
        return base

    osnap = getattr(proyecto, "origen_snapshot", None)
    if osnap is not None:
        datos = getattr(osnap, "datos", None)
        if isinstance(datos, dict) and datos:
            return _deep_merge_dict(dict(datos), overlay)
    oest = getattr(proyecto, "origen_estudio", None)
    if oest is not None:
        datos = getattr(oest, "datos", None)
        if isinstance(datos, dict) and datos:
            return _deep_merge_dict(dict(datos), overlay)
    return overlay or {}


def _calc_beneficio_inversor(
    part: Participacion,
    proyecto: Proyecto,
    snapshot: dict,
    resultado_mem: dict,
    total_proj: float,
) -> dict:
    beneficio_bruto = float(resultado_mem.get("beneficio_neto") or 0.0)
    inv_sec = snapshot.get("inversor") if isinstance(snapshot.get("inversor"), dict) else {}
    comision_pct = _safe_float(
        inv_sec.get("comision_inversure_pct")
        or inv_sec.get("inversure_comision_pct")
        or inv_sec.get("comision_pct")
        or 0.0,
        0.0,
    )
    comision_pct = max(0.0, min(100.0, comision_pct))
    comision_eur = beneficio_bruto * (comision_pct / 100.0) if beneficio_bruto else 0.0
    beneficio_neto_total = beneficio_bruto - comision_eur

    proj_extra = proyecto.extra if isinstance(proyecto.extra, dict) else {}
    proj_override = proj_extra.get("beneficio_operacion_override")
    if isinstance(proj_override, dict):
        override_bruto = proj_override.get("beneficio_bruto")
        override_comision = proj_override.get("comision_eur")
        override_neto = proj_override.get("beneficio_neto_total")
        if override_bruto not in (None, ""):
            beneficio_bruto = _safe_float(override_bruto, beneficio_bruto)
        if override_comision not in (None, ""):
            comision_eur = _safe_float(override_comision, comision_eur)
        if override_neto not in (None, ""):
            beneficio_neto_total = _safe_float(override_neto, beneficio_neto_total)
        elif override_bruto not in (None, "") or override_comision not in (None, ""):
            beneficio_neto_total = beneficio_bruto - comision_eur

    ratio = float(part.importe_invertido or 0) / total_proj if total_proj > 0 else 0.0
    beneficio_inversor = beneficio_neto_total * ratio
    override_val = float(part.beneficio_neto_override) if part.beneficio_neto_override is not None else None
    override_data = part.beneficio_override_data if isinstance(part.beneficio_override_data, dict) else {}
    if override_data.get("beneficio_inversor") not in (None, ""):
        beneficio_inversor = _safe_float(override_data.get("beneficio_inversor"), beneficio_inversor)
    elif override_val is not None:
        beneficio_inversor = override_val
    retencion = beneficio_inversor * 0.19
    if override_data.get("retencion") not in (None, ""):
        retencion = _safe_float(override_data.get("retencion"), retencion)
    neto_cobrar = beneficio_inversor - retencion
    if override_data.get("neto_cobrar") not in (None, ""):
        neto_cobrar = _safe_float(override_data.get("neto_cobrar"), neto_cobrar)
    return {
        "beneficio_neto_inversor": beneficio_inversor,
        "retencion": retencion,
        "neto_cobrar": neto_cobrar,
    }


def _build_comunicacion_context(
    proyecto: Proyecto,
    part: Participacion,
    snapshot: dict,
    resultado_mem: dict,
    total_proj: float,
) -> dict:
    inm = snapshot.get("inmueble") if isinstance(snapshot.get("inmueble"), dict) else {}
    if not isinstance(inm, dict):
        inm = {}
    sup = inm.get("superficie_m2") or inm.get("superficie")
    sup_txt = ""
    try:
        sup_val = float(sup)
        sup_txt = f"{_fmt_es_number(sup_val, 0)} m²"
    except Exception:
        sup_txt = str(sup or "")

    valor_ref_raw = inm.get("valor_referencia") or snapshot.get("valor_referencia") or ""
    try:
        valor_ref = _fmt_eur(float(valor_ref_raw))
    except Exception:
        valor_ref = str(valor_ref_raw or "")

    escenarios = snapshot.get("escenarios") or snapshot.get("escenario") or ""
    if isinstance(escenarios, (list, tuple)):
        escenarios = "\n".join(str(x) for x in escenarios)
    escenarios = str(escenarios or "")

    ctx = {
        "inversor_nombre": getattr(part.cliente, "nombre", "") or "",
        "proyecto_nombre": proyecto.nombre or "",
        "proyecto_estado": _estado_label(proyecto.estado),
        "inmueble_estado": inm.get("estado") or "",
        "inmueble_direccion": inm.get("direccion") or inm.get("direccion_completa") or "",
        "inmueble_tipologia": inm.get("tipologia") or "",
        "inmueble_superficie": sup_txt,
        "inmueble_situacion": inm.get("situacion") or "",
        "valor_referencia": valor_ref,
        "escenarios": escenarios,
        "fecha_hoy": timezone.now().date().strftime("%d/%m/%Y"),
        "fecha_compra": getattr(proyecto, "fecha_compra", None) or getattr(proyecto, "fecha", None),
        "fecha_transmision": getattr(proyecto, "fecha", None),
        "valor_adquisicion": _fmt_eur(float(resultado_mem.get("valor_adquisicion") or 0.0)),
        "valor_transmision": _fmt_eur(float(resultado_mem.get("valor_transmision") or 0.0)),
    }
    fecha_compra = ctx.get("fecha_compra")
    if isinstance(fecha_compra, date):
        ctx["fecha_compra"] = fecha_compra.strftime("%d/%m/%Y")
    elif fecha_compra is None:
        ctx["fecha_compra"] = ""
    fecha_trans = ctx.get("fecha_transmision")
    if isinstance(fecha_trans, date):
        ctx["fecha_transmision"] = fecha_trans.strftime("%d/%m/%Y")
    elif fecha_trans is None:
        ctx["fecha_transmision"] = ""

    benefit = _calc_beneficio_inversor(part, proyecto, snapshot, resultado_mem, total_proj)
    ctx["beneficio_neto_inversor"] = _fmt_eur(float(benefit.get("beneficio_neto_inversor") or 0.0))
    ctx["retencion"] = _fmt_eur(float(benefit.get("retencion") or 0.0))
    ctx["neto_cobrar"] = _fmt_eur(float(benefit.get("neto_cobrar") or 0.0))
    return ctx


def _build_carta_pdf_with_error(
    request,
    titulo: str,
    mensaje: str,
    perfil: InversorPerfil,
    proyecto: Proyecto | None,
) -> tuple[bytes | None, str | None]:
    try:
        logo_url = ""
        logo_data_uri = ""
        if request is not None:
            logo_url = request.build_absolute_uri(static("core/logo_inversure.png"))
        try:
            logo_path = finders.find("core/logo_inversure.png")
            if logo_path:
                with open(logo_path, "rb") as logo_file:
                    logo_bytes = logo_file.read()
                mime, _ = mimetypes.guess_type(logo_path)
                mime = mime or "image/png"
                logo_data_uri = f"data:{mime};base64,{base64.b64encode(logo_bytes).decode('ascii')}"
        except Exception:
            logo_data_uri = ""
        mensaje_html = mark_safe((mensaje or "").replace("**INVERSURE**", "<strong>INVERSURE</strong>"))
        html = render_to_string(
            "core/pdf_carta_inversor.html",
            {
                "titulo": titulo,
                "mensaje": mensaje,
                "mensaje_html": mensaje_html,
                "cliente": perfil.cliente,
                "proyecto": proyecto,
                "fecha": timezone.now().date(),
                "logo_url": logo_url,
                "logo_data_uri": logo_data_uri,
            },
        )
        from weasyprint import HTML  # defer import
        pdf = HTML(string=html, base_url=request.build_absolute_uri("/") if request else None).write_pdf()
        return pdf, None
    except Exception as e:
        return None, str(e)


def _build_carta_pdf(request, titulo: str, mensaje: str, perfil: InversorPerfil, proyecto: Proyecto | None) -> bytes | None:
    pdf, _ = _build_carta_pdf_with_error(request, titulo, mensaje, perfil, proyecto)
    return pdf


def _build_anexos_cover_pdf(request) -> bytes | None:
    try:
        logo_url = ""
        if request is not None:
            logo_url = request.build_absolute_uri(static("core/logo_inversure.png"))
        html = render_to_string(
            "core/pdf_carta_inversor.html",
            {
                "titulo": "Anexos del inmueble",
                "mensaje": "Documentacion complementaria adjunta a esta comunicacion.",
                "cliente": None,
                "proyecto": None,
                "fecha": timezone.now().date(),
                "logo_url": logo_url,
            },
        )
        from weasyprint import HTML  # defer import
        return HTML(string=html, base_url=request.build_absolute_uri("/") if request else None).write_pdf()
    except Exception:
        return None


def _merge_pdf_with_anexos(carta_pdf: bytes, anexos: list[DocumentoProyecto], request=None) -> bytes | None:
    if not carta_pdf:
        return None
    try:
        from io import BytesIO
        from pypdf import PdfReader, PdfWriter

        writer = PdfWriter()
        carta_reader = PdfReader(BytesIO(carta_pdf))
        for page in carta_reader.pages:
            writer.add_page(page)
        anexos_readers = []
        for doc in anexos:
            try:
                if not doc.archivo.name.lower().endswith(".pdf"):
                    continue
                with doc.archivo.open("rb") as f:
                    anexos_readers.append(PdfReader(f))
            except Exception:
                continue
        if anexos_readers:
            cover_pdf = _build_anexos_cover_pdf(request)
            if cover_pdf:
                cover_reader = PdfReader(BytesIO(cover_pdf))
                for page in cover_reader.pages:
                    writer.add_page(page)
            for reader in anexos_readers:
                for page in reader.pages:
                    writer.add_page(page)
        buffer = BytesIO()
        writer.write(buffer)
        return buffer.getvalue()
    except Exception:
        return carta_pdf


# =========================
# PRESENTACIONES DE PROYECTO
# =========================
def _logo_data_uri(logo_name: str = "core/logo_inversure.png") -> str:
    try:
        logo_path = finders.find(logo_name)
        if not logo_path:
            return ""
        with open(logo_path, "rb") as logo_file:
            logo_bytes = logo_file.read()
        mime, _ = mimetypes.guess_type(logo_path)
        mime = mime or "image/png"
        return f"data:{mime};base64,{base64.b64encode(logo_bytes).decode('ascii')}"
    except Exception:
        return ""


def _documento_url(request, documento: DocumentoProyecto) -> str:
    key = getattr(documento.archivo, "name", "") or ""
    signed = _s3_presigned_url(key)
    if signed:
        return signed
    try:
        if request:
            return request.build_absolute_uri(documento.archivo.url)
    except Exception:
        pass
    try:
        return documento.archivo.url
    except Exception:
        return ""


def _documento_image_url(request, documento: DocumentoProyecto) -> str:
    nombre = (documento.archivo.name or "").lower()
    if nombre.endswith(".pdf"):
        try:
            from io import BytesIO
            from pdf2image import convert_from_bytes
            poppler_path = getattr(settings, "POPPLER_PATH", "") or os.environ.get("POPPLER_PATH", "")
            if not poppler_path:
                pdftoppm_path = shutil.which("pdftoppm")
                if pdftoppm_path:
                    poppler_path = os.path.dirname(pdftoppm_path)
            with documento.archivo.open("rb") as f:
                pdf_bytes = f.read()
            convert_kwargs = {"first_page": 1, "last_page": 1, "dpi": 150}
            if poppler_path:
                convert_kwargs["poppler_path"] = poppler_path
            images = convert_from_bytes(pdf_bytes, **convert_kwargs)
            if not images:
                return ""
            buf = BytesIO()
            images[0].save(buf, format="PNG")
            data = base64.b64encode(buf.getvalue()).decode("ascii")
            return f"data:image/png;base64,{data}"
        except Exception:
            logging.getLogger(__name__).exception(
                "Fallo al convertir PDF a imagen (pdf2image) para documento %s",
                documento.id,
            )
        try:
            import fitz  # PyMuPDF
            from io import BytesIO

            with documento.archivo.open("rb") as f:
                pdf_bytes = f.read()
            doc = fitz.open(stream=pdf_bytes, filetype="pdf")
            if doc.page_count < 1:
                return ""
            page = doc.load_page(0)
            pix = page.get_pixmap(dpi=150)
            buf = BytesIO(pix.tobytes("png"))
            data = base64.b64encode(buf.getvalue()).decode("ascii")
            return f"data:image/png;base64,{data}"
        except Exception:
            logging.getLogger(__name__).exception(
                "Fallo al convertir PDF a imagen (pymupdf) para documento %s",
                documento.id,
            )
            return ""
    return _documento_url(request, documento)


def _documento_pdf_bytes(request, documento: DocumentoProyecto) -> bytes | None:
    nombre = (documento.archivo.name or "").lower()
    if nombre.endswith(".pdf"):
        try:
            with documento.archivo.open("rb") as f:
                return f.read()
        except Exception:
            return None
    mime, _ = mimetypes.guess_type(nombre)
    if not mime or not mime.startswith("image/"):
        return None
    img_url = _documento_url(request, documento)
    html = render_to_string(
        "core/pdf_anexo_documento.html",
        {
            "titulo": documento.titulo,
            "imagen_url": img_url,
            "logo_data_uri": _logo_data_uri(),
        },
    )
    from weasyprint import HTML  # defer import
    return HTML(string=html, base_url=request.build_absolute_uri("/") if request else None).write_pdf()


def _merge_pdf_with_documentos(base_pdf: bytes, anexos: list[DocumentoProyecto], request=None) -> bytes | None:
    if not base_pdf:
        return None
    try:
        from io import BytesIO
        from pypdf import PdfReader, PdfWriter

        writer = PdfWriter()
        base_reader = PdfReader(BytesIO(base_pdf))
        for page in base_reader.pages:
            writer.add_page(page)
        for doc in anexos:
            doc_pdf = _documento_pdf_bytes(request, doc)
            if not doc_pdf:
                continue
            reader = PdfReader(BytesIO(doc_pdf))
            for page in reader.pages:
                writer.add_page(page)
        buffer = BytesIO()
        writer.write(buffer)
        return buffer.getvalue()
    except Exception:
        return base_pdf


def _can_preview_facturas(user) -> bool:
    if not user or not getattr(user, "is_authenticated", False):
        return False
    if is_admin_user(user):
        return True
    if use_custom_permissions(user):
        perms = resolve_permissions(user)
        return bool(perms.get("can_facturas_preview"))
    return False


def _build_presentacion_html(request, context: dict) -> str:
    return render_to_string("core/pdf_presentacion_proyecto.html", context)


def _build_presentacion_pdf(request, context: dict) -> bytes | None:
    try:
        from weasyprint import HTML  # defer import
        html = _build_presentacion_html(request, context)
        return HTML(string=html, base_url=request.build_absolute_uri("/") if request else None).write_pdf()
    except Exception:
        logging.getLogger(__name__).exception("Fallo al generar PDF de presentacion")
        return None


def _build_presentacion_png(request, context: dict) -> bytes | None:
    try:
        from weasyprint import HTML  # defer import
        html = _build_presentacion_html(request, context)
        doc = HTML(string=html, base_url=request.build_absolute_uri("/") if request else None)
        if not hasattr(doc, "write_png"):
            logging.getLogger(__name__).warning("WeasyPrint no soporta write_png en este entorno")
            return None
        return doc.write_png()
    except Exception:
        logging.getLogger(__name__).exception("Fallo al generar PNG de presentacion")
        return None


# --- Helper para sanear datos para JSONField (Decimal, fechas, etc.) ---
def _sanitize_for_json(value):
    """Convierte objetos no serializables (Decimal, fechas) a tipos JSON-safe."""
    if isinstance(value, Decimal):
        # JSONField no acepta Decimal; convertimos a float
        return float(value)
    if isinstance(value, (datetime, date)):
        return value.isoformat()
    if isinstance(value, dict):
        return {k: _sanitize_for_json(v) for k, v in value.items()}
    if isinstance(value, (list, tuple)):
        return [_sanitize_for_json(v) for v in value]
    return value


def _parse_decimal(value):
    if value is None or value == "":
        return None
    if isinstance(value, Decimal):
        return value
    if isinstance(value, (int, float)):
        return Decimal(str(value))
    if isinstance(value, str):
        s = value.strip().replace("€", "").replace("%", "").strip()
        if not s:
            return None
        if "." in s and "," in s:
            s = s.replace(".", "").replace(",", ".")
        else:
            s = s.replace(",", ".")
        return Decimal(s)
    raise ValueError("decimal_invalido")


def _parse_date(value):
    if value is None or value == "":
        return None
    if isinstance(value, date):
        return value
    if isinstance(value, str):
        s = value.strip()
        if not s:
            return None
        return date.fromisoformat(s)
    raise ValueError("fecha_invalida")


def _deep_merge_dict(base: dict, overlay: dict) -> dict:
    """Merge recursivo: overlay pisa base; diccionarios se fusionan."""
    if not isinstance(base, dict):
        base = {}
    if not isinstance(overlay, dict):
        return base
    for k, v in overlay.items():
        if isinstance(v, dict) and isinstance(base.get(k), dict):
            base[k] = _deep_merge_dict(base.get(k, {}), v)
        else:
            base[k] = v
    return base


def _safe_float(v, default: float = 0.0) -> float:
    try:
        if v is None:
            return default
        # strings like "1.234,56" or "1,234.56" → normalize
        if isinstance(v, str):
            s = v.strip()
            # remove currency/percent symbols
            s = s.replace("€", "").replace("%", "").strip()
            # spanish thousands/decimal
            if "." in s and "," in s:
                # assume dot thousands, comma decimal
                s = s.replace(".", "").replace(",", ".")
            else:
                # otherwise, treat comma as decimal
                s = s.replace(",", ".")
            v = s
        return float(v)
    except (TypeError, ValueError):
        return default


def _resultado_desde_metricas(metricas: dict) -> dict:
    if not isinstance(metricas, dict):
        metricas = {}
    beneficio_neto = _safe_float(
        metricas.get("beneficio_neto") or metricas.get("beneficio") or 0.0,
        0.0,
    )
    roi = _safe_float(metricas.get("roi") or metricas.get("roi_neto") or 0.0, 0.0)
    valor_adq = _safe_float(
        metricas.get("valor_adquisicion_total")
        or metricas.get("valor_adquisicion")
        or metricas.get("inversion_total")
        or 0.0,
        0.0,
    )
    ratio_euro = _safe_float(
        metricas.get("ratio_euro") or (beneficio_neto / valor_adq if valor_adq else 0.0),
        0.0,
    )
    precio_min_venta = _safe_float(
        metricas.get("precio_minimo_venta")
        or metricas.get("precio_breakeven")
        or metricas.get("breakeven")
        or metricas.get("break_even")
        or 0.0,
        0.0,
    )
    colchon = _safe_float(
        metricas.get("colchon_seguridad")
        or metricas.get("colchon")
        or 0.0,
        0.0,
    )
    margen = _safe_float(
        metricas.get("margen_neto")
        or metricas.get("margen")
        or 0.0,
        0.0,
    )
    ajuste_precio_venta = _safe_float(metricas.get("ajuste_precio_venta") or 0.0, 0.0)
    ajuste_gastos = _safe_float(metricas.get("ajuste_gastos") or 0.0, 0.0)

    viable = roi >= 15 and beneficio_neto >= 30000
    ajustada = roi >= 15 and 0 < beneficio_neto < 30000

    return {
        "beneficio_neto": beneficio_neto,
        "roi": roi,
        "valor_adquisicion": valor_adq,
        "ratio_euro": ratio_euro,
        "precio_minimo_venta": precio_min_venta,
        "colchon_seguridad": colchon,
        "margen_neto": margen,
        "ajuste_precio_venta": ajuste_precio_venta,
        "ajuste_gastos": ajuste_gastos,
        "viable": viable,
        "ajustada": ajustada,
    }


def _checklist_defaults():
    return [
        ("compra", "Tramitación de escrituras · Recogida notaría/registro"),
        ("compra", "Tramitación de escrituras · Liquidación de impuestos"),
        ("compra", "Tramitación de escrituras · Tramitación de plusvalía"),
        ("post_compra", "Pagos · Impuestos"),
        ("post_compra", "Pagos · Deudas retenidas"),
        ("post_compra", "Pagos · Facturas"),
        ("post_compra", "Cambio suministros · Alarma"),
        ("post_compra", "Cambio suministros · Cerradura"),
        ("post_compra", "Cambio suministros · Luz"),
        ("post_compra", "Cambio suministros · Agua"),
        ("operacion", "Reforma · Solicitud de presupuestos"),
        ("operacion", "Reforma · Validación"),
        ("operacion", "Reforma · Control de ejecución"),
    ]


def _ensure_checklist_defaults(proyecto: Proyecto) -> None:
    existentes = set(
        ChecklistItem.objects.filter(proyecto=proyecto).values_list("fase", "titulo")
    )
    nuevos = [
        (fase, titulo)
        for fase, titulo in _checklist_defaults()
        if (fase, titulo) not in existentes
    ]
    if not nuevos:
        return
    ChecklistItem.objects.bulk_create(
        [
            ChecklistItem(
                proyecto=proyecto,
                fase=fase,
                titulo=titulo,
                estado="pendiente",
            )
            for fase, titulo in nuevos
        ]
    )


def _resultado_desde_memoria(proyecto: Proyecto, snapshot: dict) -> dict:
    gastos = list(GastoProyecto.objects.filter(proyecto=proyecto))
    ingresos = list(IngresoProyecto.objects.filter(proyecto=proyecto))

    def _sum_importes(items):
        total = Decimal("0")
        for item in items:
            if item is None:
                continue
            total += item
        return total

    ingresos_est = _sum_importes([i.importe for i in ingresos if i.estado == "estimado"])
    ingresos_real = _sum_importes([i.importe for i in ingresos if i.estado == "confirmado"])
    venta_est = _sum_importes(
        [i.importe for i in ingresos if i.estado == "estimado" and i.tipo == "venta"]
    )
    venta_real = _sum_importes(
        [i.importe for i in ingresos if i.estado == "confirmado" and i.tipo == "venta"]
    )
    gastos_est = _sum_importes([g.importe for g in gastos if g.estado == "estimado"])
    gastos_real = _sum_importes([g.importe for g in gastos if g.estado == "confirmado"])

    has_real = ingresos_real > 0 or gastos_real > 0
    ingresos_base = ingresos_real if ingresos_real > 0 else ingresos_est
    venta_base = venta_real if venta_real > 0 else venta_est
    gastos_venta_est = _sum_importes([g.importe for g in gastos if g.estado == "estimado" and g.categoria == "venta"])
    gastos_venta_real = _sum_importes([g.importe for g in gastos if g.estado == "confirmado" and g.categoria == "venta"])
    gastos_venta_base = gastos_venta_real if gastos_venta_real > 0 else gastos_venta_est
    gastos_base = gastos_real if gastos_real > 0 else gastos_est
    beneficio = ingresos_base - gastos_base

    cats_adq = {"adquisicion", "reforma", "seguridad", "operativos", "financieros", "legales", "otros"}
    gastos_adq_est = _sum_importes([g.importe for g in gastos if g.estado == "estimado" and g.categoria in cats_adq])
    gastos_adq_real = _sum_importes([g.importe for g in gastos if g.estado == "confirmado" and g.categoria in cats_adq])
    gastos_adq_base = gastos_adq_real if gastos_adq_real > 0 else gastos_adq_est

    snap_econ = snapshot.get("economico") if isinstance(snapshot.get("economico"), dict) else {}
    snap_kpis = snapshot.get("kpis") if isinstance(snapshot.get("kpis"), dict) else {}
    snap_met = snap_kpis.get("metricas") if isinstance(snap_kpis.get("metricas"), dict) else {}

    snap_valor_adq = _parse_decimal(
        snap_econ.get("valor_adquisicion_total")
        or snap_econ.get("valor_adquisicion")
        or snap_met.get("valor_adquisicion_total")
        or snap_met.get("valor_adquisicion")
        or ""
    )
    snap_valor_trans = _parse_decimal(
        snap_econ.get("valor_transmision")
        or snap_econ.get("precio_transmision")
        or snap_econ.get("valor_transmision_estimado")
        or snap_econ.get("precio_venta_estimado")
        or snap_econ.get("venta_estimada")
        or snap_met.get("valor_transmision")
        or snap_met.get("precio_transmision")
        or snap_met.get("valor_transmision_estimado")
        or ""
    )
    snap_beneficio = _parse_decimal(
        snap_econ.get("beneficio_bruto")
        or snap_econ.get("beneficio_neto")
        or snap_econ.get("beneficio")
        or snap_met.get("beneficio_bruto")
        or snap_met.get("beneficio_neto")
        or snap_met.get("beneficio")
        or ""
    )
    snap_gastos_venta = _sum_importes(
        [
            _parse_decimal(snap_econ.get("plusvalia")),
            _parse_decimal(snap_econ.get("inmobiliaria")),
            _parse_decimal(snap_econ.get("gestion_comercial")),
            _parse_decimal(snap_econ.get("gestion_administracion")),
        ]
    )

    base_precio = (
        proyecto.precio_compra_inmueble
        or proyecto.precio_propiedad
        or _parse_decimal(snap_econ.get("precio_propiedad") or snap_econ.get("precio_escritura") or "")
        or _parse_decimal(snap_met.get("precio_propiedad") or snap_met.get("precio_escritura") or "")
        or Decimal("0")
    )

    no_movimientos = ingresos_est == 0 and ingresos_real == 0 and gastos_est == 0 and gastos_real == 0

    if no_movimientos and snap_valor_adq is not None and snap_valor_adq > 0:
        valor_adquisicion = snap_valor_adq
    else:
        valor_adquisicion = base_precio + gastos_adq_base

    venta_snapshot = (
        snap_valor_trans
        or _parse_decimal(
            snap_econ.get("venta_estimada")
            or snap_econ.get("valor_transmision")
            or snap_met.get("venta_estimada")
            or snap_met.get("valor_transmision")
            or ""
        )
        or Decimal("0")
    )
    if venta_base > 0:
        valor_transmision = venta_base - gastos_venta_base
    else:
        valor_transmision = venta_snapshot

    if no_movimientos and gastos_venta_base == 0 and snap_gastos_venta > 0:
        gastos_venta_base = snap_gastos_venta

    if no_movimientos:
        if snap_beneficio is not None:
            beneficio = snap_beneficio
        elif valor_transmision > 0 or valor_adquisicion > 0:
            beneficio = valor_transmision - valor_adquisicion

    roi = float(beneficio / valor_adquisicion * 100) if valor_adquisicion > 0 else 0.0
    ratio_euro = float(beneficio / valor_adquisicion) if valor_adquisicion > 0 else 0.0
    margen_pct = float(beneficio / valor_transmision * 100) if valor_transmision > 0 else 0.0

    beneficio_objetivo = Decimal("30000")
    objetivo_roi = valor_adquisicion * Decimal("0.15")
    objetivo_beneficio = beneficio_objetivo if beneficio_objetivo > objetivo_roi else objetivo_roi
    min_valor_transmision = valor_adquisicion + objetivo_beneficio
    min_venta = min_valor_transmision + gastos_venta_base

    ajuste_precio_venta = float(max(min_valor_transmision - valor_transmision, Decimal("0"))) if valor_transmision > 0 else float(min_valor_transmision)

    costo_requerido_roi = valor_transmision / Decimal("1.15") if valor_transmision > 0 else Decimal("0")
    costo_requerido_benef = valor_transmision - beneficio_objetivo
    costo_requerido = min(costo_requerido_roi, costo_requerido_benef)
    if costo_requerido < 0:
        costo_requerido = Decimal("0")
    ajuste_gastos = float(max(valor_adquisicion - costo_requerido, Decimal("0"))) if valor_transmision > 0 else float(valor_adquisicion)

    colchon_seguridad = float(valor_transmision - valor_adquisicion - objetivo_beneficio) if valor_transmision > 0 else 0.0

    return {
        "beneficio_neto": float(beneficio),
        "roi": roi,
        "valor_adquisicion": float(valor_adquisicion),
        "valor_transmision": float(valor_transmision),
        "ratio_euro": ratio_euro,
        "precio_minimo_venta": float(min_venta),
        "colchon_seguridad": colchon_seguridad,
        "margen_neto": margen_pct,
        "ajuste_precio_venta": ajuste_precio_venta,
        "ajuste_gastos": ajuste_gastos,
        "gastos_real_total": float(gastos_real),
        "gastos_est_total": float(gastos_est),
        "origen_memoria": True,
        "base_memoria_real": bool(has_real),
    }


def _capital_objetivo_desde_memoria(proyecto: Proyecto, snapshot: dict | None = None) -> float:
    snap = snapshot if isinstance(snapshot, dict) else {}
    resultado = _resultado_desde_memoria(proyecto, snap)
    gastos_real = _safe_float(resultado.get("gastos_real_total"), 0.0)
    if gastos_real > 0:
        return gastos_real
    gastos_est = _safe_float(resultado.get("gastos_est_total"), 0.0)
    if gastos_est > 0:
        return gastos_est
    capital_objetivo = _safe_float(resultado.get("valor_adquisicion"), 0.0)
    if capital_objetivo <= 0:
        capital_objetivo = _safe_float(
            getattr(proyecto, "precio_compra_inmueble", None)
            or getattr(proyecto, "precio_propiedad", None)
            or 0.0,
            0.0,
        )
    return capital_objetivo


def _beneficio_estimado_real_memoria(proyecto: Proyecto) -> dict:
    gastos = list(GastoProyecto.objects.filter(proyecto=proyecto))
    ingresos = list(IngresoProyecto.objects.filter(proyecto=proyecto))

    def _sum_importes(items):
        total = Decimal("0")
        for item in items:
            if item is None:
                continue
            total += item
        return total

    def _importe_estimado(item):
        estimado = getattr(item, "importe_estimado", None)
        if estimado is not None:
            return estimado
        if getattr(item, "estado", "") == "estimado":
            return item.importe
        return Decimal("0")

    def _importe_real(item):
        if getattr(item, "estado", "") != "confirmado":
            return Decimal("0")
        real = getattr(item, "importe_real", None)
        return real if real is not None else item.importe

    ingresos_estimados = _sum_importes([_importe_estimado(i) for i in ingresos])
    ingresos_reales = _sum_importes([_importe_real(i) for i in ingresos])
    gastos_estimados = _sum_importes([_importe_estimado(g) for g in gastos])
    gastos_reales = _sum_importes([_importe_real(g) for g in gastos])

    return {
        "beneficio_estimado": float((ingresos_estimados - gastos_estimados) or 0),
        "beneficio_real": float((ingresos_reales - gastos_reales) or 0),
        "has_movimientos": bool(ingresos or gastos),
    }


def _fmt_es_number(x: float, decimals: int = 2) -> str:
    # 12,345.67 -> 12.345,67
    s = f"{x:,.{decimals}f}"
    s = s.replace(",", "X").replace(".", ",").replace("X", ".")
    return s


def _fmt_eur(x: float) -> str:
    return f"{_fmt_es_number(x, 2)} €"


def _fmt_pct(x: float) -> str:
    return f"{_fmt_es_number(x, 2)} %"


def _metricas_desde_estudio(estudio: Estudio) -> dict:
    d = estudio.datos or {}

    def _deep_get(*keys, default=None):
        containers = [
            d,
            d.get("inversor") if isinstance(d.get("inversor"), dict) else {},
            (d.get("snapshot") or {}).get("inversor") if isinstance(d.get("snapshot"), dict) else {},
            (d.get("kpis") or {}).get("metricas") if isinstance(d.get("kpis"), dict) else {},
            d.get("kpis") if isinstance(d.get("kpis"), dict) else {},
            d.get("economico") if isinstance(d.get("economico"), dict) else {},
            d.get("comite") if isinstance(d.get("comite"), dict) else {},
        ]
        for k in keys:
            for c in containers:
                if not isinstance(c, dict):
                    continue
                if k in c and c.get(k) not in (None, ""):
                    return c.get(k)
        return default

    valor_adquisicion = _safe_float(d.get("valor_adquisicion"), 0.0)

    # intentar localizar precio de venta/valor de transmisión
    precio_transmision = _safe_float(
        d.get("precio_transmision")
        or d.get("precio_venta_estimado")
        or d.get("valor_transmision")
        or d.get("valor_transmision_estimado"),
        0.0,
    )

    beneficio = _safe_float(d.get("beneficio"), precio_transmision - valor_adquisicion)

    roi = _safe_float(d.get("roi"), (beneficio / valor_adquisicion * 100.0) if valor_adquisicion else 0.0)

    media_valoraciones = _safe_float(d.get("media_valoraciones"), 0.0)

    metricas = {
        "valor_adquisicion": valor_adquisicion,
        "valor_adquisicion_total": valor_adquisicion,
        # aliases usados por plantillas antiguas
        "precio_adquisicion": valor_adquisicion,
        "precio_compra": valor_adquisicion,
        "precio_transmision": precio_transmision,
        "valor_transmision": precio_transmision,
        "beneficio": beneficio,
        "roi": roi,
        "media_valoraciones": media_valoraciones,
        # alias típicos por si la plantilla usa otros nombres
        "inversion_total": valor_adquisicion,
        "beneficio_neto": beneficio,
        "roi_neto": roi,
    }

    metricas_fmt = {
        "valor_adquisicion": _fmt_eur(valor_adquisicion),
        "valor_adquisicion_total": _fmt_eur(valor_adquisicion),
        # aliases
        "precio_adquisicion": _fmt_eur(valor_adquisicion),
        "precio_compra": _fmt_eur(valor_adquisicion),
        "precio_transmision": _fmt_eur(precio_transmision),
        "valor_transmision": _fmt_eur(precio_transmision),
        "beneficio": _fmt_eur(beneficio),
        "roi": _fmt_pct(roi),
        "media_valoraciones": _fmt_eur(media_valoraciones),
        # alias
        "inversion_total": _fmt_eur(valor_adquisicion),
        "beneficio_neto": _fmt_eur(beneficio),
        "roi_neto": _fmt_pct(roi),
    }

    # decisión simple (placeholder) para que la plantilla no quede vacía
    resultado = {
        "viable": True if (beneficio >= 0 and roi >= 0) else False,
        "mensaje": "Operación viable" if (beneficio >= 0 and roi >= 0) else "Operación no viable",
    }

    # --- Enriquecimiento automático con métricas de Comité/Inversor guardadas en `datos` ---
    # El simulador guarda muchos KPIs adicionales (breakeven, colchón, riesgo, etc.) dentro de `estudio.datos`.
    # Para que el PDF los pueda mostrar sin depender de campos del modelo, los añadimos aquí de forma defensiva.
    texto = {}

    def _is_percent_key(key: str) -> bool:
        k = (key or "").lower()
        return any(t in k for t in ["roi", "%", "pct", "porc", "porcentaje", "tasa"]) and not any(t in k for t in ["euros", "eur", "euro"])

    def _is_ratio_key(key: str) -> bool:
        k = (key or "").lower()
        return "ratio" in k or "multiplic" in k

    def _is_currency_key(key: str) -> bool:
        k = (key or "").lower()
        # Heurística: casi todo en el simulador es dinero salvo ratios/%.
        # Aun así, si el nombre sugiere % o ratio, no lo tratamos como €.
        if _is_percent_key(k) or _is_ratio_key(k):
            return False
        return True

    for k, v in d.items():
        # Guardar textos (para estado/situación, decisión, comentarios, etc.)
        if isinstance(v, str):
            sv = v.strip()
            if sv and k not in texto:
                texto[k] = sv

        # Añadir numéricos que no estén ya normalizados
        if k in metricas:
            continue
        fv = _safe_float(v, None)
        if fv is None:
            continue
        metricas[k] = fv

        # Formateo por heurística
        if _is_percent_key(k):
            metricas_fmt[k] = _fmt_pct(fv)
        elif _is_ratio_key(k):
            metricas_fmt[k] = _fmt_es_number(fv, 2)
        elif _is_currency_key(k):
            metricas_fmt[k] = _fmt_eur(fv)
        else:
            metricas_fmt[k] = _fmt_es_number(fv, 2)

    # Enriquecer con métricas anidadas (comite/inversor/economico/kpis) si no estaban en raíz
    nested_sections = [
        d.get("comite"),
        d.get("inversor"),
        d.get("economico"),
        d.get("kpis"),
        (d.get("kpis") or {}).get("metricas") if isinstance(d.get("kpis"), dict) else None,
        (d.get("snapshot") or {}).get("kpis") if isinstance(d.get("snapshot"), dict) else None,
        ((d.get("snapshot") or {}).get("kpis") or {}).get("metricas") if isinstance(d.get("snapshot"), dict) else None,
    ]
    for sec in nested_sections:
        if not isinstance(sec, dict):
            continue
        for k, v in sec.items():
            if k in metricas:
                continue
            fv = _safe_float(v, None)
            if fv is None:
                continue
            metricas[k] = fv
            if _is_percent_key(k):
                metricas_fmt[k] = _fmt_pct(fv)
            elif _is_ratio_key(k):
                metricas_fmt[k] = _fmt_es_number(fv, 2)
            elif _is_currency_key(k):
                metricas_fmt[k] = _fmt_eur(fv)
            else:
                metricas_fmt[k] = _fmt_es_number(fv, 2)

    # Algunos alias habituales (por si la plantilla usa nombres alternativos)
    if "margen" in metricas and "margen_seguridad" not in metricas:
        metricas["margen_seguridad"] = metricas.get("margen")
        metricas_fmt["margen_seguridad"] = metricas_fmt.get("margen")
    if "colchon" in metricas and "colchon_seguridad" not in metricas:
        metricas["colchon_seguridad"] = metricas.get("colchon")
        metricas_fmt["colchon_seguridad"] = metricas_fmt.get("colchon")
    if "breakeven" in metricas and "precio_breakeven" not in metricas:
        metricas["precio_breakeven"] = metricas.get("breakeven")
        metricas_fmt["precio_breakeven"] = metricas_fmt.get("breakeven")
    if "break_even" in metricas and "precio_breakeven" not in metricas:
        metricas["precio_breakeven"] = metricas.get("break_even")
        metricas_fmt["precio_breakeven"] = metricas_fmt.get("break_even")

    # --- Vista inversor + reparto (para PDF/plantillas) ---
    inversion_total = _safe_float(
        metricas.get("inversion_total")
        or metricas.get("valor_adquisicion_total")
        or metricas.get("valor_adquisicion")
        or 0.0,
        0.0,
    )

    beneficio_bruto = _safe_float(
        metricas.get("beneficio_bruto")
        or metricas.get("beneficio")
        or 0.0,
        0.0,
    )

    comision_pct = _safe_float(
        _deep_get(
            "comision_inversure_pct",
            "inversure_comision_pct",
            "comision_pct",
        ),
        0.0,
    )
    if comision_pct < 0:
        comision_pct = 0.0
    if comision_pct > 100:
        comision_pct = 100.0

    comision_eur = _safe_float(
        _deep_get(
            "comision_inversure_eur",
            "inversure_comision_eur",
            "comision_eur",
        ),
        0.0,
    )

    # Si no viene calculada, la calculamos sobre el beneficio bruto
    if comision_eur == 0.0 and comision_pct and beneficio_bruto:
        comision_eur = beneficio_bruto * (comision_pct / 100.0)

    beneficio_neto_inversor = _safe_float(
        metricas.get("beneficio_neto")
        or (beneficio_bruto - comision_eur),
        0.0,
    )

    roi_neto_inversor = _safe_float(
        metricas.get("roi_neto")
        or ((beneficio_neto_inversor / inversion_total) * 100.0 if inversion_total else 0.0),
        0.0,
    )

    # Asegurar aliases útiles para plantillas
    metricas["comision_inversure_pct"] = comision_pct
    metricas["comision_inversure_eur"] = comision_eur
    metricas["beneficio_bruto"] = beneficio_bruto
    metricas["beneficio_neto"] = beneficio_neto_inversor
    metricas["roi_neto"] = roi_neto_inversor
    metricas["inversion_total"] = inversion_total
    # Aliases esperados por el PDF
    metricas["beneficio_estimado"] = metricas.get("beneficio_estimado", beneficio_bruto)
    metricas["roi_estimado"] = metricas.get("roi_estimado", roi)

    metricas_fmt["comision_inversure_pct"] = _fmt_pct(comision_pct)
    metricas_fmt["comision_inversure_eur"] = _fmt_eur(comision_eur)
    metricas_fmt["beneficio_bruto"] = _fmt_eur(beneficio_bruto)
    metricas_fmt["beneficio_neto"] = _fmt_eur(beneficio_neto_inversor)
    metricas_fmt["roi_neto"] = _fmt_pct(roi_neto_inversor)
    metricas_fmt["inversion_total"] = _fmt_eur(inversion_total)
    metricas_fmt["beneficio_estimado"] = _fmt_eur(metricas["beneficio_estimado"])
    metricas_fmt["roi_estimado"] = _fmt_pct(metricas["roi_estimado"])

    inversor = SafeAccessDict(
        {
            "inversion_total": inversion_total,
            "comision_inversure_pct": comision_pct,
            "comision_inversure_eur": comision_eur,
            "beneficio_neto_inversor": beneficio_neto_inversor,
            "roi_neto_inversor": roi_neto_inversor,
            # aliases por si el template usa otros nombres
            "comision_pct": comision_pct,
            "comision_eur": comision_eur,
            "beneficio_neto": beneficio_neto_inversor,
            "roi_neto": roi_neto_inversor,
        }
    )

    inversor_fmt = SafeAccessDict(
        {
            "inversion_total": _fmt_eur(inversion_total),
            "comision_inversure_pct": _fmt_pct(comision_pct),
            "comision_inversure_eur": _fmt_eur(comision_eur),
            "beneficio_neto_inversor": _fmt_eur(beneficio_neto_inversor),
            "roi_neto_inversor": _fmt_pct(roi_neto_inversor),
            # aliases
            "comision_pct": _fmt_pct(comision_pct),
            "comision_eur": _fmt_eur(comision_eur),
            "beneficio_neto": _fmt_eur(beneficio_neto_inversor),
            "roi_neto": _fmt_pct(roi_neto_inversor),
        }
    )

    # Reparto del beneficio (para barras/indicadores en PDF)
    reparto_total = beneficio_bruto
    reparto_inversure = comision_eur
    reparto_inversor = max(reparto_total - reparto_inversure, 0.0)

    if reparto_total > 0:
        pct_inversure = (reparto_inversure / reparto_total) * 100.0
        pct_inversor = (reparto_inversor / reparto_total) * 100.0
    else:
        pct_inversure = 0.0
        pct_inversor = 0.0

    # clamp para uso en CSS width
    pct_inversure = max(0.0, min(100.0, pct_inversure))
    pct_inversor = max(0.0, min(100.0, pct_inversor))

    reparto = SafeAccessDict(
        {
            "total": reparto_total,
            "inversure": reparto_inversure,
            "inversor": reparto_inversor,
            "pct_inversure": pct_inversure,
            "pct_inversor": pct_inversor,
        }
    )

    reparto_fmt = SafeAccessDict(
        {
            "total": _fmt_eur(reparto_total),
            "inversure": _fmt_eur(reparto_inversure),
            "inversor": _fmt_eur(reparto_inversor),
            "pct_inversure": _fmt_pct(pct_inversure),
            "pct_inversor": _fmt_pct(pct_inversor),
        }
    )

    return {
        "metricas": metricas,
        "metricas_fmt": metricas_fmt,
        "resultado": resultado,
        "texto": texto,
        "inversor": inversor,
        "inversor_fmt": inversor_fmt,
        "reparto": reparto,
        "reparto_fmt": reparto_fmt,
    }


# --- Datos de identificación inmueble desde estudio ---
def _datos_inmueble_desde_estudio(estudio: Estudio) -> dict:
    """Extrae y normaliza datos de identificación del inmueble desde `estudio` y su JSON `datos`.

    El simulador/JS puede guardar estos campos con nombres distintos o dentro de secciones
    (`datos['inmueble']`, `datos['tecnico']`, etc.). Aquí buscamos de forma defensiva.
    """
    d = estudio.datos or {}

    def _s(v) -> str:
        if v is None:
            return ""
        return str(v).strip()

    def _deep_get(*keys, default=None):
        containers = [
            d,
            d.get("inmueble") if isinstance(d.get("inmueble"), dict) else {},
            d.get("tecnico") if isinstance(d.get("tecnico"), dict) else {},
            d.get("kpis") if isinstance(d.get("kpis"), dict) else {},
        ]
        for k in keys:
            for c in containers:
                if not isinstance(c, dict):
                    continue
                if k in c and c.get(k) not in (None, ""):
                    return c.get(k)
        return default

    tipologia = _s(
        _deep_get(
            "tipologia",
            "tipo_inmueble",
            "tipologia_inmueble",
            "tipo",
            "tipoActivo",
            "tipo_activo",
        )
    )

    estado = _s(
        _deep_get(
            "estado",
            "estado_conservacion",
            "estadoConservacion",
            "conservacion",
            "estado_inmueble",
        )
    )

    situacion = _s(
        _deep_get(
            "situacion",
            "situacion_ocupacional",
            "situacionOcupacional",
            "ocupacion",
            "situacion_inmueble",
        )
    )

    superficie_raw = _deep_get(
        "superficie_m2",
        "superficie",
        "m2",
        "metros_cuadrados",
        "m2_construidos",
        "m2Construidos",
        "superficie_construida",
        "superficieConstruida",
    )
    superficie_m2 = _safe_float(superficie_raw, 0.0)

    nombre_proyecto = _s(
        _deep_get(
            "nombre_proyecto",
            "nombre",
            "proyecto",
            "proyecto_nombre",
        )
    )
    if not nombre_proyecto:
        nombre_proyecto = _s(getattr(estudio, "nombre", "") or "")

    direccion = _s(
        _deep_get(
            "direccion",
            "direccion_completa",
            "proyecto_direccion",
        )
    )
    if not direccion:
        direccion = _s(getattr(estudio, "direccion", "") or "")

    ref_catastral = _s(
        _deep_get(
            "ref_catastral",
            "referencia_catastral",
            "ref_catastral_inmueble",
        )
    )
    if not ref_catastral:
        ref_catastral = _s(getattr(estudio, "ref_catastral", "") or "")

    # Valor de referencia: preferimos el campo del modelo si existe
    valor_referencia_num = _safe_float(getattr(estudio, "valor_referencia", None), None)
    if valor_referencia_num is None:
        valor_referencia_num = _safe_float(
            _deep_get(
                "valor_referencia",
                "valor_referencia_catastral",
                "valorRefCatastral",
                "valorReferencia",
                "valor_referencia_catastro",
            ),
            0.0,
        )

    # Formatos
    superficie_m2_fmt = f"{_fmt_es_number(superficie_m2, 0)} m²" if superficie_m2 else ""
    valor_referencia_fmt = _fmt_eur(valor_referencia_num) if valor_referencia_num else ""

    creado = getattr(estudio, "creado", None)
    creado_fmt = creado.strftime("%d/%m/%Y") if creado else ""

    return {
        "nombre_proyecto": nombre_proyecto,
        "direccion": direccion,
        "ref_catastral": ref_catastral,
        "tipologia": tipologia,
        "estado": estado,
        "situacion": situacion,
        "superficie_m2": superficie_m2,
        "superficie_m2_fmt": superficie_m2_fmt,
        "valor_referencia": valor_referencia_num,
        "valor_referencia_fmt": valor_referencia_fmt,
        "fecha": creado,
        "fecha_fmt": creado_fmt,
    }


def _build_dashboard_context(user):
    perms = resolve_permissions(user)
    estados_cerrados = {"cerrado", "descartado"}
    proyectos = Proyecto.objects.all()
    proyectos_activos = proyectos.exclude(estado__in=estados_cerrados)
    activos_ids = list(proyectos_activos.values_list("id", flat=True))
    capital_acumulado = (
        Participacion.objects.filter(estado="confirmada")
        .aggregate(total=Sum("importe_invertido"))
        .get("total")
        or Decimal("0")
    )
    inversores_con_cuota = (
        Cliente.objects.filter(participaciones__estado="confirmada", cuota_abonada=True)
        .distinct()
        .count()
    )
    capital_actual = (
        Participacion.objects.filter(estado="confirmada", proyecto_id__in=activos_ids)
        .aggregate(total=Sum("importe_invertido"))
        .get("total")
        or Decimal("0")
    )
    inversores_activos = (
        Participacion.objects.filter(estado="confirmada", proyecto_id__in=activos_ids)
        .values_list("cliente_id", flat=True)
        .distinct()
        .count()
    )
    total_operaciones = proyectos.count()

    perfiles = {
        p.cliente_id: p
        for p in InversorPerfil.objects.filter(cliente_id__in=Participacion.objects.filter(estado="confirmada").values_list("cliente_id", flat=True))
    }
    aportacion_por_cliente = {}
    for part in (
        Participacion.objects.filter(estado="confirmada")
        .order_by("cliente_id", "creado", "id")
    ):
        if part.cliente_id in aportacion_por_cliente:
            continue
        perfil = perfiles.get(part.cliente_id)
        override = getattr(perfil, "aportacion_inicial_override", None) if perfil else None
        if override not in (None, ""):
            aportacion_por_cliente[part.cliente_id] = Decimal(override)
        else:
            aportacion_por_cliente[part.cliente_id] = Decimal(part.importe_invertido or 0)
    capital_en_vigor = sum(aportacion_por_cliente.values(), Decimal("0"))

    estado_colores = {
        "captacion": "#f59e0b",
        "comprado": "#0ea5e9",
        "comercializacion": "#6366f1",
        "reservado": "#22c55e",
        "vendido": "#10b981",
        "cerrado": "#14b8a6",
        "descartado": "#94a3b8",
    }
    beneficios = []
    total_beneficio = 0.0
    for proyecto in proyectos:
        snap = _get_snapshot_comunicacion(proyecto)
        resultado = _resultado_desde_memoria(proyecto, snap)
        beneficio = float(resultado.get("beneficio_neto") or 0.0)
        valor_adq = float(resultado.get("valor_adquisicion") or 0.0)
        pct_beneficio = (beneficio / valor_adq * 100.0) if valor_adq else 0.0
        total_beneficio += beneficio
        estado = proyecto.estado or ""
        estado_label = proyecto.get_estado_display() if hasattr(proyecto, "get_estado_display") else estado
        beneficios.append(
            {
                "nombre": proyecto.nombre or f"Proyecto {proyecto.id}",
                "valor": beneficio,
                "pct_beneficio": pct_beneficio,
                "estado": estado,
                "estado_label": estado_label,
            }
        )

    beneficios_validos = [b for b in beneficios if b["valor"] is not None]
    avg_beneficio = (
        (total_beneficio / len(beneficios_validos)) if beneficios_validos else 0.0
    )
    max_beneficio = max([b["valor"] for b in beneficios_validos], default=0.0)
    beneficios_chart = []
    for b in sorted(beneficios_validos, key=lambda x: x["valor"], reverse=True):
        pct = (b["valor"] / max_beneficio * 100.0) if max_beneficio else 0.0
        beneficios_chart.append(
            {
                "nombre": b["nombre"],
                "valor": b["valor"],
                "valor_fmt": _fmt_eur(b["valor"]),
                "pct_fmt": _fmt_pct(b.get("pct_beneficio") or 0.0),
                "estado": b.get("estado") or "",
                "estado_label": b.get("estado_label") or "",
                "color": estado_colores.get(b.get("estado"), "#f2b53b"),
                "pct": pct,
            }
        )

    def _fmt_money(value):
        return _fmt_eur(float(value or 0.0))

    def _calc_beneficios_operacion(proyecto: Proyecto, snapshot: dict) -> dict:
        resultado = _resultado_desde_memoria(proyecto, snapshot)
        beneficio_bruto = float(resultado.get("beneficio_neto") or 0.0)
        valor_adquisicion = float(resultado.get("valor_adquisicion") or 0.0)
        inv_sec = snapshot.get("inversor") if isinstance(snapshot.get("inversor"), dict) else {}
        comision_pct = _safe_float(
            inv_sec.get("comision_inversure_pct")
            or inv_sec.get("inversure_comision_pct")
            or inv_sec.get("comision_pct")
            or snapshot.get("comision_inversure_pct")
            or snapshot.get("inversure_comision_pct")
            or snapshot.get("comision_pct")
            or 0.0,
            0.0,
        )
        comision_pct = max(0.0, min(100.0, comision_pct))
        comision_eur = beneficio_bruto * (comision_pct / 100.0) if beneficio_bruto else 0.0
        beneficio_neto = beneficio_bruto - comision_eur

        proj_extra = proyecto.extra if isinstance(proyecto.extra, dict) else {}
        proj_override = proj_extra.get("beneficio_operacion_override")
        if isinstance(proj_override, dict):
            override_bruto = proj_override.get("beneficio_bruto")
            override_comision = proj_override.get("comision_eur")
            override_neto = proj_override.get("beneficio_neto_total")
            if override_bruto not in (None, ""):
                beneficio_bruto = _safe_float(override_bruto, beneficio_bruto)
            if override_comision not in (None, ""):
                comision_eur = _safe_float(override_comision, comision_eur)
            if override_neto not in (None, ""):
                beneficio_neto = _safe_float(override_neto, beneficio_neto)
            elif override_bruto not in (None, "") or override_comision not in (None, ""):
                beneficio_neto = beneficio_bruto - comision_eur
        return {
            "beneficio_bruto": beneficio_bruto,
            "beneficio_neto": beneficio_neto,
            "comision_eur": comision_eur,
            "valor_adquisicion": valor_adquisicion,
        }

    proyectos_estado = []
    cerrado_estados = {"cerrado"}
    abierto_estados = {"captacion", "comprado", "comercializacion", "reservado", "vendido"}
    cerrado_bruto = cerrado_neto = 0.0
    cerrado_valor_adq = 0.0
    cerrado_roi_bruto = []
    cerrado_roi_neto = []
    abierto_bruto = abierto_neto = 0.0
    total_comision_inversure = 0.0
    beneficio_deviation = []
    for proyecto in proyectos:
        snap = _get_snapshot_comunicacion(proyecto)
        benef = _calc_beneficios_operacion(proyecto, snap)
        beneficio_bruto = benef["beneficio_bruto"]
        beneficio_neto = benef["beneficio_neto"]
        valor_adquisicion = benef["valor_adquisicion"]
        total_comision_inversure += benef.get("comision_eur") or 0.0
        estado = proyecto.estado or ""
        estado_label = proyecto.get_estado_display() if hasattr(proyecto, "get_estado_display") else estado
        proyectos_estado.append(
            {
                "id": proyecto.id,
                "nombre": proyecto.nombre or f"Proyecto {proyecto.id}",
                "estado": estado,
                "estado_label": estado_label,
            }
        )
        if estado in cerrado_estados:
            cerrado_bruto += beneficio_bruto
            cerrado_neto += beneficio_neto
            cerrado_valor_adq += valor_adquisicion
            if valor_adquisicion:
                cerrado_roi_bruto.append(beneficio_bruto / valor_adquisicion * 100.0)
                cerrado_roi_neto.append(beneficio_neto / valor_adquisicion * 100.0)
        elif estado in abierto_estados:
            abierto_bruto += beneficio_bruto
            abierto_neto += beneficio_neto

        memoria_benef = _beneficio_estimado_real_memoria(proyecto)
        beneficio_estimado = memoria_benef.get("beneficio_estimado", 0.0)
        beneficio_real = memoria_benef.get("beneficio_real", 0.0)
        if memoria_benef.get("has_movimientos"):
            beneficio_deviation.append(
                {
                    "nombre": proyecto.nombre or f"Proyecto {proyecto.id}",
                    "estimado": float(beneficio_estimado or 0.0),
                    "real": float(beneficio_real or 0.0),
                }
            )

    cerrado_roi_bruto_total = (
        (cerrado_bruto / cerrado_valor_adq * 100.0) if cerrado_valor_adq else 0.0
    )
    cerrado_roi_neto_total = (
        (cerrado_neto / cerrado_valor_adq * 100.0) if cerrado_valor_adq else 0.0
    )
    cerrado_roi_bruto_medio = (
        sum(cerrado_roi_bruto) / len(cerrado_roi_bruto) if cerrado_roi_bruto else 0.0
    )
    cerrado_roi_neto_medio = (
        sum(cerrado_roi_neto) / len(cerrado_roi_neto) if cerrado_roi_neto else 0.0
    )
    cerrado_bruto_medio = (cerrado_bruto / len(cerrado_roi_bruto)) if cerrado_roi_bruto else 0.0
    cerrado_neto_medio = (cerrado_neto / len(cerrado_roi_neto)) if cerrado_roi_neto else 0.0

    today = timezone.now().date()
    checklist_qs = ChecklistItem.objects.select_related("proyecto").exclude(estado="hecho")
    checklist_overdue_qs = checklist_qs.filter(fecha_objetivo__lt=today)
    checklist_items = []
    for it in checklist_qs.order_by("fecha_objetivo", "id")[:6]:
        overdue = bool(it.fecha_objetivo and it.fecha_objetivo < today)
        dias_retraso = (today - it.fecha_objetivo).days if overdue else 0
        checklist_items.append(
            {
                "proyecto": it.proyecto.nombre if it.proyecto else "",
                "fase": it.get_fase_display(),
                "titulo": it.titulo,
                "responsable": it.responsable or "",
                "fecha_objetivo": it.fecha_objetivo,
                "overdue": overdue,
                "dias_retraso": dias_retraso,
            }
        )

    return {
        "is_admin": is_admin_user(user),
        "can_simulador": perms.get("can_simulador"),
        "can_estudios": perms.get("can_estudios"),
        "can_proyectos": perms.get("can_proyectos"),
        "can_clientes": perms.get("can_clientes"),
        "can_inversores": perms.get("can_inversores"),
        "can_usuarios": perms.get("can_usuarios"),
        "can_cms": perms.get("can_cms"),
        "dashboard_stats": {
            "inversores_activos": inversores_activos,
            "inversores_cuota": inversores_con_cuota,
            "capital_en_vigor": capital_en_vigor,
            "capital_actual": capital_actual,
            "capital_acumulado": capital_acumulado,
            "operaciones": total_operaciones,
            "beneficio_total": total_beneficio,
            "beneficio_medio": avg_beneficio,
            "beneficio_cerrado_bruto": cerrado_bruto,
            "beneficio_cerrado_neto": cerrado_neto,
            "beneficio_cerrado_bruto_medio": cerrado_bruto_medio,
            "beneficio_cerrado_neto_medio": cerrado_neto_medio,
            "beneficio_abierto_bruto": abierto_bruto,
            "beneficio_abierto_neto": abierto_neto,
            "beneficio_cerrado_roi_bruto_total": cerrado_roi_bruto_total,
            "beneficio_cerrado_roi_neto_total": cerrado_roi_neto_total,
            "beneficio_cerrado_roi_bruto_medio": cerrado_roi_bruto_medio,
            "beneficio_cerrado_roi_neto_medio": cerrado_roi_neto_medio,
            "beneficio_inversure": total_comision_inversure,
        },
        "dashboard_stats_fmt": {
            "capital_en_vigor": _fmt_money(capital_en_vigor),
            "capital_actual": _fmt_money(capital_actual),
            "capital_acumulado": _fmt_money(capital_acumulado),
            "beneficio_total": _fmt_money(total_beneficio),
            "beneficio_medio": _fmt_money(avg_beneficio),
            "beneficio_cerrado_bruto": _fmt_money(cerrado_bruto),
            "beneficio_cerrado_neto": _fmt_money(cerrado_neto),
            "beneficio_cerrado_bruto_medio": _fmt_money(cerrado_bruto_medio),
            "beneficio_cerrado_neto_medio": _fmt_money(cerrado_neto_medio),
            "beneficio_abierto_bruto": _fmt_money(abierto_bruto),
            "beneficio_abierto_neto": _fmt_money(abierto_neto),
            "beneficio_cerrado_roi_bruto_total": _fmt_pct(cerrado_roi_bruto_total),
            "beneficio_cerrado_roi_neto_total": _fmt_pct(cerrado_roi_neto_total),
            "beneficio_cerrado_roi_bruto_medio": _fmt_pct(cerrado_roi_bruto_medio),
            "beneficio_cerrado_roi_neto_medio": _fmt_pct(cerrado_roi_neto_medio),
            "beneficio_inversure": _fmt_money(total_comision_inversure),
        },
        "beneficios_chart": beneficios_chart,
        "beneficio_deviation_chart": beneficio_deviation,
        "proyectos_estado": proyectos_estado,
        "checklist_alerts": {
            "pendientes": checklist_qs.count(),
            "vencidas": checklist_overdue_qs.count(),
            "items": checklist_items,
        },
    }


def home(request):
    ctx = _build_dashboard_context(request.user)
    return render(request, "core/home.html", ctx)


def dashboard(request):
    ctx = _build_dashboard_context(request.user)
    return render(request, "core/dashboard.html", ctx)


def checklist_pendientes(request):
    estado = (request.GET.get("estado") or "pendiente").strip().lower()
    fase = (request.GET.get("fase") or "").strip().lower()
    proyecto_q = (request.GET.get("proyecto") or "").strip()
    responsable_q = (request.GET.get("responsable") or "").strip()
    estado_filter = estado if estado in {"pendiente", "en_curso", "hecho", "vencidas"} else "pendiente"

    qs = ChecklistItem.objects.select_related("proyecto")
    if estado_filter == "vencidas":
        qs = qs.exclude(estado="hecho")
        qs = qs.filter(fecha_objetivo__lt=timezone.now().date())
    else:
        qs = qs.filter(estado=estado_filter)

    if fase:
        qs = qs.filter(fase=fase)
    if proyecto_q:
        qs = qs.filter(proyecto__nombre__icontains=proyecto_q)
    if responsable_q:
        qs = qs.filter(responsable__icontains=responsable_q)

    qs = qs.order_by("fecha_objetivo", "id")

    fases = [f for f, _ in ChecklistItem.FASES]

    ctx = {
        "items": qs,
        "estado": estado_filter,
        "fase": fase,
        "proyecto_q": proyecto_q,
        "responsable_q": responsable_q,
        "fases": fases,
    }
    return render(request, "core/checklist_pendientes.html", ctx)


def nuevo_estudio(request):
    """Crea un estudio nuevo, limpia la sesión del estudio anterior y redirige al simulador."""
    # Crear un estudio vacío como BORRADOR (no debe aparecer en lista hasta que se guarde)
    estudio = Estudio.objects.create(
        nombre="",
        direccion="",
        ref_catastral="",
        valor_referencia=None,
        datos={},
        guardado=False,
    )

    # Marcarlo como estudio activo en la sesión
    request.session["estudio_id"] = estudio.id

    # Redirigir al simulador (la vista simulador leerá el estudio desde sesión)
    return redirect("core:simulador")


def simulador(request):
    """Renderiza el simulador.

    - Si llega un estudio explícito por GET (estudio_id / id / codigo), lo carga y lo fija en sesión.
    - Si no, usa el estudio activo en sesión.
    - Si no hay ninguno, muestra el formulario vacío.

    Nota: `codigo` se acepta por compatibilidad con enlaces antiguos.
    Si `codigo` es numérico, se interpreta como `id`.
    Si no es numérico y el modelo Estudio tiene campo `codigo`, se busca por ese campo.
    """

    # 1) Selección explícita desde lista (prioridad sobre sesión)
    estudio_id_param = (request.GET.get("estudio_id") or request.GET.get("id") or "").strip()
    codigo_param = (request.GET.get("codigo") or "").strip()

    selected_id = None

    if estudio_id_param.isdigit():
        selected_id = int(estudio_id_param)
    elif codigo_param:
        if codigo_param.isdigit():
            selected_id = int(codigo_param)
        else:
            # Intentar buscar por campo `codigo` si existe en el modelo
            try:
                Estudio._meta.get_field("codigo")
            except Exception:
                selected_id = None
            else:
                try:
                    selected_id = Estudio.objects.only("id").get(codigo=codigo_param).id
                except Estudio.DoesNotExist:
                    selected_id = None

    # Si se seleccionó uno válido por GET, fijarlo en sesión
    if selected_id:
        request.session["estudio_id"] = selected_id

    # 2) Resolver estudio desde sesión
    estudio_obj = None
    estudio_id = request.session.get("estudio_id")
    if estudio_id:
        try:
            estudio_obj = Estudio.objects.get(id=estudio_id)
        except Estudio.DoesNotExist:
            estudio_obj = None

    # 3) Construir contexto
    if estudio_obj is None:
        estudio = {
            "id": None,
            "nombre": "",
            "direccion": "",
            "ref_catastral": "",
            "valor_referencia": "",
            "datos": {},
            "guardado": False,
            "bloqueado": False,
        }
    else:
        estudio = {
            "id": estudio_obj.id,
            "nombre": estudio_obj.nombre,
            "direccion": estudio_obj.direccion,
            "ref_catastral": estudio_obj.ref_catastral,
            "valor_referencia": estudio_obj.valor_referencia,
            "datos": estudio_obj.datos or {},
            "guardado": bool(getattr(estudio_obj, "guardado", False)),
            "bloqueado": bool(getattr(estudio_obj, "bloqueado", False)),
        }

    # --- Estado inicial para hidratar el simulador al abrir un estudio guardado ---
    estado_inicial = {}
    try:
        if estudio_obj is not None:
            datos0 = getattr(estudio_obj, "datos", None) or {}
            if isinstance(datos0, dict):
                # Preferimos snapshot si existe; si no, el JSON completo
                estado_inicial = datos0.get("snapshot") or datos0
    except Exception:
        estado_inicial = {}

    ctx = {
        "estudio": estudio,
        "ESTUDIO_ID": str(estudio_obj.id) if estudio_obj is not None else "",
        "ESTADO_INICIAL_JSON": json.dumps(estado_inicial, ensure_ascii=False),
    }

    return render(request, "core/simulador.html", ctx)


def lista_estudio(request):
    # Por defecto, ocultamos estudios ya convertidos a proyecto (bloqueados), para no saturar el listado.
    # Si se desea ver también los convertidos, usar ?mostrar_convertidos=1
    estudios_qs = Estudio.objects.filter(guardado=True)

    mostrar_convertidos = (request.GET.get("mostrar_convertidos") == "1")
    try:
        Estudio._meta.get_field("bloqueado")
        if not mostrar_convertidos:
            estudios_qs = estudios_qs.filter(bloqueado=False)
    except Exception:
        # Si el modelo no tiene el campo (o hay inconsistencias), mantenemos el listado clásico
        pass

    estudios_qs_base = estudios_qs
    try:
        estudios_qs = estudios_qs.order_by("-datos__roi_neto", "-datos__roi", "-id")
        # Force evaluation to catch JSON lookup errors on backends without JSON1 support.
        list(estudios_qs[:1])
    except Exception:
        estudios_qs = estudios_qs_base.order_by("-id")
    estudios = []

    for e in estudios_qs:
        d = e.datos or {}
        beneficio_neto = d.get("beneficio_neto", None)
        roi_neto = d.get("roi_neto", None)
        estudios.append({
            "id": e.id,
            "nombre": e.nombre,
            "direccion": e.direccion,
            "ref_catastral": e.ref_catastral,
            "valor_referencia": e.valor_referencia,
            "valor_adquisicion": d.get("valor_adquisicion", 0),
            "beneficio": beneficio_neto if beneficio_neto not in (None, "") else d.get("beneficio", 0),
            "roi": roi_neto if roi_neto not in (None, "") else d.get("roi", 0),
           "fecha": e.creado,
            "guardado": bool(getattr(e, "guardado", False)),
            "bloqueado": bool(getattr(e, "bloqueado", False)),
        })

    return render(
        request,
        "core/lista_estudio.html",
        {"estudios": estudios},
    )


def lista_proyectos(request):
    estados_cerrados = {"cerrado", "descartado"}
    proyectos = Proyecto.objects.exclude(estado__in=estados_cerrados).order_by("-id")
    if is_comercial_user(request.user) and not is_admin_user(request.user) and not use_custom_permissions(request.user):
        proyectos = proyectos.filter(acceso_comercial=True)
    proyectos_ids = list(proyectos.values_list("id", flat=True))

    def _as_float(val, default=0.0):
        try:
            if val is None or val == "":
                return float(default)
            return float(val)
        except Exception:
            return float(default)

    def _get_snapshot(p: Proyecto) -> dict:
        # Prioridad: snapshot_datos (copia inmutable) > origen_snapshot.datos > origen_estudio.datos
        snap = getattr(p, "snapshot_datos", None)
        if isinstance(snap, dict) and snap:
            return snap
        osnap = getattr(p, "origen_snapshot", None)
        if osnap is not None:
            datos = getattr(osnap, "datos", None)
            if isinstance(datos, dict) and datos:
                return datos
        oest = getattr(p, "origen_estudio", None)
        if oest is not None:
            datos = getattr(oest, "datos", None)
            if isinstance(datos, dict) and datos:
                return datos
        return {}

    gastos_reales_map = {}
    if proyectos_ids:
        for row in (
            GastoProyecto.objects.filter(proyecto_id__in=proyectos_ids, estado="confirmado")
            .values("proyecto_id")
            .annotate(total=Sum("importe"))
        ):
            gastos_reales_map[row["proyecto_id"]] = _as_float(row.get("total"), 0.0)

    # Enriquecer cada proyecto con métricas heredadas (sin exigir cambios en el template)
    for p in proyectos:
        snap = _get_snapshot(p)
        economico = snap.get("economico") if isinstance(snap.get("economico"), dict) else {}
        inversor = snap.get("inversor") if isinstance(snap.get("inversor"), dict) else {}
        kpis = snap.get("kpis") if isinstance(snap.get("kpis"), dict) else {}
        metricas = kpis.get("metricas") if isinstance(kpis.get("metricas"), dict) else {}

        # Capital objetivo: total de gastos (real/estimado) desde memoria
        capital_objetivo = _capital_objetivo_desde_memoria(p, snap)

        # Capital captado: suma de participaciones reales del proyecto
        capital_captado = Participacion.objects.filter(
            proyecto=p, estado="confirmada"
        ).aggregate(total=Sum("importe_invertido")).get("total") or 0
        capital_captado = _as_float(capital_captado, 0.0)

        # ROI heredado del estudio (preferimos neto si existe)
        roi = (
            inversor.get("roi_neto")
            or metricas.get("roi_neto")
            or metricas.get("roi")
            or economico.get("roi_estimado")
            or economico.get("roi")
            or 0
        )
        roi = _as_float(roi, 0.0)

        # Adjuntar atributos para plantilla
        p.capital_objetivo = capital_objetivo
        p.capital_captado = capital_captado
        p.roi = roi
        p._snapshot = snap
        try:
            extra = getattr(p, "extra", None)
            if isinstance(extra, dict) and "notificar_inversores" in extra:
                p.notificar_inversores = bool(extra.get("notificar_inversores"))
            else:
                sec = snap.get("proyecto") if isinstance(snap.get("proyecto"), dict) else {}
                p.notificar_inversores = bool(sec.get("notificar_inversores")) if "notificar_inversores" in sec else True
        except Exception:
            p.notificar_inversores = True

    return render(
        request,
        "core/lista_proyectos.html",
        {
            "proyectos": proyectos,
            "titulo": "Proyectos",
            "subtitulo": "Operaciones activas en fase de ejecución y seguimiento",
            "cerrados_url": reverse("core:lista_proyectos_cerrados"),
            "cerrados_label": "Ver proyectos cerrados",
        },
    )


def lista_proyectos_cerrados(request):
    estados_cerrados = {"cerrado", "descartado"}
    proyectos = Proyecto.objects.filter(estado__in=estados_cerrados).order_by("-id")
    if is_comercial_user(request.user) and not is_admin_user(request.user) and not use_custom_permissions(request.user):
        proyectos = proyectos.filter(acceso_comercial=True)
    proyectos_ids = list(proyectos.values_list("id", flat=True))

    def _as_float(val, default=0.0):
        try:
            if val is None or val == "":
                return float(default)
            return float(val)
        except Exception:
            return float(default)

    def _get_snapshot(p: Proyecto) -> dict:
        snap = getattr(p, "snapshot_datos", None)
        if isinstance(snap, dict) and snap:
            return snap
        osnap = getattr(p, "origen_snapshot", None)
        if osnap is not None:
            datos = getattr(osnap, "datos", None)
            if isinstance(datos, dict) and datos:
                return datos
        oest = getattr(p, "origen_estudio", None)
        if oest is not None:
            datos = getattr(oest, "datos", None)
            if isinstance(datos, dict) and datos:
                return datos
        return {}

    gastos_reales_map = {}
    if proyectos_ids:
        for row in (
            GastoProyecto.objects.filter(proyecto_id__in=proyectos_ids, estado="confirmado")
            .values("proyecto_id")
            .annotate(total=Sum("importe"))
        ):
            gastos_reales_map[row["proyecto_id"]] = _as_float(row.get("total"), 0.0)

    for p in proyectos:
        snap = _get_snapshot(p)
        economico = snap.get("economico") if isinstance(snap.get("economico"), dict) else {}
        inversor = snap.get("inversor") if isinstance(snap.get("inversor"), dict) else {}
        kpis = snap.get("kpis") if isinstance(snap.get("kpis"), dict) else {}
        metricas = kpis.get("metricas") if isinstance(kpis.get("metricas"), dict) else {}

        # Capital objetivo: total de gastos (real/estimado) desde memoria
        capital_objetivo = _capital_objetivo_desde_memoria(p, snap)

        capital_captado = Participacion.objects.filter(
            proyecto=p, estado="confirmada"
        ).aggregate(total=Sum("importe_invertido")).get("total") or 0
        capital_captado = _as_float(capital_captado, 0.0)

        roi = (
            inversor.get("roi_neto")
            or metricas.get("roi_neto")
            or metricas.get("roi")
            or economico.get("roi_estimado")
            or economico.get("roi")
            or 0
        )
        roi = _as_float(roi, 0.0)

        p.capital_objetivo = capital_objetivo
        p.capital_captado = capital_captado
        p.roi = roi
        p._snapshot = snap
        try:
            extra = getattr(p, "extra", None)
            if isinstance(extra, dict) and "notificar_inversores" in extra:
                p.notificar_inversores = bool(extra.get("notificar_inversores"))
            else:
                sec = snap.get("proyecto") if isinstance(snap.get("proyecto"), dict) else {}
                p.notificar_inversores = bool(sec.get("notificar_inversores")) if "notificar_inversores" in sec else True
        except Exception:
            p.notificar_inversores = True

    return render(
        request,
        "core/lista_proyectos.html",
        {
            "proyectos": proyectos,
            "titulo": "Proyectos cerrados",
            "subtitulo": "Operaciones finalizadas o descartadas",
            "cerrados_url": reverse("core:lista_proyectos"),
            "cerrados_label": "Ver proyectos activos",
        },
    )


def clientes(request):
    clientes_qs = Cliente.objects.all().order_by("nombre")
    return render(request, "core/clientes.html", {"clientes": clientes_qs})


def _normalizar_dni_cif(value: str) -> str:
    return (value or "").strip().upper().replace(" ", "")


def _validar_dni_cif(value: str) -> bool:
    value = _normalizar_dni_cif(value)
    if not value:
        return False
    letras = "TRWAGMYFPDXBNJZSQVHLCKE"
    # DNI: 8 dígitos + letra
    if len(value) == 9 and value[:-1].isdigit():
        num = int(value[:-1])
        return value[-1] == letras[num % 23]
    # NIE: X/Y/Z + 7 dígitos + letra
    if len(value) == 9 and value[0] in "XYZ" and value[1:-1].isdigit():
        prefix = {"X": "0", "Y": "1", "Z": "2"}[value[0]]
        num = int(prefix + value[1:-1])
        return value[-1] == letras[num % 23]
    # CIF: letra + 7 dígitos + control
    if len(value) == 9 and value[0].isalpha() and value[1:-1].isdigit():
        letra = value[0]
        nums = value[1:-1]
        control = value[-1]
        suma_par = sum(int(nums[i]) for i in range(1, 7, 2))
        suma_impar = 0
        for i in range(0, 7, 2):
            n = int(nums[i]) * 2
            suma_impar += (n // 10) + (n % 10)
        total = suma_par + suma_impar
        digito = (10 - (total % 10)) % 10
        control_letra = "JABCDEFGHI"[digito]
        if letra in "ABEH":
            return control == str(digito)
        if letra in "KPQS":
            return control == control_letra
        return control == str(digito) or control == control_letra
    return False


def clientes_form(request):
    if request.method == "POST":
        data = request.POST
        try:
            dni_cif = _normalizar_dni_cif(data.get("dni_cif"))
            if not _validar_dni_cif(dni_cif):
                messages.error(request, "DNI/NIE/CIF no es válido.")
                return render(
                    request,
                    "core/clientes_form.html",
                    {
                        "titulo": "Nuevo cliente",
                        "form_data": data,
                        "dni_cif_error": "DNI/NIE/CIF no es válido.",
                    },
                )
            kwargs = {
                "tipo_persona": data.get("tipo_persona") or "F",
                "nombre": (data.get("nombre") or "").strip(),
                "dni_cif": dni_cif,
                "email": (data.get("email") or "").strip() or None,
                "telefono": (data.get("telefono") or "").strip() or None,
                "iban": (data.get("iban") or "").strip() or None,
                "observaciones": (data.get("observaciones") or "").strip() or None,
                "direccion_postal": (data.get("direccion") or "").strip() or None,
                "cuota_abonada": bool(data.get("cuota_pagada")),
                "presente_en_comunidad": bool(data.get("en_comunidad")),
            }
            fecha = _parse_date(data.get("fecha_alta"))
            if fecha:
                kwargs["fecha_introduccion"] = fecha
            Cliente.objects.create(**kwargs)
            messages.success(request, "Cliente creado correctamente.")
            return redirect("core:clientes")
        except Exception as e:
            messages.error(request, f"No se pudo crear el cliente: {e}")

    form_data = {}
    if request.GET:
        form_data = {
            "dni_cif": (request.GET.get("dni_cif") or "").strip(),
            "email": (request.GET.get("email") or "").strip(),
            "telefono": (request.GET.get("telefono") or "").strip(),
            "nombre": (request.GET.get("nombre") or "").strip(),
        }
    return render(
        request,
        "core/clientes_form.html",
        {
            "titulo": "Nuevo cliente",
            "cliente": Cliente(),
            "form_data": form_data,
        },
    )


def cliente_edit(request, cliente_id: int):
    cliente = get_object_or_404(Cliente, id=cliente_id)
    if request.method == "POST":
        data = request.POST
        try:
            dni_cif = _normalizar_dni_cif(data.get("dni_cif"))
            if not _validar_dni_cif(dni_cif):
                messages.error(request, "DNI/NIE/CIF no es válido.")
                return render(
                    request,
                    "core/clientes_form.html",
                    {
                        "titulo": "Editar cliente",
                        "cliente": cliente,
                        "form_data": data,
                        "dni_cif_error": "DNI/NIE/CIF no es válido.",
                    },
                )
            cliente.tipo_persona = data.get("tipo_persona") or cliente.tipo_persona
            cliente.nombre = (data.get("nombre") or "").strip()
            cliente.dni_cif = dni_cif
            cliente.email = (data.get("email") or "").strip() or None
            cliente.telefono = (data.get("telefono") or "").strip() or None
            cliente.iban = (data.get("iban") or "").strip() or None
            cliente.observaciones = (data.get("observaciones") or "").strip() or None
            if data.get("fecha_alta"):
                cliente.fecha_introduccion = _parse_date(data.get("fecha_alta")) or cliente.fecha_introduccion
            cliente.direccion_postal = (data.get("direccion") or "").strip() or None
            cliente.cuota_abonada = bool(data.get("cuota_pagada"))
            cliente.presente_en_comunidad = bool(data.get("en_comunidad"))
            cliente.save()
            messages.success(request, "Cliente actualizado correctamente.")
            return redirect("core:clientes")
        except Exception as e:
            messages.error(request, f"No se pudo actualizar el cliente: {e}")

    return render(request, "core/clientes_form.html", {"titulo": "Editar cliente", "cliente": cliente})


def inversores_list(request):
    participaciones_qs = Participacion.objects.select_related("proyecto").filter(
        estado="confirmada"
    ).order_by("-creado")
    clientes_base = Cliente.objects.all().order_by("nombre").prefetch_related(
        Prefetch("participaciones", queryset=participaciones_qs, to_attr="participaciones_confirmadas")
    )
    perfiles_map = {}
    for cliente in clientes_base:
        perfil, _ = InversorPerfil.objects.get_or_create(cliente=cliente)
        perfiles_map[cliente.id] = perfil

    perfiles_ids = [p.id for p in perfiles_map.values()]
    cliente_ids = list(clientes_base.values_list("id", flat=True))

    totales = {
        row["cliente_id"]: row
        for row in (
            Participacion.objects.filter(cliente_id__in=cliente_ids, estado="confirmada")
            .values("cliente_id")
            .annotate(total=Sum("importe_invertido"), num=Count("id"))
        )
    }
    first_part_qs = (
        Participacion.objects.filter(cliente_id=OuterRef("cliente_id"), estado="confirmada")
        .order_by("creado", "id")
        .values("importe_invertido")[:1]
    )
    aportacion_inicial = {
        row["cliente_id"]: row["first_importe"]
        for row in (
            Participacion.objects.filter(cliente_id__in=cliente_ids, estado="confirmada")
            .values("cliente_id")
            .annotate(first_importe=Subquery(first_part_qs))
        )
    }

    estados_cerrados = {"cerrado", "cerrado_positivo", "cerrado_negativo", "finalizado", "descartado", "vendido"}
    activos = {
        row["cliente_id"]: row["num"]
        for row in (
            Participacion.objects.filter(cliente_id__in=cliente_ids, estado="confirmada")
            .exclude(proyecto__estado__in=estados_cerrados)
            .values("cliente_id")
            .annotate(num=Count("proyecto", distinct=True))
        )
    }

    solicitudes_pend = {
        row["inversor_id"]: row["total"]
        for row in (
            SolicitudParticipacion.objects.filter(inversor_id__in=perfiles_ids, estado="pendiente")
            .values("inversor_id")
            .annotate(total=Count("id"))
        )
    }

    comunicaciones = {
        row["inversor_id"]: row
        for row in (
            ComunicacionInversor.objects.filter(inversor_id__in=perfiles_ids)
            .values("inversor_id")
            .annotate(total=Count("id"), ultima=Max("creado"))
        )
    }

    docs_por_inversor = {}
    if perfiles_ids:
        for d in DocumentoInversor.objects.filter(inversor_id__in=perfiles_ids).order_by("-creado"):
            signed = _s3_presigned_url(d.archivo.name)
            setattr(d, "signed_url", signed or "")
            docs_por_inversor.setdefault(d.inversor_id, []).append(d)

    inversores = []
    total_invertido = 0
    total_participaciones = 0
    total_pendientes = 0

    for cliente in clientes_base:
        perfil = perfiles_map.get(cliente.id)
        if not perfil:
            continue
        total_row = totales.get(cliente.id, {})
        total_cli = float(total_row.get("total") or 0)
        num_part = int(total_row.get("num") or 0)
        total_invertido += total_cli
        total_participaciones += num_part

        pend = int(solicitudes_pend.get(perfil.id, 0))
        total_pendientes += pend

        comm = comunicaciones.get(perfil.id, {})
        ultima_com = comm.get("ultima")
        total_com = int(comm.get("total") or 0)

        participaciones = getattr(cliente, "participaciones_confirmadas", []) or []
        preview = participaciones[:3]

        override_inicial = perfil.aportacion_inicial_override
        inicial_val = float(override_inicial) if override_inicial is not None else float(aportacion_inicial.get(cliente.id) or 0)

        inversores.append(
            {
                "perfil": perfil,
                "cliente": cliente,
                "total_invertido": total_cli,
                "aportacion_inicial": inicial_val,
                "num_participaciones": num_part,
                "proyectos_activos": int(activos.get(cliente.id, 0)),
                "solicitudes_pendientes": pend,
                "ultima_comunicacion": ultima_com,
                "total_comunicaciones": total_com,
                "participaciones_preview": preview,
                "documentos": docs_por_inversor.get(perfil.id, []),
            }
        )

    q = (request.GET.get("q") or "").strip().lower()
    inversores_filtrados = inversores
    if q:
        def _hay_match(inv):
            cliente = inv.get("cliente")
            if not cliente:
                return False
            campos = [
                getattr(cliente, "nombre", ""),
                getattr(cliente, "dni_cif", ""),
                getattr(cliente, "email", ""),
                getattr(cliente, "telefono", ""),
            ]
            return any(q in (str(c) or "").lower() for c in campos)
        inversores_filtrados = [inv for inv in inversores if _hay_match(inv)]

    paginator = Paginator(inversores_filtrados, 8)
    page_obj = paginator.get_page(request.GET.get("page"))

    ctx = {
        "inversores": page_obj.object_list,
        "page_obj": page_obj,
        "q": q,
        "total_inversores": len(inversores),
        "total_inversores_filtrados": len(inversores_filtrados),
        "total_invertido": total_invertido,
        "total_participaciones": total_participaciones,
        "total_pendientes": total_pendientes,
        "proyectos": Proyecto.objects.order_by("-id"),
    }
    return render(request, "core/inversores.html", ctx)


def clientes_import(request):
    if request.method == "POST" and request.FILES.get("archivo"):
        archivo = request.FILES["archivo"]
        try:
            import pandas as pd
        except Exception:
            messages.error(request, "Falta la dependencia pandas para importar el Excel.")
            return redirect("core:clientes_import")

        try:
            df = pd.read_excel(archivo, sheet_name="Datos Participes", header=6)
        except Exception as e:
            messages.error(request, f"No se pudo leer la hoja 'Datos Participes': {e}")
            return redirect("core:clientes_import")

        # Limpiar columnas (eliminar 'Unnamed' y espacios)
        df.columns = [str(c).strip() for c in df.columns]
        df = df.loc[:, ~df.columns.str.contains("^Unnamed", case=False, na=False)]

        def _to_str(val):
            if val is None or (isinstance(val, float) and pd.isna(val)):
                return ""
            return str(val).strip()

        def _to_bool(val):
            s = _to_str(val).lower()
            return s in {"ok", "si", "sí", "true", "1", "x"}

        creados = 0
        omitidos = 0

        for _, row in df.iterrows():
            nombre = _to_str(row.get("Nombre"))
            dni_cif = _to_str(row.get("DNI"))
            if not nombre or not dni_cif:
                omitidos += 1
                continue

            if Cliente.objects.filter(dni_cif=dni_cif).exists():
                omitidos += 1
                continue

            fecha = None
            raw_fecha = row.get("Fecha incorporación")
            if raw_fecha is not None and not (isinstance(raw_fecha, float) and pd.isna(raw_fecha)):
                try:
                    fecha = pd.to_datetime(raw_fecha).date()
                except Exception:
                    fecha = None

            Cliente.objects.create(
                tipo_persona="F",
                nombre=nombre,
                dni_cif=dni_cif,
                email=_to_str(row.get("Correo")) or None,
                telefono=_to_str(row.get("Contacto")) or None,
                iban=_to_str(row.get("Cuenta")) or None,
                direccion_postal=_to_str(row.get("Dirección")) or None,
                presente_en_comunidad=_to_bool(row.get("Comunidad Whatsapp")),
                fecha_introduccion=fecha or timezone.now().date(),
            )
            creados += 1

        messages.success(
            request,
            f"Importación finalizada: {creados} clientes creados, {omitidos} filas omitidas."
        )
        return redirect("core:clientes")

    return render(request, "core/clientes_import.html")


def cliente_inversor_link(request, cliente_id: int):
    cliente = get_object_or_404(Cliente, id=cliente_id)
    perfil, _ = InversorPerfil.objects.get_or_create(cliente=cliente)
    return render(request, "core/inversor_link.html", {"cliente": cliente, "perfil": perfil})


def inversor_buscar(request):
    dni_cif = (request.GET.get("dni_cif") or "").strip()
    email = (request.GET.get("email") or "").strip()
    cliente = None
    if dni_cif:
        dni_cif = _normalizar_dni_cif(dni_cif)
        cliente = Cliente.objects.filter(dni_cif=dni_cif).first()
    if not cliente and email:
        cliente = Cliente.objects.filter(email__iexact=email).first()

    if cliente:
        return redirect("core:cliente_inversor_link", cliente_id=cliente.id)

    if not dni_cif and not email:
        messages.info(request, "Introduce DNI/NIE/CIF o email para buscar un cliente.")
        return redirect("core:inversores_list")

    params = {}
    if dni_cif:
        params["dni_cif"] = dni_cif
    if email:
        params["email"] = email
    messages.info(request, "No existe ese cliente, crea uno nuevo.")
    return redirect(f"{reverse('core:clientes_form')}?{urlencode(params)}")


def _build_inversor_portal_context(perfil: InversorPerfil, internal_view: bool) -> dict:
    participaciones = Participacion.objects.filter(cliente=perfil.cliente).select_related("proyecto").order_by("-creado")
    comunicaciones = ComunicacionInversor.objects.filter(inversor=perfil)
    proyectos_candidatos = Proyecto.objects.filter(
        estado__in=["captacion", "comprado", "comercializacion", "reservado"]
    ).order_by("-id")
    solicitudes = SolicitudParticipacion.objects.filter(inversor=perfil).select_related("proyecto")
    solicitudes_pendientes_list = list(solicitudes.filter(estado="pendiente"))
    pendientes_count = len(solicitudes_pendientes_list)

    total_invertido = participaciones.filter(estado="confirmada").aggregate(total=Sum("importe_invertido")).get("total") or 0
    total_invertido = float(total_invertido or 0)

    participaciones_conf = participaciones.filter(estado="confirmada")
    proyectos_ids = list(participaciones_conf.values_list("proyecto_id", flat=True))

    proyectos_participados = []
    proyectos_seen = set()
    base_parts = participaciones_conf if participaciones_conf.exists() else participaciones
    for part in base_parts:
        proyecto = part.proyecto
        if not proyecto:
            continue
        if proyecto.id in proyectos_seen:
            continue
        proyectos_seen.add(proyecto.id)
        proyectos_participados.append(proyecto)

    aportacion_inicial_calc = 0.0
    first_part = participaciones_conf.order_by("creado", "id").first()
    if first_part and first_part.importe_invertido is not None:
        aportacion_inicial_calc = float(first_part.importe_invertido)
    if perfil.aportacion_inicial_override is not None:
        aportacion_inicial = float(perfil.aportacion_inicial_override)
    else:
        aportacion_inicial = aportacion_inicial_calc

    def _get_snapshot(p: Proyecto) -> dict:
        snap = getattr(p, "snapshot_datos", None)
        if not isinstance(snap, dict):
            snap = {}
        if snap:
            base = dict(snap)
        else:
            base = {}

        extra = getattr(p, "extra", None)
        overlay = {}
        if isinstance(extra, dict):
            ultimo = extra.get("ultimo_guardado")
            if isinstance(ultimo, dict) and isinstance(ultimo.get("payload"), dict):
                overlay = ultimo.get("payload") or {}
            elif isinstance(extra.get("payload"), dict):
                overlay = extra.get("payload") or {}

        if overlay:
            base = _deep_merge_dict(base, overlay)
        if base:
            return base
        osnap = getattr(p, "origen_snapshot", None)
        if osnap is not None:
            datos = getattr(osnap, "datos", None)
            if isinstance(datos, dict) and datos:
                return _deep_merge_dict(dict(datos), overlay)
        oest = getattr(p, "origen_estudio", None)
        if oest is not None:
            datos = getattr(oest, "datos", None)
            if isinstance(datos, dict) and datos:
                return _deep_merge_dict(dict(datos), overlay)
        return overlay or {}

    totales_proyecto = {}
    if proyectos_ids:
        for row in (
            Participacion.objects.filter(proyecto_id__in=proyectos_ids, estado="confirmada")
            .values("proyecto_id")
            .annotate(total=Sum("importe_invertido"))
        ):
            totales_proyecto[row["proyecto_id"]] = float(row.get("total") or 0)

    beneficios_por_proyecto = []
    total_beneficio = 0.0
    total_retencion = 0.0
    beneficio_chart = []
    for p in participaciones_conf:
        proyecto = p.proyecto
        if not proyecto:
            continue
        total_proj = totales_proyecto.get(proyecto.id, 0.0)
        if total_proj <= 0:
            continue
        snap = _get_snapshot(proyecto)
        resultado = _resultado_desde_memoria(proyecto, snap)
        beneficio_bruto = float(resultado.get("beneficio_neto") or 0.0)

        inv_sec = snap.get("inversor") if isinstance(snap.get("inversor"), dict) else {}
        comision_pct = _safe_float(
            inv_sec.get("comision_inversure_pct")
            or inv_sec.get("inversure_comision_pct")
            or inv_sec.get("comision_pct")
            or snap.get("comision_inversure_pct")
            or snap.get("inversure_comision_pct")
            or snap.get("comision_pct")
            or 0.0,
            0.0,
        )
        if comision_pct < 0:
            comision_pct = 0.0
        if comision_pct > 100:
            comision_pct = 100.0

        comision_eur = beneficio_bruto * (comision_pct / 100.0) if beneficio_bruto else 0.0
        beneficio_neto_inversor_total = beneficio_bruto - comision_eur

        proj_extra = proyecto.extra if isinstance(proyecto.extra, dict) else {}
        proj_override = proj_extra.get("beneficio_operacion_override")
        if isinstance(proj_override, dict):
            override_bruto = proj_override.get("beneficio_bruto")
            override_comision = proj_override.get("comision_eur")
            override_neto = proj_override.get("beneficio_neto_total")
            if override_bruto not in (None, ""):
                beneficio_bruto = _safe_float(override_bruto, beneficio_bruto)
            if override_comision not in (None, ""):
                comision_eur = _safe_float(override_comision, comision_eur)
            if override_neto not in (None, ""):
                beneficio_neto_inversor_total = _safe_float(override_neto, beneficio_neto_inversor_total)
            elif override_bruto not in (None, "") or override_comision not in (None, ""):
                beneficio_neto_inversor_total = beneficio_bruto - comision_eur

        ratio_part = float(p.importe_invertido or 0) / total_proj if total_proj > 0 else 0.0
        beneficio_inversor = beneficio_neto_inversor_total * ratio_part
        override_val = float(p.beneficio_neto_override) if p.beneficio_neto_override is not None else None
        override_data = p.beneficio_override_data if isinstance(p.beneficio_override_data, dict) else {}
        if override_data.get("beneficio_inversor") not in (None, ""):
            beneficio_inversor = _safe_float(override_data.get("beneficio_inversor"), beneficio_inversor)
        elif override_val is not None:
            beneficio_inversor = override_val
        retencion = beneficio_inversor * 0.19
        if override_data.get("retencion") not in (None, ""):
            retencion = _safe_float(override_data.get("retencion"), retencion)
        neto_cobrar = beneficio_inversor - retencion
        if override_data.get("neto_cobrar") not in (None, ""):
            neto_cobrar = _safe_float(override_data.get("neto_cobrar"), neto_cobrar)
        total_beneficio += beneficio_inversor
        total_retencion += retencion

        beneficios_por_proyecto.append(
            {
                "proyecto": proyecto,
                "beneficio_bruto": beneficio_bruto,
                "comision_eur": comision_eur,
                "beneficio_neto_total": beneficio_neto_inversor_total,
                "beneficio_inversor": beneficio_inversor,
                "beneficio_override": override_data.get("beneficio_inversor") if override_data.get("beneficio_inversor") not in (None, "") else override_val,
                "retencion": retencion,
                "neto_cobrar": neto_cobrar,
                "participacion_pct": ratio_part * 100.0,
                "participacion_id": p.id,
            }
        )

        fecha_ref = getattr(proyecto, "fecha", None) or getattr(p, "creado", None)
        if isinstance(fecha_ref, datetime):
            fecha_ref = fecha_ref.date().isoformat()
        elif isinstance(fecha_ref, date):
            fecha_ref = fecha_ref.isoformat()
        elif fecha_ref is not None:
            fecha_ref = str(fecha_ref)
        beneficio_chart.append(
            {
                "label": proyecto.nombre,
                "fecha": fecha_ref or "",
                "beneficio": beneficio_inversor,
                "inversion": float(p.importe_invertido or 0),
                "pct": (beneficio_inversor / float(p.importe_invertido or 0) * 100.0) if float(p.importe_invertido or 0) > 0 else 0.0,
            }
        )

    documentos_por_proyecto = []
    if proyectos_ids:
        docs = DocumentoProyecto.objects.filter(proyecto_id__in=proyectos_ids).exclude(categoria="fotografias")
        docs = docs.select_related("proyecto").order_by("-creado")
        docs_map = {}
        for d in docs:
            signed = _s3_presigned_url(d.archivo.name)
            setattr(d, "signed_url", signed or "")
            docs_map.setdefault(d.proyecto_id, {"proyecto": d.proyecto, "docs": []})["docs"].append(d)
        documentos_por_proyecto = list(docs_map.values())

    documentos_personales = []
    for d in DocumentoInversor.objects.filter(inversor=perfil).order_by("-creado"):
        signed = _s3_presigned_url(d.archivo.name)
        setattr(d, "signed_url", signed or "")
        documentos_personales.append(d)

    # --- Proyectos visibles en portal ---
    visible_ids = []
    try:
        if isinstance(perfil.proyectos_visibles, list):
            visible_ids = [int(v) for v in perfil.proyectos_visibles if str(v).isdigit()]
    except Exception:
        visible_ids = []

    candidatos_ids = list(proyectos_candidatos.values_list("id", flat=True))
    captado_map = {}
    if candidatos_ids:
        for row in (
            Participacion.objects.filter(proyecto_id__in=candidatos_ids, estado="confirmada")
            .values("proyecto_id")
            .annotate(total=Sum("importe_invertido"))
        ):
            captado_map[row["proyecto_id"]] = float(row.get("total") or 0.0)

    proyectos_abiertos = []
    for p in proyectos_candidatos:
        snap = _get_snapshot(p)

        # Capital objetivo: total de gastos (real/estimado) desde memoria
        capital_objetivo = _capital_objetivo_desde_memoria(p, snap)

        capital_captado = captado_map.get(p.id, 0.0)

        p.capital_objetivo = capital_objetivo
        p.capital_captado = capital_captado
        p.puede_solicitar = (capital_objetivo <= 0) or (capital_captado < capital_objetivo)
        if capital_objetivo > 0:
            faltante = max(capital_objetivo - capital_captado, 0.0)
            p.falta_eur = faltante
            p.falta_pct = max(0.0, min(100.0, (faltante / capital_objetivo) * 100.0))
        else:
            p.falta_eur = 0.0
            p.falta_pct = 0.0

        if visible_ids:
            if p.id in visible_ids:
                proyectos_abiertos.append(p)
        else:
            if internal_view:
                proyectos_abiertos.append(p)

    return {
        "perfil": perfil,
        "participaciones": participaciones,
        "comunicaciones": comunicaciones,
        "proyectos_abiertos": proyectos_abiertos,
        "proyectos_candidatos": proyectos_candidatos,
        "proyectos_participados": proyectos_participados,
        "proyectos_visibles": visible_ids,
        "solicitudes": solicitudes,
        "solicitudes_pendientes_list": solicitudes_pendientes_list,
        "solicitudes_pendientes": pendientes_count,
        "total_invertido": total_invertido,
        "aportacion_inicial": aportacion_inicial,
        "aportacion_inicial_override": perfil.aportacion_inicial_override,
        "beneficios_por_proyecto": beneficios_por_proyecto,
        "total_beneficio": total_beneficio,
        "total_retencion": total_retencion,
        "total_neto_cobrar": total_beneficio - total_retencion,
        "beneficio_chart": beneficio_chart,
        "documentos_por_proyecto": documentos_por_proyecto,
        "documentos_personales": documentos_personales,
        "logo_url": reverse("core:inversores_list"),
        "internal_view": internal_view,
    }


def inversor_portal(request, token: str):
    perfil = get_object_or_404(InversorPerfil, token=token, activo=True)
    ctx = _build_inversor_portal_context(perfil, internal_view=False)
    return render(request, "core/inversor_portal.html", ctx)


def inversor_portal_admin(request, perfil_id: int):
    perfil = get_object_or_404(InversorPerfil, id=perfil_id)
    ctx = _build_inversor_portal_context(perfil, internal_view=True)
    return render(request, "core/inversor_portal.html", ctx)


def inversor_portal_config(request, perfil_id: int):
    if request.method != "POST":
        return redirect("core:inversor_portal_admin", perfil_id=perfil_id)
    perfil = get_object_or_404(InversorPerfil, id=perfil_id)
    updated_fields = []

    if request.POST.get("visibilidad_submit"):
        ids = request.POST.getlist("proyectos_visibles")
        proyectos_ids = []
        for raw in ids:
            try:
                proyectos_ids.append(int(raw))
            except Exception:
                continue
        perfil.proyectos_visibles = proyectos_ids
        updated_fields.append("proyectos_visibles")

    if request.POST.get("aportacion_submit"):
        raw = (request.POST.get("aportacion_inicial_override") or "").strip()
        if raw == "":
            perfil.aportacion_inicial_override = None
        else:
            try:
                perfil.aportacion_inicial_override = _parse_decimal(raw)
            except Exception:
                messages.error(request, "No se pudo guardar la aportación inicial. Revisa el formato.")
                return redirect("core:inversor_portal_admin", perfil_id=perfil_id)
        updated_fields.append("aportacion_inicial_override")

    if updated_fields:
        perfil.save(update_fields=updated_fields)
        messages.success(request, "Ajustes del portal actualizados.")
    return redirect("core:inversor_portal_admin", perfil_id=perfil_id)


def inversor_documento_upload(request, perfil_id: int):
    if request.method != "POST":
        return redirect("core:inversores_list")
    perfil = get_object_or_404(InversorPerfil, id=perfil_id)
    titulo = (request.POST.get("doc_titulo") or "").strip()
    categoria = (request.POST.get("doc_categoria") or "otros").strip()
    archivo = request.FILES.get("doc_archivo")
    if not titulo or not archivo:
        messages.error(request, "Faltan datos para subir el documento.")
        return redirect("core:inversores_list")
    DocumentoInversor.objects.create(
        inversor=perfil,
        titulo=titulo,
        categoria=categoria,
        archivo=archivo,
    )
    messages.success(request, "Documento del inversor subido correctamente.")
    return redirect("core:inversores_list")


def inversor_documento_borrar(request, perfil_id: int, doc_id: int):
    if request.method != "POST":
        return redirect("core:inversores_list")
    perfil = get_object_or_404(InversorPerfil, id=perfil_id)
    documento = get_object_or_404(DocumentoInversor, id=doc_id, inversor=perfil)
    documento.delete()
    messages.success(request, "Documento del inversor eliminado correctamente.")
    return redirect("core:inversores_list")


def inversor_beneficio_update(request, token: str, participacion_id: int):
    perfil = get_object_or_404(InversorPerfil, token=token, activo=True)
    if request.method != "POST":
        return redirect("core:inversor_portal", token=token)

    participacion = get_object_or_404(Participacion, id=participacion_id, cliente=perfil.cliente)
    proyecto = participacion.proyecto

    def _get_decimal(name: str):
        if name not in request.POST:
            return None, False
        raw = (request.POST.get(name) or "").strip()
        if raw == "":
            return None, True
        try:
            return _parse_decimal(raw), True
        except Exception:
            return None, True

    # Compatibilidad: formulario antiguo
    legacy_val, legacy_present = _get_decimal("beneficio_neto")
    if legacy_present and set(request.POST.keys()).issubset({"csrfmiddlewaretoken", "beneficio_neto"}):
        if legacy_val is None and (request.POST.get("beneficio_neto") or "").strip() == "":
            participacion.beneficio_neto_override = None
            participacion.save(update_fields=["beneficio_neto_override"])
            messages.success(request, "Beneficio actualizado correctamente.")
            return redirect("core:inversor_portal", token=token)
        if legacy_val is None:
            messages.error(request, "El beneficio indicado no es válido.")
            return redirect("core:inversor_portal", token=token)
        participacion.beneficio_neto_override = legacy_val
        participacion.save(update_fields=["beneficio_neto_override"])
        messages.success(request, "Beneficio actualizado correctamente.")
        return redirect("core:inversor_portal", token=token)

    proj_keys = ("beneficio_bruto", "comision_eur", "beneficio_neto_total")
    inv_keys = ("beneficio_inversor", "retencion", "neto_cobrar")

    extra = proyecto.extra if isinstance(proyecto.extra, dict) else {}
    proj_override = extra.get("beneficio_operacion_override")
    if not isinstance(proj_override, dict):
        proj_override = {}

    updated_proj = False
    for key in proj_keys:
        value, present = _get_decimal(key)
        if not present:
            continue
        if value is None:
            proj_override.pop(key, None)
        else:
            proj_override[key] = float(value)
        updated_proj = True

    if updated_proj:
        if proj_override:
            extra["beneficio_operacion_override"] = proj_override
        else:
            extra.pop("beneficio_operacion_override", None)
        proyecto.extra = extra
        proyecto.save(update_fields=["extra"])

    override_data = participacion.beneficio_override_data if isinstance(participacion.beneficio_override_data, dict) else {}
    updated_inv = False
    for key in inv_keys:
        value, present = _get_decimal(key)
        if not present:
            continue
        if value is None:
            override_data.pop(key, None)
        else:
            override_data[key] = float(value)
        updated_inv = True

    if updated_inv:
        participacion.beneficio_override_data = override_data
        beneficio_override_val = override_data.get("beneficio_inversor")
        if beneficio_override_val is None and "beneficio_inversor" not in override_data:
            participacion.beneficio_neto_override = None
        elif beneficio_override_val is not None:
            participacion.beneficio_neto_override = beneficio_override_val
        participacion.save(update_fields=["beneficio_override_data", "beneficio_neto_override"])

    messages.success(request, "Beneficio actualizado correctamente.")
    return redirect("core:inversor_portal", token=token)


def inversor_solicitar(request, token: str, proyecto_id: int):
    perfil = get_object_or_404(InversorPerfil, token=token, activo=True)
    proyecto = get_object_or_404(Proyecto, id=proyecto_id)
    if request.method != "POST":
        return redirect("core:inversor_portal", token=token)

    # Validar visibilidad del proyecto en el portal
    visibles = []
    try:
        if isinstance(perfil.proyectos_visibles, list):
            visibles = [int(v) for v in perfil.proyectos_visibles if str(v).isdigit()]
    except Exception:
        visibles = []
    if visibles and proyecto.id not in visibles:
        messages.error(request, "Este proyecto no está disponible para inversión.")
        return redirect("core:inversor_portal", token=token)

    # Bloquear si la inversión ya está completa
    try:
        snap = {}
        sd = getattr(proyecto, "snapshot_datos", None)
        if isinstance(sd, dict):
            snap = sd
        capital_objetivo = _capital_objetivo_desde_memoria(proyecto, snap)

        captado = Participacion.objects.filter(
            proyecto=proyecto, estado="confirmada"
        ).aggregate(total=Sum("importe_invertido")).get("total") or 0
        captado = _safe_float(captado, 0.0)

        if capital_objetivo > 0 and captado >= capital_objetivo:
            messages.error(request, "La inversión de este proyecto está completa.")
            return redirect("core:inversor_portal", token=token)
    except Exception:
        pass

    importe = _parse_decimal(request.POST.get("importe"))
    comentario = (request.POST.get("comentario") or "").strip()
    if importe is None:
        messages.error(request, "Indica un importe válido.")
        return redirect("core:inversor_portal", token=token)

    SolicitudParticipacion.objects.create(
        proyecto=proyecto,
        inversor=perfil,
        importe_solicitado=importe,
        comentario=comentario or None,
    )
    messages.success(request, "Solicitud enviada correctamente.")
    return redirect("core:inversor_portal", token=token)


@ensure_csrf_cookie
def proyecto(request, proyecto_id: int):
    """Vista única del Proyecto (pestañas), heredando el snapshot del estudio convertido."""
    proyecto_obj = get_object_or_404(Proyecto, id=proyecto_id)
    if is_comercial_user(request.user) and not is_admin_user(request.user) and not use_custom_permissions(request.user):
        if not getattr(proyecto_obj, "acceso_comercial", False):
            messages.error(request, "Este proyecto no está habilitado para el equipo comercial.")
            return redirect("core:lista_proyectos")

    # --- Compatibilidad de plantilla: algunos campos pueden no existir en el modelo Proyecto ---
    # Django templates fallan con VariableDoesNotExist si se accede a un atributo inexistente.
    # Definimos atributos "dummy" para que la plantilla no rompa (los valores reales vendrán del snapshot).
    _tpl_expected_fields = [
        "venta_estimada",
        "precio_propiedad",
        "precio_compra_inmueble",
        "precio_venta_estimado",
        "notaria",
        "registro",
        "itp",
        "direccion",
        "ref_catastral",
        "valor_referencia",
        "meses",
        "financiacion_pct",
        "responsable",
    ]
    for _f in _tpl_expected_fields:
        if not hasattr(proyecto_obj, _f):
            setattr(proyecto_obj, _f, "")

    # Snapshot efectivo del proyecto (prioridad):
    # 1) Último ProyectoSnapshot (guardados/versionado)
    # 2) snapshot_datos (copia inmutable heredada)
    # 3) origen_snapshot.datos
    # 4) origen_estudio.datos
    snapshot: dict = {}
    try:
        last_ps = ProyectoSnapshot.objects.filter(proyecto=proyecto_obj).order_by("-version_num", "-id").first()
        if last_ps is not None:
            ps_d = getattr(last_ps, "datos", None)
            if isinstance(ps_d, dict) and ps_d:
                snapshot = ps_d

        if not snapshot:
            sd = getattr(proyecto_obj, "snapshot_datos", None)
            if isinstance(sd, dict) and sd:
                snapshot = sd

        if not snapshot:
            osnap = getattr(proyecto_obj, "origen_snapshot", None)
            if osnap is not None:
                od = getattr(osnap, "datos", None)
                if isinstance(od, dict) and od:
                    snapshot = od

        if not snapshot:
            oest = getattr(proyecto_obj, "origen_estudio", None)
            if oest is not None:
                ed = getattr(oest, "datos", None)
                if isinstance(ed, dict) and ed:
                    snapshot = ed
    except Exception:
        snapshot = {}

    # --- Normalización defensiva del snapshot y KPIs ---
    if not isinstance(snapshot, dict):
        snapshot = {}

    # --- Overlay persistente (ediciones del proyecto) ---
    # Si el usuario guardó cambios operativos del proyecto, los almacenamos en `Proyecto.extra`
    # y deben re-hidratar la vista al recargar la página.
    overlay = {}
    try:
        # 1) Preferimos `Proyecto.extra` si existe
        extra = getattr(proyecto_obj, "extra", None)
        if isinstance(extra, dict):
            ultimo = extra.get("ultimo_guardado")
            if isinstance(ultimo, dict) and isinstance(ultimo.get("payload"), dict):
                overlay = ultimo.get("payload") or {}

        # 2) Fallback: si no hay `extra`, buscamos overlay persistido dentro de `snapshot_datos`
        if not overlay:
            sd = getattr(proyecto_obj, "snapshot_datos", None)
            if isinstance(sd, dict) and isinstance(sd.get("_overlay"), dict):
                overlay = sd.get("_overlay") or {}
    except Exception:
        overlay = {}

    if overlay:
        merged_snapshot = deepcopy(snapshot) if isinstance(snapshot, dict) else {}
        merged_snapshot = _deep_merge_dict(merged_snapshot, overlay)
        snapshot = merged_snapshot
        try:
            if not getattr(proyecto_obj, "responsable", "") and overlay.get("responsable"):
                setattr(proyecto_obj, "responsable", overlay.get("responsable"))
        except Exception:
            pass
        try:
            if overlay.get("proyecto", {}).get("estado") and not getattr(proyecto_obj, "estado", ""):
                proyecto_obj.estado = overlay["proyecto"]["estado"]
            if overlay.get("proyecto", {}).get("fecha") and not getattr(proyecto_obj, "fecha", None):
                proyecto_obj.fecha = _parse_date(overlay["proyecto"]["fecha"])
            if overlay.get("proyecto", {}).get("responsable") and not getattr(proyecto_obj, "responsable", ""):
                setattr(proyecto_obj, "responsable", overlay["proyecto"]["responsable"])
        except Exception:
            pass
    # --- Forzar nombre persistido del PROYECTO en el snapshot renderizado ---
    # Evita que al recargar se muestre el nombre heredado del estudio.
    try:
        nombre_p = (getattr(proyecto_obj, "nombre", "") or "").strip()
    except Exception:
        nombre_p = ""

    if nombre_p:
        if not isinstance(snapshot, dict):
            snapshot = {}

        if not isinstance(snapshot.get("proyecto"), dict):
            snapshot["proyecto"] = {}
        snapshot["proyecto"]["nombre"] = nombre_p
        snapshot["proyecto"]["nombre_proyecto"] = nombre_p

        if not isinstance(snapshot.get("inmueble"), dict):
            snapshot["inmueble"] = {}
        snapshot["inmueble"]["nombre_proyecto"] = nombre_p
    kpis_raw = snapshot.get("kpis")
    if not isinstance(kpis_raw, dict):
        kpis_raw = {}
        snapshot["kpis"] = kpis_raw

    if not isinstance(kpis_raw.get("metricas"), dict):
        kpis_raw["metricas"] = {}

    # Exponer `metricas` como atajo seguro para la plantilla proyecto.html
    metricas_raw = kpis_raw.get("metricas") if isinstance(kpis_raw.get("metricas"), dict) else {}

    # --- Resultado de inversión para dashboard / vista proyecto ---
    resultado = {}
    try:
        snap_result = snapshot.get("resultado") if isinstance(snapshot.get("resultado"), dict) else {}
        calc = _metricas_desde_estudio(Estudio(datos=snapshot))
        metricas_calc = calc.get("metricas", {}) if isinstance(calc.get("metricas"), dict) else {}
        resultado_calc = _resultado_desde_metricas(metricas_calc)
        resultado = dict(resultado_calc)
        try:
            resultado_memoria = _resultado_desde_memoria(proyecto_obj, snapshot)
            for k, v in resultado_memoria.items():
                if v not in (None, ""):
                    resultado[k] = v
        except Exception:
            pass
        if isinstance(snap_result, dict):
            for k, v in snap_result.items():
                if v not in (None, "", []):
                    resultado[k] = v
    except Exception:
        resultado = snapshot.get("resultado") if isinstance(snapshot.get("resultado"), dict) else {}

    inv_calc = {}
    try:
        inv_calc = calc.get("inversor") if isinstance(calc.get("inversor"), dict) else {}
    except Exception:
        inv_calc = {}
    try:
        inv_snap = snapshot.get("inversor") if isinstance(snapshot.get("inversor"), dict) else {}
    except Exception:
        inv_snap = {}
    if isinstance(inv_snap, dict) and isinstance(inv_calc, dict):
        for k, v in inv_snap.items():
            if k not in inv_calc or inv_calc.get(k) in (None, ""):
                inv_calc[k] = v

    # --- Estado inicial para hidratar el simulador en modo proyecto ---
    estado_inicial = {}
    try:
        if isinstance(snapshot, dict) and snapshot:
            # Si el snapshot ya incluye un bloque snapshot (overlay completo), lo preferimos
            estado_inicial = snapshot.get("snapshot") if isinstance(snapshot.get("snapshot"), dict) else snapshot
    except Exception:
        estado_inicial = {}

    # --- Editabilidad del proyecto ---
    # En proyecto (fase operativa) el formulario debe ser editable por defecto.
    # Solo lo bloqueamos si existe un campo de estado/cierre que indique finalización.
    editable = True
    try:
        username = (getattr(request.user, "username", "") or "").strip().lower()
        if username == "mperez":
            editable = True
        else:
            estado = (getattr(proyecto_obj, "estado", "") or "").strip().lower()
            # Estados típicos de cierre (ajústalos si tu modelo usa otros nombres)
            if estado in {"cerrado", "cerrado_positivo", "cerrado_negativo", "finalizado", "descartado"}:
                editable = False
    except Exception:
        editable = True

    # --- Captación / Progreso de inversión (robusto) ---
    # Objetivo: lo que se pretende captar (normalmente la inversión total)
    try:
        inv_sec = snapshot.get("inversor") if isinstance(snapshot.get("inversor"), dict) else {}
        kpis_sec = snapshot.get("kpis") if isinstance(snapshot.get("kpis"), dict) else {}
        met_sec = kpis_sec.get("metricas") if isinstance(kpis_sec.get("metricas"), dict) else {}

        # Capital objetivo: total de gastos (real/estimado) desde memoria
        capital_objetivo = _capital_objetivo_desde_memoria(proyecto_obj, snapshot)

        # Capital captado: suma de participaciones confirmadas (si existe el módulo)
        capital_captado_db = Participacion.objects.filter(
            proyecto=proyecto_obj, estado="confirmada"
        ).aggregate(total=Sum("importe_invertido")).get("total") or 0
        capital_captado_db = _safe_float(capital_captado_db, 0.0)

        # Capital captado: si aún no hay módulo de inversores, por defecto 0
        cap_sec = snapshot.get("captacion") if isinstance(snapshot.get("captacion"), dict) else {}
        capital_captado = _safe_float(
            cap_sec.get("capital_captado")
            or cap_sec.get("captado")
            or inv_sec.get("capital_captado")
            or inv_sec.get("captado")
            or met_sec.get("capital_captado")
            or 0.0,
            0.0,
        )
        if capital_captado_db > 0:
            capital_captado = capital_captado_db

        # Normalizar
        if capital_objetivo < 0:
            capital_objetivo = 0.0
        if capital_captado < 0:
            capital_captado = 0.0

        # % captado
        if capital_objetivo > 0:
            pct_captado = (capital_captado / capital_objetivo) * 100.0
        else:
            pct_captado = 0.0

        # clamp 0..100
        if pct_captado < 0:
            pct_captado = 0.0
        if pct_captado > 100:
            pct_captado = 100.0

        restante = max(capital_objetivo - capital_captado, 0.0)
        pct_restante = max(0.0, 100.0 - pct_captado)

        captacion_ctx = SafeAccessDict({
            "capital_objetivo": capital_objetivo,
            "capital_captado": capital_captado,
            "pct_captado": pct_captado,
            "restante": restante,
            "pct_restante": pct_restante,
            "capital_objetivo_fmt": _fmt_eur(capital_objetivo),
            "capital_captado_fmt": _fmt_eur(capital_captado),
            "restante_fmt": _fmt_eur(restante),
            "pct_captado_fmt": _fmt_pct(pct_captado),
            "pct_restante_fmt": _fmt_pct(pct_restante),
        })
    except Exception:
        captacion_ctx = SafeAccessDict({
            "capital_objetivo": 0.0,
            "capital_captado": 0.0,
            "pct_captado": 0.0,
            "restante": 0.0,
            "pct_restante": 0.0,
            "capital_objetivo_fmt": _fmt_eur(0.0),
            "capital_captado_fmt": _fmt_eur(0.0),
            "restante_fmt": _fmt_eur(0.0),
            "pct_captado_fmt": _fmt_pct(0.0),
            "pct_restante_fmt": _fmt_pct(0.0),
        })

    notify_flag = True
    try:
        extra = getattr(proyecto_obj, "extra", None)
        if isinstance(extra, dict) and "notificar_inversores" in extra:
            notify_flag = bool(extra.get("notificar_inversores"))
        elif isinstance(snapshot, dict):
            sec = snapshot.get("proyecto") if isinstance(snapshot.get("proyecto"), dict) else {}
            if "notificar_inversores" in sec:
                notify_flag = bool(sec.get("notificar_inversores"))
    except Exception:
        notify_flag = True

    ctx = {
        "PROYECTO_ID": str(proyecto_obj.id),
        "ESTADO_INICIAL_JSON": json.dumps(estado_inicial, ensure_ascii=False),
        "editable": editable,
        "is_admin": is_admin_user(request.user),
        "can_manage_difusion": is_admin_user(request.user) or use_custom_permissions(request.user),
        "acceso_comercial": bool(getattr(proyecto_obj, "acceso_comercial", False)),
        "proyecto": proyecto_obj,
        "notificar_inversores": notify_flag,
        "snapshot": _safe_template_obj(snapshot),
        # Atajos por si `proyecto.html` los usa como en el PDF/estudio
        "inmueble": _safe_template_obj(snapshot.get("inmueble", {})) if isinstance(snapshot.get("inmueble"), dict) else SafeAccessDict(),
        "economico": _safe_template_obj(snapshot.get("economico", {})) if isinstance(snapshot.get("economico"), dict) else SafeAccessDict(),
        "inversor": _safe_template_obj(inv_calc) if isinstance(inv_calc, dict) else SafeAccessDict(),
        "inv": _safe_template_obj(inv_calc) if isinstance(inv_calc, dict) else SafeAccessDict(),
        "comite": _safe_template_obj(snapshot.get("comite", {})) if isinstance(snapshot.get("comite"), dict) else SafeAccessDict(),
        "kpis": _safe_template_obj(snapshot.get("kpis", {})) if isinstance(snapshot.get("kpis"), dict) else SafeAccessDict(),
        "metricas": _safe_template_obj(metricas_raw) if isinstance(metricas_raw, dict) else SafeAccessDict(),
        "resultado": _safe_template_obj(resultado) if isinstance(resultado, dict) else SafeAccessDict(),
        "captacion": captacion_ctx,
        "capital_objetivo": captacion_ctx.get("capital_objetivo"),
        "capital_captado": captacion_ctx.get("capital_captado"),
        "pct_captado": captacion_ctx.get("pct_captado"),
    }
    try:
        extra = getattr(proyecto_obj, "extra", None)
        landing_config = extra.get("landing", {}) if isinstance(extra, dict) else {}
        if not landing_config and isinstance(overlay, dict):
            landing_config = overlay.get("landing", {}) or {}
        ctx["landing_config"] = landing_config if isinstance(landing_config, dict) else {}
        publicaciones_config = extra.get("publicaciones", {}) if isinstance(extra, dict) else {}
        if not publicaciones_config and isinstance(overlay, dict):
            publicaciones_config = overlay.get("publicaciones", {}) or {}
        ctx["publicaciones_config"] = publicaciones_config if isinstance(publicaciones_config, dict) else {}
        difusion_config = extra.get("difusion", {}) if isinstance(extra, dict) else {}
        if not difusion_config and isinstance(overlay, dict):
            difusion_config = overlay.get("difusion", {}) or {}
        ctx["difusion_config"] = difusion_config if isinstance(difusion_config, dict) else {}
        anexos_map = difusion_config.get("anexos") if isinstance(difusion_config, dict) else {}
        if isinstance(anexos_map, dict):
            ctx["difusion_anexos_ids"] = {str(k) for k, v in anexos_map.items() if v}
        else:
            ctx["difusion_anexos_ids"] = set()
    except Exception:
        ctx["landing_config"] = {}
        ctx["publicaciones_config"] = {}
        ctx["difusion_config"] = {}
        ctx["difusion_anexos_ids"] = set()

    try:
        _ensure_checklist_defaults(proyecto_obj)
        ctx["checklist_items"] = ChecklistItem.objects.filter(proyecto=proyecto_obj).order_by("fase", "fecha_objetivo", "id")
    except Exception:
        ctx["checklist_items"] = []
    try:
        ctx["clientes"] = Cliente.objects.all().order_by("nombre")
    except Exception:
        ctx["clientes"] = []
    try:
        ctx["difusion_clientes_ids"] = list(
            proyecto_obj.difusion_clientes.values_list("id", flat=True)
        )
    except Exception:
        ctx["difusion_clientes_ids"] = []
    try:
        participaciones = list(
            Participacion.objects.filter(proyecto=proyecto_obj)
            .select_related("cliente")
            .order_by("-id")
        )
        capital_objetivo = _parse_decimal(captacion_ctx.get("capital_objetivo")) or Decimal("0")
        total_confirmadas = (
            Participacion.objects.filter(proyecto=proyecto_obj, estado="confirmada")
            .aggregate(total=Sum("importe_invertido"))
            .get("total")
            or Decimal("0")
        )
        total_confirmadas = _parse_decimal(total_confirmadas) or Decimal("0")
        for p in participaciones:
            pct = None
            if capital_objetivo > 0:
                pct = (p.importe_invertido / capital_objetivo) * Decimal("100")
            elif total_confirmadas > 0:
                pct = (p.importe_invertido / total_confirmadas) * Decimal("100")
            if pct is not None:
                p.porcentaje_participacion = pct
        ctx["participaciones"] = participaciones
    except Exception:
        ctx["participaciones"] = []
    try:
        ctx["solicitudes_pendientes_count"] = SolicitudParticipacion.objects.filter(
            proyecto=proyecto_obj,
            estado="pendiente",
        ).count()
    except Exception:
        ctx["solicitudes_pendientes_count"] = 0
    try:
        documentos = list(DocumentoProyecto.objects.filter(proyecto=proyecto_obj).order_by("-creado", "-id"))
        use_signed = False
        try:
            use_signed = bool(getattr(settings, "AWS_STORAGE_BUCKET_NAME", None))
        except Exception:
            use_signed = False
        if use_signed:
            for doc in documentos:
                try:
                    key = getattr(doc.archivo, "name", "") or ""
                    signed = _s3_presigned_url(key)
                    if signed:
                        doc.signed_url = signed
                except Exception:
                    pass
        categorias_map = {}
        for doc in documentos:
            cat = getattr(doc, "categoria", "otros") or "otros"
            categorias_map.setdefault(cat, []).append(doc)
        ctx["documentos_por_categoria"] = categorias_map
        ctx["documentos"] = documentos
        principal = next((d for d in documentos if d.categoria == "fotografias" and d.es_principal), None)
        if principal is None:
            principal = next((d for d in documentos if d.categoria == "fotografias"), None)
        if principal:
            try:
                ctx["foto_principal_url"] = principal.signed_url if hasattr(principal, "signed_url") and principal.signed_url else principal.archivo.url
                ctx["foto_principal_titulo"] = principal.titulo
            except Exception:
                pass
        try:
            publicaciones_config = ctx.get("publicaciones_config") if isinstance(ctx.get("publicaciones_config"), dict) else {}
            cabecera_id = publicaciones_config.get("cabecera_imagen_id")
            if cabecera_id:
                cabecera_doc = next(
                    (d for d in documentos if str(d.id) == str(cabecera_id) and d.categoria == "fotografias"),
                    None,
                )
                if cabecera_doc:
                    ctx["foto_principal_url"] = cabecera_doc.signed_url if hasattr(cabecera_doc, "signed_url") and cabecera_doc.signed_url else cabecera_doc.archivo.url
                    ctx["foto_principal_titulo"] = cabecera_doc.titulo
        except Exception:
            pass
        try:
            fotos_docs = []
            for doc in documentos:
                if doc.categoria != "fotografias":
                    continue
                archivo_url = None
                try:
                    archivo_url = doc.signed_url if hasattr(doc, "signed_url") and doc.signed_url else doc.archivo.url
                except Exception:
                    archivo_url = None
                fotos_docs.append({
                    "id": doc.id,
                    "titulo": doc.titulo,
                    "archivo_url": archivo_url,
                })
            ctx["fotos_docs"] = fotos_docs
        except Exception:
            ctx["fotos_docs"] = []

        try:
            landing_config = ctx.get("landing_config") if isinstance(ctx.get("landing_config"), dict) else {}
            landing_img_id = landing_config.get("imagen_id")
            landing_preview_url = None
            if landing_img_id:
                landing_doc = next(
                    (d for d in documentos if str(d.id) == str(landing_img_id) and d.categoria == "fotografias"),
                    None,
                )
                if landing_doc:
                    landing_preview_url = landing_doc.signed_url if hasattr(landing_doc, "signed_url") and landing_doc.signed_url else landing_doc.archivo.url
            if not landing_preview_url and principal:
                landing_preview_url = principal.signed_url if hasattr(principal, "signed_url") and principal.signed_url else principal.archivo.url
            ctx["landing_preview_url"] = landing_preview_url
        except Exception:
            ctx["landing_preview_url"] = None
        try:
            facturas_docs = []
            for doc in documentos:
                if doc.categoria != "facturas":
                    continue
                archivo_url = None
                try:
                    archivo_url = doc.signed_url if hasattr(doc, "signed_url") and doc.signed_url else doc.archivo.url
                except Exception:
                    archivo_url = None
                facturas_docs.append({
                    "id": doc.id,
                    "titulo": doc.titulo,
                    "fecha": doc.fecha_factura.isoformat() if doc.fecha_factura else None,
                    "importe": float(doc.importe_factura) if doc.importe_factura is not None else None,
                    "archivo_url": archivo_url,
                })
            ctx["facturas_docs"] = facturas_docs
        except Exception:
            ctx["facturas_docs"] = []
    except Exception:
        ctx["documentos"] = []
    try:
        facturas = []
        for factura in FacturaGasto.objects.select_related("gasto").filter(gasto__proyecto=proyecto_obj).order_by("-fecha_subida", "-id"):
            factura_url = None
            try:
                key = getattr(factura.archivo, "name", "") or ""
                signed = _s3_presigned_url(key)
                factura_url = signed if signed else factura.archivo.url
            except Exception:
                factura_url = None
            facturas.append({
                "id": factura.id,
                "gasto_id": factura.gasto_id,
                "concepto": factura.gasto.concepto if factura.gasto else "—",
                "fecha": factura.gasto.fecha if factura.gasto else None,
                "importe": factura.gasto.importe if factura.gasto else None,
                "archivo_url": factura_url,
                "nombre": factura.nombre_original or (os.path.basename(factura.archivo.name) if factura.archivo else "Factura"),
            })
        ctx["facturas_gasto"] = facturas
    except Exception:
        ctx["facturas_gasto"] = []

    return render(request, "core/proyecto.html", ctx)


@csrf_exempt
def guardar_estudio(request):
    if request.method != "POST":
        return JsonResponse({"ok": False, "error": "Método no permitido"}, status=405)

    try:
        data = json.loads(request.body or "{}")

        # Puede venir como `id` o puede no venir (si el frontend perdió el ID).
        # Para evitar duplicados, si no llega ID usamos el estudio activo en sesión.
        estudio_id = data.get("id") or data.get("estudio_id") or data.get("ESTUDIO_ID")
        if not estudio_id:
            estudio_id = request.session.get("estudio_id")

        # Si el estudio está bloqueado (ya convertido a proyecto), no permitimos cambios.
        if estudio_id:
            try:
                _e0 = Estudio.objects.only("id", "bloqueado").get(id=estudio_id)
                if getattr(_e0, "bloqueado", False):
                    return JsonResponse(
                        {"ok": False, "error": "Este estudio está bloqueado porque ya se convirtió en proyecto."},
                        status=409,
                    )
            except Estudio.DoesNotExist:
                pass

        # Aceptar tanto las keys antiguas como las del formulario actual (simulador.html)
        nombre = (
            data.get("nombre")
            or data.get("nombre_proyecto")
            or data.get("proyecto_nombre")
            or ""
        ).strip()

        direccion = (
            data.get("direccion")
            or data.get("direccion_completa")
            or data.get("proyecto_direccion")
            or ""
        ).strip()

        ref_catastral = (
            data.get("ref_catastral")
            or data.get("referencia_catastral")
            or data.get("ref_catastral_inmueble")
            or ""
        ).strip()

        # `datos` siempre debe ser dict
        datos = data.get("datos", {}) or {}
        if not isinstance(datos, dict):
            datos = {}

        # --- HIDRATAR SNAPSHOT CANÓNICO PARA PDF / PROYECTO ---
        # Garantiza que inversor, kpis y economico NUNCA sean strings vacíos
        try:
            fake_estudio = Estudio(
                datos=datos,
                valor_referencia=None,
            )

            kpis = _metricas_desde_estudio(fake_estudio)
            inmueble = _datos_inmueble_desde_estudio(fake_estudio)

            snapshot = {
                "inmueble": inmueble,
                "economico": kpis.get("metricas", {}),
                "kpis": {
                    "metricas": kpis.get("metricas", {}),
                    "metricas_fmt": kpis.get("metricas_fmt", {}),
                },
                "inversor": kpis.get("inversor", {}),
                "comite": datos.get("comite", {}) if isinstance(datos.get("comite"), dict) else {},
                "resultado": kpis.get("resultado", {}),
                "texto": kpis.get("texto", {}),
                "reparto": kpis.get("reparto", {}),
            }

            # Preservar campos operativos no calculados (p.ej. meses/financiación)
            meses_raw = datos.get("meses") or datos.get("meses_operacion") or datos.get("meses_operación")
            financiacion_raw = datos.get("financiacion_pct") or datos.get("porcentaje_financiacion")
            if meses_raw not in (None, ""):
                snapshot["economico"]["meses"] = meses_raw
            if financiacion_raw not in (None, ""):
                snapshot["economico"]["financiacion_pct"] = financiacion_raw

            # Forzar snapshot y secciones críticas
            datos["snapshot"] = snapshot
            datos["inversor"] = snapshot.get("inversor", {})
            if not isinstance(datos.get("economico"), dict):
                datos["economico"] = {}
            datos["economico"] = _deep_merge_dict(datos["economico"], snapshot.get("economico", {}))
            datos["kpis"] = snapshot.get("kpis", {})

        except Exception:
            # En caso extremo, evitar que inversor sea string
            if not isinstance(datos.get("inversor"), dict):
                datos["inversor"] = {}
            if not isinstance(datos.get("economico"), dict):
                datos["economico"] = {}
            if not isinstance(datos.get("kpis"), dict):
                datos["kpis"] = {}

        # --- Compatibilidad: payloads que envían secciones en la raíz (no dentro de `datos`) ---
        # Hay campos editables (p.ej. comisión) que deben sobrescribir valores existentes.
        ALWAYS_OVERWRITE_KEYS = {
            # comisión Inversure (porcentaje / euros)
            "comision_inversure_pct",
            "inversure_comision_pct",
            "comision_pct",
            "comision_inversure_eur",
            "inversure_comision_eur",
            "comision_eur",
            # variantes usadas en diferentes pantallas
            "comision_inversure",
            "comision_inversure_sobre_beneficio",
            "comision_inversure_sobre_beneficio_pct",
            "comision_inversure_sobre_beneficio_eur",
        }

        for _root_sec in ("inmueble", "economico", "comite", "inversor", "kpis", "tecnico", "proyecto"):
            sec_val = data.get(_root_sec)
            if isinstance(sec_val, dict):
                if _root_sec not in datos or not isinstance(datos.get(_root_sec), dict):
                    datos[_root_sec] = {}
                for kk, vv in sec_val.items():
                    if kk in ALWAYS_OVERWRITE_KEYS:
                        datos[_root_sec][kk] = vv
                    else:
                        if kk not in datos[_root_sec] or datos[_root_sec].get(kk) in (None, ""):
                            datos[_root_sec][kk] = vv

        # Aplanar secciones por compatibilidad (algunos templates esperan keys en raíz)
        def _flatten_section(section_key: str) -> None:
            sec = datos.get(section_key)
            if isinstance(sec, dict):
                for kk, vv in sec.items():
                    if kk in ALWAYS_OVERWRITE_KEYS:
                        datos[kk] = vv
                    else:
                        if kk not in datos or datos.get(kk) in (None, ""):
                            datos[kk] = vv

        for _sec in ("tecnico", "economico", "comite", "inversor", "kpis", "inmueble", "proyecto"):
            _flatten_section(_sec)

        # Normalizar decisiones de comité si llegan con claves alternativas
        if isinstance(datos.get("comite"), dict):
            comite_sec = datos["comite"]
            if comite_sec.get("decision") in (None, "") and comite_sec.get("decision_estado") not in (None, ""):
                comite_sec["decision"] = comite_sec.get("decision_estado")
            if comite_sec.get("observaciones") in (None, ""):
                if comite_sec.get("comentario") not in (None, ""):
                    comite_sec["observaciones"] = comite_sec.get("comentario")
                elif comite_sec.get("resumen_ejecutivo") not in (None, ""):
                    comite_sec["observaciones"] = comite_sec.get("resumen_ejecutivo")
            if comite_sec.get("resumen_ejecutivo") in (None, "") and comite_sec.get("resumen_ejecutivo_comite") not in (None, ""):
                comite_sec["resumen_ejecutivo"] = comite_sec.get("resumen_ejecutivo_comite")

        # Absorber `datos.snapshot` si existe
        snap = datos.get("snapshot") if isinstance(datos.get("snapshot"), dict) else {}
        if snap:
            for kk, vv in snap.items():
                if kk == "comite":
                    continue
                if kk not in datos or datos.get(kk) in (None, ""):
                    datos[kk] = vv

            if isinstance(snap.get("comite"), dict):
                if "comite" not in datos or not isinstance(datos.get("comite"), dict):
                    datos["comite"] = {}
                for kk, vv in snap["comite"].items():
                    if kk not in datos["comite"] or datos["comite"].get(kk) in (None, ""):
                        datos["comite"][kk] = vv

                for kk in (
                    "decision",
                    "decision_texto",
                    "recomendacion",
                    "nivel_riesgo",
                    "comentario",
                    "observaciones",
                ):
                    if kk in datos["comite"] and (kk not in datos or datos.get(kk) in (None, "")):
                        datos[kk] = datos["comite"].get(kk)

        # Fallback de campos principales desde `datos` (para que lista_estudio tenga nombre/dirección)
        def _get_str_from(*vals) -> str:
            for v in vals:
                if v is None:
                    continue
                if isinstance(v, str):
                    s = v.strip()
                    if s:
                        return s
                else:
                    s = str(v).strip()
                    if s:
                        return s
            return ""

        inmueble_sec = datos.get("inmueble") if isinstance(datos.get("inmueble"), dict) else {}
        proyecto_sec = datos.get("proyecto") if isinstance(datos.get("proyecto"), dict) else {}

        if not nombre:
            nombre = _get_str_from(
                datos.get("nombre"),
                datos.get("nombre_proyecto"),
                proyecto_sec.get("nombre"),
                proyecto_sec.get("nombre_proyecto"),
                inmueble_sec.get("nombre"),
                inmueble_sec.get("nombre_proyecto"),
                datos.get("proyecto_nombre"),
                datos.get("proyecto"),
            )

        if not direccion:
            direccion = _get_str_from(
                datos.get("direccion"),
                datos.get("direccion_completa"),
                proyecto_sec.get("direccion"),
                proyecto_sec.get("direccion_completa"),
                inmueble_sec.get("direccion"),
                inmueble_sec.get("direccion_completa"),
                datos.get("proyecto_direccion"),
            )

        if not ref_catastral:
            ref_catastral = _get_str_from(
                datos.get("ref_catastral"),
                datos.get("referencia_catastral"),
                proyecto_sec.get("ref_catastral"),
                proyecto_sec.get("referencia_catastral"),
                inmueble_sec.get("ref_catastral"),
                inmueble_sec.get("referencia_catastral"),
            )

        # Valor de referencia (opcional)
        valor_referencia_raw = (
            data.get("valor_referencia")
            or datos.get("valor_referencia")
            or proyecto_sec.get("valor_referencia")
            or inmueble_sec.get("valor_referencia")
            or data.get("valor_referencia_catastral")
            or datos.get("valor_referencia_catastral")
        )
        valor_referencia = None
        if valor_referencia_raw not in (None, ""):
            try:
                # admitir formatos es-ES "231.369,24"
                if isinstance(valor_referencia_raw, str):
                    s = valor_referencia_raw.strip().replace("€", "").strip()
                    if "." in s and "," in s:
                        s = s.replace(".", "").replace(",", ".")
                    else:
                        s = s.replace(",", ".")
                    valor_referencia = Decimal(s)
                else:
                    valor_referencia = Decimal(str(valor_referencia_raw))
            except Exception:
                valor_referencia = None

        # Sanear datos para JSONField
        datos = _sanitize_for_json(datos)

        # Guardar (actualizando el borrador existente para NO duplicar)
        if estudio_id:
            try:
                estudio_obj = Estudio.objects.get(id=int(estudio_id))
            except Exception:
                estudio_obj = None
        else:
            estudio_obj = None

        if estudio_obj is None:
            # Si por algún motivo no existe borrador, creamos uno nuevo
            estudio_obj = Estudio.objects.create(
                nombre=nombre,
                direccion=direccion,
                ref_catastral=ref_catastral,
                valor_referencia=valor_referencia,
                datos=datos,
                guardado=True,
            )
        else:
            estudio_obj.nombre = nombre
            estudio_obj.direccion = direccion
            estudio_obj.ref_catastral = ref_catastral
            if valor_referencia is not None:
                estudio_obj.valor_referencia = valor_referencia
            estudio_obj.datos = datos
            estudio_obj.guardado = True
            estudio_obj.save()

        # Asegurar sesión apuntando al estudio guardado
        request.session["estudio_id"] = estudio_obj.id

        return JsonResponse({"ok": True, "id": estudio_obj.id})

    except Exception as e:
        return JsonResponse({"ok": False, "error": str(e)}, status=400)


@csrf_exempt
def guardar_proyecto(request, proyecto_id: int):
    """Guarda cambios del Proyecto de forma automática.

    Este endpoint existe porque `core/urls.py` lo referencia.
    Persistimos el payload dentro de `Proyecto.extra['ultimo_guardado']` para re-hidratar la vista.
    """
    if request.method != "POST":
        return JsonResponse({"ok": False, "error": "Método no permitido"}, status=405)

    proyecto_obj = get_object_or_404(Proyecto, id=proyecto_id)

    try:
        payload = json.loads(request.body or "{}")
    except Exception:
        payload = {}

    if not isinstance(payload, dict):
        payload = {}
    if isinstance(payload.get("payload"), dict):
        payload = payload.get("payload") or {}

    update_fields = []

    payload_proyecto = payload.get("proyecto") if isinstance(payload.get("proyecto"), dict) else {}
    payload_economico = payload.get("economico") if isinstance(payload.get("economico"), dict) else {}

    # Permitir que el payload incluya un nombre editable (si se quiere persistir)
    nombre = (
        payload.get("nombre")
        or payload.get("nombre_proyecto")
        or payload_proyecto.get("nombre")
        or payload_proyecto.get("nombre_proyecto")
        or ""
    ).strip()
    if nombre:
        try:
            proyecto_obj.nombre = nombre
            update_fields.append("nombre")
        except Exception:
            # si el campo no existe en el modelo, ignoramos
            pass

    # Estado, fecha y responsable (cabecera de proyecto)
    estado_prev = (getattr(proyecto_obj, "estado", "") or "").strip().lower()
    estado = (payload.get("estado") or payload_proyecto.get("estado") or "").strip()
    estado_changed = False
    if estado:
        try:
            estado_changed = estado_prev != estado.lower()
            proyecto_obj.estado = estado
            update_fields.append("estado")
        except Exception:
            pass

    fecha_raw = payload.get("fecha") or payload_proyecto.get("fecha")
    if fecha_raw not in (None, ""):
        try:
            proyecto_obj.fecha = _parse_date(fecha_raw)
            update_fields.append("fecha")
        except Exception:
            pass

    responsable = (payload.get("responsable") or payload_proyecto.get("responsable") or "").strip()
    if responsable:
        try:
            setattr(proyecto_obj, "responsable", responsable)
            update_fields.append("responsable")
        except Exception:
            # si el campo no existe en el modelo, lo guardamos en extra
            pass

    codigo_raw = payload.get("codigo_proyecto") or payload_proyecto.get("codigo_proyecto")
    if codigo_raw not in (None, ""):
        try:
            if isinstance(codigo_raw, str):
                codigo_raw = codigo_raw.strip()
            codigo_val = int(float(codigo_raw))
            if codigo_val >= 0:
                proyecto_obj.codigo_proyecto = codigo_val
                update_fields.append("codigo_proyecto")
        except Exception:
            pass

    meses_raw = (
        payload_economico.get("meses")
        or payload.get("meses")
        or payload_proyecto.get("meses")
    )
    if meses_raw not in (None, ""):
        try:
            if isinstance(meses_raw, str):
                meses_raw = meses_raw.strip()
            meses_val = int(float(meses_raw))
            if meses_val >= 0:
                proyecto_obj.meses = meses_val
                update_fields.append("meses")
        except Exception:
            pass

    acceso_raw = payload_proyecto.get("acceso_comercial", payload.get("acceso_comercial"))
    if acceso_raw is not None and is_admin_user(request.user):
        if isinstance(acceso_raw, str):
            acceso_raw = acceso_raw.strip().lower() in {"1", "true", "si", "sí", "on"}
        proyecto_obj.acceso_comercial = bool(acceso_raw)
        update_fields.append("acceso_comercial")

    mostrar_landing_raw = payload_proyecto.get(
        "mostrar_en_landing",
        payload.get("mostrar_en_landing"),
    )
    if mostrar_landing_raw is not None and is_admin_user(request.user):
        if isinstance(mostrar_landing_raw, str):
            mostrar_landing_raw = mostrar_landing_raw.strip().lower() in {"1", "true", "si", "sí", "on"}
        proyecto_obj.mostrar_en_landing = bool(mostrar_landing_raw)
        update_fields.append("mostrar_en_landing")

    if update_fields:
        try:
            proyecto_obj.save(update_fields=list(set(update_fields)))
        except Exception:
            pass

    # Guardar overlay en `extra`
    try:
        extra = getattr(proyecto_obj, "extra", None)
        if not isinstance(extra, dict):
            extra = {}

        extra["ultimo_guardado"] = {
            "ts": timezone.now().isoformat(),
            "payload": _sanitize_for_json(payload),
        }
        if responsable:
            extra["responsable"] = responsable
        if estado:
            extra["estado"] = estado
        if fecha_raw not in (None, ""):
            extra["fecha"] = fecha_raw
        if codigo_raw not in (None, ""):
            extra["codigo_proyecto"] = codigo_raw
        if "notificar_inversores" in payload_proyecto or "notificar_inversores" in payload:
            notif_val = payload_proyecto.get("notificar_inversores", payload.get("notificar_inversores"))
            if isinstance(notif_val, str):
                notif_val = notif_val.strip().lower() in {"1", "true", "si", "sí", "on"}
            extra["notificar_inversores"] = bool(notif_val)
        landing_payload = payload.get("landing")
        if isinstance(landing_payload, dict):
            extra["landing"] = _sanitize_for_json(landing_payload)
        publicaciones_payload = payload.get("publicaciones")
        if isinstance(publicaciones_payload, dict):
            extra["publicaciones"] = _sanitize_for_json(publicaciones_payload)
        difusion_payload = payload.get("difusion")
        if isinstance(difusion_payload, dict):
            extra["difusion"] = _sanitize_for_json(difusion_payload)

        # Guardar también dentro de snapshot_datos como fallback si existe
        try:
            proyecto_obj.extra = extra
            proyecto_obj.save(update_fields=["extra"])
        except Exception:
            # si el campo extra no existe, intentamos snapshot_datos
            sd = getattr(proyecto_obj, "snapshot_datos", None)
            if isinstance(sd, dict):
                sd["_overlay"] = _sanitize_for_json(payload)
                proyecto_obj.snapshot_datos = sd
                proyecto_obj.save(update_fields=["snapshot_datos"])

        if estado_changed and _notificar_inversores_habilitado(proyecto_obj, snapshot=payload):
            try:
                estado_label = {
                    "captacion": "Captación",
                    "comprado": "Comprado",
                    "comercializacion": "Comercialización",
                    "reservado": "Reservado",
                    "vendido": "Vendido",
                    "cerrado": "Cerrado",
                    "descartado": "Descartado",
                }.get(estado.lower(), estado)
                clientes = Cliente.objects.filter(participaciones__proyecto=proyecto_obj).distinct()
                for cliente in clientes:
                    perfil, _ = InversorPerfil.objects.get_or_create(cliente=cliente)
                    _crear_comunicacion(
                        request,
                        perfil,
                        proyecto_obj,
                        "Actualización del estado del proyecto",
                        f"El proyecto {proyecto_obj.nombre} ha cambiado a estado: {estado_label}.",
                    )
            except Exception:
                pass
        return JsonResponse({"ok": True})

    except Exception as e:
        return JsonResponse({"ok": False, "error": str(e)}, status=400)


def borrar_estudio(request, estudio_id: int):
    estudio = get_object_or_404(Estudio, id=estudio_id)
    estudio.delete()
    # si se borró el activo en sesión, limpiar
    if request.session.get("estudio_id") == estudio_id:
        try:
            del request.session["estudio_id"]
        except KeyError:
            pass
    return redirect("core:lista_estudio")


@csrf_exempt
def convertir_a_proyecto(request, estudio_id: int):
    """Convierte un Estudio guardado en Proyecto.

    - Crea un EstudioSnapshot inmutable.
    - Crea un Proyecto heredando nombre/dirección/ref y snapshot.
    - Bloquea el estudio (si existe el campo).

    Devuelve JSON con redirect a lista_proyectos.
    """

    if request.method not in ("POST", "GET"):
        return JsonResponse({"ok": False, "error": "Método no permitido"}, status=405)
    if not is_admin_user(request.user):
        return JsonResponse({"ok": False, "error": "No tienes permisos para convertir estudios."}, status=403)

    estudio = get_object_or_404(Estudio, id=estudio_id)

    # Si ya está bloqueado, intentamos redirigir al proyecto existente si lo hubiera
    try:
        if getattr(estudio, "bloqueado", False):
            return JsonResponse({"ok": True, "redirect": reverse("core:lista_proyectos")})
    except Exception:
        pass

    def _has_field(model_cls, field_name: str) -> bool:
        try:
            model_cls._meta.get_field(field_name)
            return True
        except Exception:
            return False

    with transaction.atomic():
        # 1) Snapshot del estudio
        datos_snapshot = _sanitize_for_json(estudio.datos or {})
        datos_raw = estudio.datos or {}
        if not isinstance(datos_raw, dict):
            datos_raw = {}
        inmueble_raw = datos_raw.get("inmueble") if isinstance(datos_raw.get("inmueble"), dict) else {}
        proyecto_raw = datos_raw.get("proyecto") if isinstance(datos_raw.get("proyecto"), dict) else {}

        # versionado si existe
        snap_kwargs = {"estudio": estudio, "datos": datos_snapshot}
        if _has_field(EstudioSnapshot, "version_num"):
            last_v = (
                EstudioSnapshot.objects.filter(estudio=estudio)
                .order_by("-version_num", "-id")
                .values_list("version_num", flat=True)
                .first()
            )
            snap_kwargs["version_num"] = int(last_v or 0) + 1

        estudio_snapshot = EstudioSnapshot.objects.create(**snap_kwargs)

        # 2) Crear proyecto heredando
        metricas_estudio = _metricas_desde_estudio(estudio)
        proyecto_kwargs = {}
        nombre_estudio = (
            estudio.nombre
            or datos_raw.get("nombre_proyecto")
            or datos_raw.get("nombre")
            or proyecto_raw.get("nombre")
            or proyecto_raw.get("nombre_proyecto")
            or ""
        )
        direccion_estudio = (
            estudio.direccion
            or datos_raw.get("direccion")
            or inmueble_raw.get("direccion")
            or inmueble_raw.get("direccion_inmueble")
            or ""
        )
        ref_catastral_estudio = (
            estudio.ref_catastral
            or datos_raw.get("ref_catastral")
            or inmueble_raw.get("ref_catastral")
            or ""
        )
        valor_referencia_estudio = (
            estudio.valor_referencia
            if estudio.valor_referencia is not None
            else inmueble_raw.get("valor_referencia")
            or datos_raw.get("valor_referencia")
        )

        if _has_field(Proyecto, "nombre"):
            proyecto_kwargs["nombre"] = nombre_estudio
        if _has_field(Proyecto, "direccion"):
            proyecto_kwargs["direccion"] = direccion_estudio
        if _has_field(Proyecto, "ref_catastral"):
            proyecto_kwargs["ref_catastral"] = ref_catastral_estudio
        if _has_field(Proyecto, "valor_referencia"):
            proyecto_kwargs["valor_referencia"] = valor_referencia_estudio
        if _has_field(Proyecto, "origen_estudio"):
            proyecto_kwargs["origen_estudio"] = estudio
        if _has_field(Proyecto, "origen_snapshot"):
            proyecto_kwargs["origen_snapshot"] = estudio_snapshot
        if _has_field(Proyecto, "snapshot_datos"):
            proyecto_kwargs["snapshot_datos"] = datos_snapshot
        if _has_field(Proyecto, "estado"):
            # estado inicial del proyecto
            proyecto_kwargs["estado"] = "captacion"
        proyecto = Proyecto.objects.create(**proyecto_kwargs)

        # 3) Bloquear el estudio
        if _has_field(Estudio, "bloqueado"):
            estudio.bloqueado = True
        if _has_field(Estudio, "bloqueado_en"):
            estudio.bloqueado_en = timezone.now()
        estudio.save()

    return JsonResponse({"ok": True, "proyecto_id": proyecto.id, "redirect": reverse("core:lista_proyectos")})

def pdf_estudio_preview(request, estudio_id: int):
    estudio = get_object_or_404(Estudio, id=estudio_id)

    # Recalcular SIEMPRE desde backend
    kpis = _metricas_desde_estudio(estudio)
    inmueble = _datos_inmueble_desde_estudio(estudio)
    datos_raw = estudio.datos or {}
    if not isinstance(datos_raw, dict):
        datos_raw = {}

    comite_raw = datos_raw.get("comite") if isinstance(datos_raw.get("comite"), dict) else {}
    comite = dict(comite_raw) if isinstance(comite_raw, dict) else {}
    # Completar con campos sueltos (compatibilidad con payloads antiguos)
    for src_key, dst_key in (
        ("recomendacion", "recomendacion"),
        ("decision", "recomendacion"),
        ("decision_texto", "recomendacion"),
        ("observaciones", "observaciones"),
        ("comentario", "observaciones"),
        ("comentario_comite", "observaciones"),
        ("resumen_ejecutivo_comite", "observaciones"),
        ("resumen_ejecutivo", "resumen_ejecutivo"),
        ("resumen_ejecutivo_comite", "resumen_ejecutivo"),
    ):
        if comite.get(dst_key) in (None, "") and datos_raw.get(src_key) not in (None, ""):
            comite[dst_key] = datos_raw.get(src_key)

    # Snapshot canónico (el PDF SOLO usa esto)
    kpis_metricas = kpis.get("metricas", {}) if isinstance(kpis.get("metricas", {}), dict) else {}
    meses = _safe_float(
        datos_raw.get("meses")
        or datos_raw.get("meses_operacion")
        or datos_raw.get("meses_operación")
        or (datos_raw.get("economico") or {}).get("meses") if isinstance(datos_raw.get("economico"), dict) else None,
        None,
    )
    financiacion_pct = _safe_float(
        datos_raw.get("financiacion_pct")
        or datos_raw.get("porcentaje_financiacion")
        or (datos_raw.get("economico") or {}).get("financiacion_pct") if isinstance(datos_raw.get("economico"), dict) else None,
        None,
    )
    if meses is not None and "meses" not in kpis_metricas:
        kpis_metricas["meses"] = meses
    if financiacion_pct is not None and "financiacion_pct" not in kpis_metricas:
        kpis_metricas["financiacion_pct"] = financiacion_pct
    snapshot = {
        "inmueble": inmueble,
        "economico": {**kpis_metricas},
        # Compatibilidad: exponer KPIs tanto en raíz de "kpis" como dentro de "metricas".
        "kpis": {
            **kpis_metricas,
            "metricas": kpis_metricas,
            "metricas_fmt": kpis.get("metricas_fmt", {}),
        },
        "inversor": kpis.get("inversor", {}),
        "inversor_fmt": kpis.get("inversor_fmt", {}),
        "comite": comite,
        "resultado": kpis.get("resultado", {}),
        "texto": kpis.get("texto", {}),
        "reparto": kpis.get("reparto", {}),
        "reparto_fmt": kpis.get("reparto_fmt", {}),
    }

    ctx = {
        "estudio": estudio,
        "datos": _safe_template_obj(estudio.datos or {}),
        "inmueble": _safe_template_obj(inmueble),
        "metricas": _safe_template_obj(kpis.get("metricas", {})),
        "metricas_fmt": _safe_template_obj(kpis.get("metricas_fmt", {})),
        "inversor": _safe_template_obj(kpis.get("inversor", {})),
        "inversor_fmt": _safe_template_obj(kpis.get("inversor_fmt", {})),
        "reparto": _safe_template_obj(kpis.get("reparto", {})),
        "reparto_fmt": _safe_template_obj(kpis.get("reparto_fmt", {})),
        "resultado": _safe_template_obj(kpis.get("resultado", {})),
        "texto": _safe_template_obj(kpis.get("texto", {})),
        "comite": _safe_template_obj(comite),
        "snapshot": _safe_template_obj(snapshot),
    }

    return render(request, "core/pdf_estudio_rentabilidad.html", ctx)


def pdf_memoria_economica(request, proyecto_id: int):
    proyecto = get_object_or_404(Proyecto, id=proyecto_id)
    gastos = list(GastoProyecto.objects.filter(proyecto=proyecto).order_by("fecha", "id"))
    ingresos = list(IngresoProyecto.objects.filter(proyecto=proyecto).order_by("fecha", "id"))

    for i in ingresos:
        if not i.estado:
            i.estado = "confirmado"

    def _sum_importes(items):
        total = Decimal("0")
        for item in items:
            if item is None:
                continue
            total += item
        return total

    def _importe_estimado(item):
        estimado = getattr(item, "importe_estimado", None)
        if estimado is not None:
            return estimado
        if getattr(item, "estado", "") == "estimado":
            return item.importe
        return Decimal("0")

    def _importe_real(item):
        if getattr(item, "estado", "") != "confirmado":
            return Decimal("0")
        real = getattr(item, "importe_real", None)
        return real if real is not None else item.importe

    ingresos_estimados = _sum_importes([_importe_estimado(i) for i in ingresos])
    ingresos_reales = _sum_importes([_importe_real(i) for i in ingresos])
    gastos_estimados = _sum_importes([_importe_estimado(g) for g in gastos])
    gastos_reales = _sum_importes([_importe_real(g) for g in gastos])

    beneficio_estimado = ingresos_estimados - gastos_estimados
    beneficio_real = ingresos_reales - gastos_reales

    snapshot = _get_snapshot_comunicacion(proyecto)
    inv_sec = snapshot.get("inversor") if isinstance(snapshot.get("inversor"), dict) else {}
    comision_pct = _safe_float(
        inv_sec.get("comision_inversure_pct")
        or inv_sec.get("comision_pct")
        or snapshot.get("comision_inversure_pct")
        or snapshot.get("comision_pct")
        or 0.0,
        0.0,
    )
    if comision_pct < 0:
        comision_pct = 0.0
    if comision_pct > 100:
        comision_pct = 100.0

    pct_decimal = Decimal(str(comision_pct)) / Decimal("100")
    comision_estimada = beneficio_estimado * pct_decimal if beneficio_estimado else Decimal("0")
    comision_real = beneficio_real * pct_decimal if beneficio_real else Decimal("0")
    beneficio_neto_estimado = beneficio_estimado - comision_estimada
    beneficio_neto_real = beneficio_real - comision_real

    base_precio = proyecto.precio_compra_inmueble or proyecto.precio_propiedad or Decimal("0")
    cats_adq = {"adquisicion", "reforma", "seguridad", "operativos", "financieros", "legales", "otros"}
    gastos_adq_estimado = _sum_importes(
        [_importe_estimado(g) for g in gastos if g.categoria in cats_adq]
    )
    gastos_adq_real = _sum_importes(
        [_importe_real(g) for g in gastos if g.categoria in cats_adq]
    )

    base_est = base_precio + gastos_adq_estimado
    base_real = base_precio + gastos_adq_real
    roi_estimado = (beneficio_estimado / base_est * Decimal("100")) if base_est > 0 else None
    roi_real = (beneficio_real / base_real * Decimal("100")) if base_real > 0 else None

    categorias = []
    for key, label in GastoProyecto.CATEGORIAS:
        est = _sum_importes([_importe_estimado(g) for g in gastos if g.categoria == key])
        real = _sum_importes([_importe_real(g) for g in gastos if g.categoria == key])
        categorias.append({"nombre": label, "estimado": est, "real": real})

    resumen = {
        "ingresos_estimados": ingresos_estimados,
        "ingresos_reales": ingresos_reales,
        "gastos_estimados": gastos_estimados,
        "gastos_reales": gastos_reales,
        "beneficio_estimado": beneficio_estimado,
        "beneficio_real": beneficio_real,
        "comision_inversure_pct": comision_pct,
        "comision_inversure_estimada": comision_estimada,
        "comision_inversure_real": comision_real,
        "beneficio_neto_estimado": beneficio_neto_estimado,
        "beneficio_neto_real": beneficio_neto_real,
        "roi_estimado": roi_estimado,
        "roi_real": roi_real,
        "categorias": categorias,
    }

    ctx = {
        "proyecto": proyecto,
        "gastos": gastos,
        "ingresos": ingresos,
        "resumen": resumen,
        "fecha_informe": timezone.now(),
    }
    return render(request, "core/pdf_memoria_economica.html", ctx)


@csrf_exempt
def proyecto_gastos(request, proyecto_id: int):
    try:
        proyecto = Proyecto.objects.get(id=proyecto_id)
    except Proyecto.DoesNotExist:
        return JsonResponse({"ok": False, "error": "Proyecto no encontrado"}, status=404)

    if request.method == "GET":
        can_preview = _can_preview_facturas(request.user)
        facturas_docs = {}
        try:
            docs = (
                DocumentoProyecto.objects.filter(
                    proyecto=proyecto,
                    categoria="facturas",
                    fecha_factura__isnull=False,
                    importe_factura__isnull=False,
                )
                .order_by("-creado", "-id")
            )
            for doc in docs:
                key = (doc.fecha_factura, doc.importe_factura)
                if key not in facturas_docs:
                    facturas_docs[key] = doc
        except Exception:
            facturas_docs = {}
        gastos = []
        for g in GastoProyecto.objects.filter(proyecto=proyecto).order_by("fecha", "id"):
            factura_url = None
            if can_preview:
                if hasattr(g, "factura") and g.factura:
                    try:
                        key = getattr(g.factura.archivo, "name", "") or ""
                        signed = _s3_presigned_url(key)
                        factura_url = signed if signed else g.factura.archivo.url
                    except Exception:
                        factura_url = None
                if not factura_url and facturas_docs:
                    doc = facturas_docs.get((g.fecha, g.importe))
                    if doc and doc.archivo:
                        try:
                            key = getattr(doc.archivo, "name", "") or ""
                            signed = _s3_presigned_url(key)
                            factura_url = signed if signed else doc.archivo.url
                        except Exception:
                            factura_url = None
            gastos.append({
                "id": g.id,
                "fecha": g.fecha.isoformat(),
                "categoria": g.categoria,
                "concepto": g.concepto,
                "proveedor": g.proveedor,
                "importe": float(g.importe),
                "imputable_inversores": g.imputable_inversores,
                "estado": g.estado,
                "observaciones": g.observaciones,
                "factura_url": factura_url,
                "has_factura": bool(factura_url),
            })
        return JsonResponse({"ok": True, "gastos": gastos})

    if request.method != "POST":
        return JsonResponse({"ok": False, "error": "Método no permitido"}, status=405)

    try:
        data = json.loads(request.body or "{}")
        fecha = _parse_date(data.get("fecha"))
        categoria = (data.get("categoria") or "").strip()
        concepto = (data.get("concepto") or "").strip()
        importe = _parse_decimal(data.get("importe"))

        if not fecha or not categoria or not concepto or importe is None:
            return JsonResponse({"ok": False, "error": "Faltan campos obligatorios"}, status=400)

        estado = (data.get("estado") or "estimado")
        gasto = GastoProyecto.objects.create(
            proyecto=proyecto,
            fecha=fecha,
            categoria=categoria,
            concepto=concepto,
            proveedor=(data.get("proveedor") or "").strip() or None,
            importe=importe,
            importe_estimado=importe,
            importe_real=importe if estado == "confirmado" else None,
            imputable_inversores=bool(data.get("imputable_inversores", True)),
            estado=estado,
            observaciones=(data.get("observaciones") or "").strip() or None,
        )
        return JsonResponse({"ok": True, "id": gasto.id})
    except Exception as e:
        return JsonResponse({"ok": False, "error": str(e)}, status=400)


@csrf_exempt
def proyecto_gasto_detalle(request, proyecto_id: int, gasto_id: int):
    try:
        gasto = GastoProyecto.objects.select_related("proyecto").get(id=gasto_id, proyecto_id=proyecto_id)
    except GastoProyecto.DoesNotExist:
        return JsonResponse({"ok": False, "error": "Gasto no encontrado"}, status=404)

    if request.method == "GET":
        factura_url = None
        if _can_preview_facturas(request.user) and hasattr(gasto, "factura") and gasto.factura:
            try:
                key = getattr(gasto.factura.archivo, "name", "") or ""
                signed = _s3_presigned_url(key)
                factura_url = signed if signed else gasto.factura.archivo.url
            except Exception:
                factura_url = None
        return JsonResponse({
            "ok": True,
            "gasto": {
                "id": gasto.id,
                "fecha": gasto.fecha.isoformat(),
                "categoria": gasto.categoria,
                "concepto": gasto.concepto,
                "proveedor": gasto.proveedor,
                "importe": float(gasto.importe),
                "imputable_inversores": gasto.imputable_inversores,
                "estado": gasto.estado,
                "observaciones": gasto.observaciones,
                "factura_url": factura_url,
                "has_factura": bool(factura_url),
            },
        })

    if request.method == "DELETE":
        gasto.delete()
        return JsonResponse({"ok": True})

    if request.method not in ("PUT", "PATCH"):
        return JsonResponse({"ok": False, "error": "Método no permitido"}, status=405)

    try:
        prev_importe = gasto.importe
        prev_estado = gasto.estado
        data = json.loads(request.body or "{}")
        if "fecha" in data:
            gasto.fecha = _parse_date(data.get("fecha")) or gasto.fecha
        if "categoria" in data:
            gasto.categoria = (data.get("categoria") or gasto.categoria).strip()
        if "concepto" in data:
            gasto.concepto = (data.get("concepto") or gasto.concepto).strip()
        if "proveedor" in data:
            gasto.proveedor = (data.get("proveedor") or "").strip() or None
        if "importe" in data:
            gasto.importe = _parse_decimal(data.get("importe")) or gasto.importe
        if "imputable_inversores" in data:
            gasto.imputable_inversores = bool(data.get("imputable_inversores"))
        if "estado" in data:
            gasto.estado = (data.get("estado") or gasto.estado)
        if "observaciones" in data:
            gasto.observaciones = (data.get("observaciones") or "").strip() or None

        if gasto.estado == "estimado":
            gasto.importe_estimado = gasto.importe
        elif prev_estado == "estimado" and gasto.estado == "confirmado" and not gasto.importe_estimado:
            gasto.importe_estimado = prev_importe

        if gasto.estado == "confirmado":
            if gasto.importe_real is None or "importe" in data or prev_estado != "confirmado":
                gasto.importe_real = gasto.importe

        gasto.save()
        return JsonResponse({"ok": True})
    except Exception as e:
        return JsonResponse({"ok": False, "error": str(e)}, status=400)


@csrf_exempt
def proyecto_gasto_factura(request, proyecto_id: int, gasto_id: int):
    try:
        gasto = GastoProyecto.objects.select_related("proyecto").get(id=gasto_id, proyecto_id=proyecto_id)
    except GastoProyecto.DoesNotExist:
        return JsonResponse({"ok": False, "error": "Gasto no encontrado"}, status=404)

    if request.method == "DELETE":
        try:
            FacturaGasto.objects.filter(gasto=gasto).delete()
            return JsonResponse({"ok": True})
        except Exception as e:
            return JsonResponse({"ok": False, "error": str(e)}, status=400)

    if request.method != "POST":
        return JsonResponse({"ok": False, "error": "Método no permitido"}, status=405)

    documento_id = request.POST.get("documento_id")
    archivo = request.FILES.get("factura") or request.FILES.get("archivo")
    if not archivo and not documento_id:
        return JsonResponse({"ok": False, "error": "Archivo requerido"}, status=400)

    factura_obj, _ = FacturaGasto.objects.get_or_create(gasto=gasto)
    if documento_id:
        try:
            doc = DocumentoProyecto.objects.get(
                id=documento_id,
                proyecto_id=proyecto_id,
                categoria="facturas",
            )
            factura_obj.archivo = doc.archivo
            factura_obj.nombre_original = doc.titulo or doc.archivo.name
        except DocumentoProyecto.DoesNotExist:
            return JsonResponse({"ok": False, "error": "Documento no encontrado"}, status=404)
    else:
        factura_obj.archivo = archivo
        factura_obj.nombre_original = getattr(archivo, "name", "") or factura_obj.nombre_original
    factura_obj.save()

    factura_url = None
    try:
        key = getattr(factura_obj.archivo, "name", "") or ""
        signed = _s3_presigned_url(key)
        factura_url = signed if signed else factura_obj.archivo.url
    except Exception:
        factura_url = None

    return JsonResponse({"ok": True, "factura_url": factura_url})


@csrf_exempt
def proyecto_ingresos(request, proyecto_id: int):
    try:
        proyecto = Proyecto.objects.get(id=proyecto_id)
    except Proyecto.DoesNotExist:
        return JsonResponse({"ok": False, "error": "Proyecto no encontrado"}, status=404)

    if request.method == "GET":
        ingresos = []
        for i in IngresoProyecto.objects.filter(proyecto=proyecto).order_by("fecha", "id"):
            ingresos.append({
                "id": i.id,
                "fecha": i.fecha.isoformat(),
                "tipo": i.tipo,
                "concepto": i.concepto,
                "importe": float(i.importe),
                "estado": i.estado,
                "imputable_inversores": i.imputable_inversores,
                "observaciones": i.observaciones,
            })
        return JsonResponse({"ok": True, "ingresos": ingresos})

    if request.method != "POST":
        return JsonResponse({"ok": False, "error": "Método no permitido"}, status=405)

    try:
        data = json.loads(request.body or "{}")
        fecha = _parse_date(data.get("fecha"))
        tipo = (data.get("tipo") or "").strip()
        concepto = (data.get("concepto") or "").strip()
        importe = _parse_decimal(data.get("importe"))

        if not fecha or not tipo or not concepto or importe is None:
            return JsonResponse({"ok": False, "error": "Faltan campos obligatorios"}, status=400)

        estado = (data.get("estado") or "estimado")
        ingreso = IngresoProyecto.objects.create(
            proyecto=proyecto,
            fecha=fecha,
            tipo=tipo,
            concepto=concepto,
            importe=importe,
            importe_estimado=importe,
            importe_real=importe if estado == "confirmado" else None,
            estado=estado,
            imputable_inversores=bool(data.get("imputable_inversores", True)),
            observaciones=(data.get("observaciones") or "").strip() or None,
        )
        return JsonResponse({"ok": True, "id": ingreso.id})
    except Exception as e:
        return JsonResponse({"ok": False, "error": str(e)}, status=400)


@csrf_exempt
def proyecto_ingreso_detalle(request, proyecto_id: int, ingreso_id: int):
    try:
        ingreso = IngresoProyecto.objects.select_related("proyecto").get(id=ingreso_id, proyecto_id=proyecto_id)
    except IngresoProyecto.DoesNotExist:
        return JsonResponse({"ok": False, "error": "Ingreso no encontrado"}, status=404)

    if request.method == "GET":
        return JsonResponse({
            "ok": True,
            "ingreso": {
                "id": ingreso.id,
                "fecha": ingreso.fecha.isoformat(),
                "tipo": ingreso.tipo,
                "concepto": ingreso.concepto,
                "importe": float(ingreso.importe),
                "estado": ingreso.estado,
                "imputable_inversores": ingreso.imputable_inversores,
                "observaciones": ingreso.observaciones,
            },
        })

    if request.method == "DELETE":
        ingreso.delete()
        return JsonResponse({"ok": True})

    if request.method not in ("PUT", "PATCH"):
        return JsonResponse({"ok": False, "error": "Método no permitido"}, status=405)

    try:
        prev_importe = ingreso.importe
        prev_estado = ingreso.estado
        data = json.loads(request.body or "{}")
        if "fecha" in data:
            ingreso.fecha = _parse_date(data.get("fecha")) or ingreso.fecha
        if "tipo" in data:
            ingreso.tipo = (data.get("tipo") or ingreso.tipo).strip()
        if "concepto" in data:
            ingreso.concepto = (data.get("concepto") or ingreso.concepto).strip()
        if "importe" in data:
            ingreso.importe = _parse_decimal(data.get("importe")) or ingreso.importe
        if "estado" in data:
            ingreso.estado = (data.get("estado") or ingreso.estado)
        if "imputable_inversores" in data:
            ingreso.imputable_inversores = bool(data.get("imputable_inversores"))
        if "observaciones" in data:
            ingreso.observaciones = (data.get("observaciones") or "").strip() or None

        if ingreso.estado == "estimado":
            ingreso.importe_estimado = ingreso.importe
        elif prev_estado == "estimado" and ingreso.estado == "confirmado" and not ingreso.importe_estimado:
            ingreso.importe_estimado = prev_importe

        if ingreso.estado == "confirmado":
            if ingreso.importe_real is None or "importe" in data or prev_estado != "confirmado":
                ingreso.importe_real = ingreso.importe

        ingreso.save()
        return JsonResponse({"ok": True})
    except Exception as e:
        return JsonResponse({"ok": False, "error": str(e)}, status=400)


def proyecto_documentos(request, proyecto_id: int):
    proyecto = get_object_or_404(Proyecto, id=proyecto_id)

    if request.method != "POST":
        return JsonResponse({"ok": False, "error": "Método no permitido"}, status=405)

    archivos = request.FILES.getlist("archivo")
    if not archivos:
        return redirect(f"{reverse('core:proyecto', args=[proyecto_id])}#vista-documentacion")

    titulo = (request.POST.get("titulo") or "").strip()

    categoria = (request.POST.get("categoria") or "otros").strip()
    categorias_validas = {c[0] for c in DocumentoProyecto.CATEGORIAS}
    if categoria not in categorias_validas:
        categoria = "otros"
    factura_fecha = _parse_date(request.POST.get("factura_fecha")) if categoria == "facturas" else None
    factura_importe = _parse_decimal(request.POST.get("factura_importe")) if categoria == "facturas" else None

    for idx, archivo in enumerate(archivos, start=1):
        nombre_base = os.path.splitext(archivo.name or "")[0] or "Documento"
        if titulo:
            doc_titulo = f"{titulo} ({idx})" if len(archivos) > 1 else titulo
        else:
            doc_titulo = nombre_base
        DocumentoProyecto.objects.create(
            proyecto=proyecto,
            tipo=categoria,
            categoria=categoria,
            titulo=doc_titulo,
            archivo=archivo,
            fecha_factura=factura_fecha,
            importe_factura=factura_importe,
        )

    return redirect(f"{reverse('core:proyecto', args=[proyecto_id])}#vista-documentacion")


def proyecto_documento_borrar(request, proyecto_id: int, documento_id: int):
    if request.method != "POST":
        return JsonResponse({"ok": False, "error": "Método no permitido"}, status=405)

    documento = get_object_or_404(
        DocumentoProyecto,
        id=documento_id,
        proyecto_id=proyecto_id,
    )
    documento.delete()
    return redirect(f"{reverse('core:proyecto', args=[proyecto_id])}#vista-documentacion")


def proyecto_documento_principal(request, proyecto_id: int, documento_id: int):
    if request.method != "POST":
        return JsonResponse({"ok": False, "error": "Método no permitido"}, status=405)
    documento = get_object_or_404(
        DocumentoProyecto,
        id=documento_id,
        proyecto_id=proyecto_id,
    )
    if documento.categoria != "fotografias":
        return JsonResponse({"ok": False, "error": "Solo válido para fotografías"}, status=400)
    DocumentoProyecto.objects.filter(
        proyecto_id=proyecto_id,
        categoria="fotografias",
    ).update(es_principal=False)
    documento.es_principal = True
    documento.save(update_fields=["es_principal"])
    return redirect(f"{reverse('core:proyecto', args=[proyecto_id])}#vista-documentacion")


def proyecto_documento_flag(request, proyecto_id: int, documento_id: int):
    if request.method != "POST":
        return JsonResponse({"ok": False, "error": "Método no permitido"}, status=405)
    documento = get_object_or_404(
        DocumentoProyecto,
        id=documento_id,
        proyecto_id=proyecto_id,
        categoria="fotografias",
    )
    field = (request.POST.get("field") or "").strip()
    allowed = {"usar_pdf", "usar_story", "usar_instagram", "usar_dossier"}
    if field not in allowed:
        return JsonResponse({"ok": False, "error": "Campo no permitido"}, status=400)
    value_raw = (request.POST.get("value") or "").strip().lower()
    value = value_raw in {"1", "true", "si", "sí", "on"}
    setattr(documento, field, value)
    documento.save(update_fields=[field])
    return JsonResponse({"ok": True, "field": field, "value": value})


def proyecto_presentacion_generar(request, proyecto_id: int):
    proyecto = get_object_or_404(Proyecto, id=proyecto_id)
    if request.method != "POST":
        return redirect(f"{reverse('core:proyecto', args=[proyecto_id])}#vista-difusion")

    def _post_prefixed(key: str, default=None):
        val = request.POST.get(f"difusion.{key}")
        if val in (None, ""):
            return request.POST.get(key, default)
        return val

    estilo = (_post_prefixed("estilo") or "coin").strip().lower()
    formatos = {
        "pdf": _post_prefixed("formatos.pdf") == "on" or request.POST.get("gen_pdf") == "on",
        "ig_feed": _post_prefixed("formatos.feed") == "on" or request.POST.get("gen_feed") == "on",
        "ig_story": _post_prefixed("formatos.story") == "on" or request.POST.get("gen_story") == "on",
    }
    if not any(formatos.values()):
        formatos["pdf"] = True

    titulo = (
        _post_prefixed("titulo")
        or proyecto.nombre
        or getattr(proyecto, "nombre_proyecto", "")
        or "Proyecto"
    ).strip()
    descripcion = (_post_prefixed("descripcion") or "").strip()
    ubicacion = (_post_prefixed("ubicacion") or "").strip()
    rentabilidad = _parse_decimal(_post_prefixed("rentabilidad"))
    plazo_meses = _parse_decimal(_post_prefixed("plazo_meses"))
    acceso_minimo = _parse_decimal(_post_prefixed("acceso_minimo"))
    try:
        anio = int(_post_prefixed("anio") or timezone.now().year)
    except Exception:
        anio = timezone.now().year

    foto_doc = None
    foto_id = _post_prefixed("foto_id")
    if foto_id:
        foto_doc = DocumentoProyecto.objects.filter(
            proyecto=proyecto, id=foto_id, categoria="fotografias"
        ).first()
    if not foto_doc:
        extra = getattr(proyecto, "extra", None)
        landing_cfg = extra.get("landing", {}) if isinstance(extra, dict) else {}
        publicaciones_cfg = extra.get("publicaciones", {}) if isinstance(extra, dict) else {}
        landing_img_id = landing_cfg.get("imagen_id")
        cabecera_id = publicaciones_cfg.get("cabecera_imagen_id")
        chosen_id = landing_img_id or cabecera_id
        if chosen_id:
            foto_doc = DocumentoProyecto.objects.filter(
                proyecto=proyecto, id=chosen_id, categoria="fotografias"
            ).first()
    if not foto_doc:
        foto_doc = DocumentoProyecto.objects.filter(
            proyecto=proyecto, categoria="fotografias", es_principal=True
        ).first()
    if not foto_doc:
        foto_doc = DocumentoProyecto.objects.filter(
            proyecto=proyecto, categoria="fotografias"
        ).first()

    def _foto_por_flag(flag: str):
        return DocumentoProyecto.objects.filter(
            proyecto=proyecto, categoria="fotografias", **{flag: True}
        ).order_by("-creado", "-id").first()

    foto_doc_pdf = _foto_por_flag("usar_pdf") or foto_doc
    foto_doc_feed = _foto_por_flag("usar_instagram") or foto_doc
    foto_doc_story = _foto_por_flag("usar_story") or foto_doc

    def _foto_url_for(doc):
        if not doc:
            return ""
        return _documento_url(request, doc)

    foto_url = _foto_url_for(foto_doc_pdf)
    foto_url_feed = _foto_url_for(foto_doc_feed)
    foto_url_story = _foto_url_for(foto_doc_story)

    if not foto_url:
        foto_url = request.build_absolute_uri(static("landing/assets/hero_investor.jpg"))
    if not foto_url_feed:
        foto_url_feed = foto_url
    if not foto_url_story:
        foto_url_story = foto_url

    mapa_id = _post_prefixed("mapa_id") or ""
    dossier_id = _post_prefixed("dossier_id") or ""
    anexos_ids = request.POST.getlist("anexos")
    if not anexos_ids:
        anexos_ids = []
        for key in request.POST.keys():
            if key.startswith("difusion.anexos."):
                doc_id = key.split("difusion.anexos.", 1)[-1]
                if doc_id:
                    anexos_ids.append(doc_id)
    anexos_ids = [x for x in anexos_ids if x]
    anexos_docs = []
    mapa_url = ""
    dossier_url = ""
    lookup_ids = [x for x in [mapa_id, dossier_id, *anexos_ids] if x]
    if lookup_ids:
        docs = DocumentoProyecto.objects.filter(proyecto=proyecto, id__in=lookup_ids)
        docs_map = {str(doc.id): doc for doc in docs}
        if mapa_id:
            mapa_doc = docs_map.get(str(mapa_id))
            if mapa_doc:
                mapa_url = _documento_image_url(request, mapa_doc)
        if dossier_id:
            dossier_doc = docs_map.get(str(dossier_id))
            if dossier_doc:
                dossier_url = _documento_image_url(request, dossier_doc)
        for doc_id in anexos_ids:
            doc = docs_map.get(str(doc_id))
            if not doc or doc.categoria == "presentacion":
                continue
            anexos_docs.append(doc)

    snapshot = _get_snapshot_comunicacion(proyecto)
    inmueble_raw = snapshot.get("inmueble") if isinstance(snapshot.get("inmueble"), dict) else {}
    inmueble = SafeAccessDict(inmueble_raw)
    inmueble["dormitorios"] = inmueble.get("dormitorios") or inmueble.get("habitaciones") or inmueble.get("num_dormitorios")
    inmueble["banos"] = inmueble.get("banos") or inmueble.get("baños") or inmueble.get("num_banos") or inmueble.get("num_baños")
    inmueble["anio_construccion"] = inmueble.get("anio_construccion") or inmueble.get("ano_construccion") or inmueble.get("year_built")
    resultado = _resultado_desde_memoria(proyecto, snapshot)
    if rentabilidad is None and resultado.get("roi") is not None:
        rentabilidad = resultado.get("roi")

    roi_val = _safe_float(rentabilidad if rentabilidad is not None else resultado.get("roi"), 0.0)
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

    fotos_urls = []
    for doc in anexos_docs:
        if doc.categoria != "fotografias":
            continue
        fotos_urls.append(_documento_url(request, doc))
    if not fotos_urls:
        fotos_docs = DocumentoProyecto.objects.filter(
            proyecto=proyecto, categoria="fotografias", usar_dossier=True
        ).order_by("-creado", "-id")
        if fotos_docs.exists():
            for doc in fotos_docs:
                fotos_urls.append(_documento_url(request, doc))
        else:
            fotos_docs = DocumentoProyecto.objects.filter(
                proyecto=proyecto, categoria="fotografias"
            ).order_by("-es_principal", "-creado", "-id")[:2]
            for doc in fotos_docs:
                fotos_urls.append(_documento_url(request, doc))

    context = {
        "proyecto": proyecto,
        "titulo": titulo,
        "descripcion": descripcion,
        "ubicacion": ubicacion,
        "rentabilidad": rentabilidad,
        "plazo_meses": plazo_meses,
        "acceso_minimo": acceso_minimo,
        "anio": anio,
        "estilo": estilo,
        "formato": "pdf",
        "foto_url": foto_url,
        "descripcion_foto_url": fotos_urls[0] if fotos_urls else foto_url,
        "logo_data_uri": _logo_data_uri("core/logo_inversure_blanco.png"),
        "inmueble": inmueble,
        "resultado": resultado,
        "mapa_url": mapa_url,
        "dossier_url": dossier_url,
        "fotos_urls": fotos_urls,
        "semaforo_estado": semaforo_estado,
        "semaforo_label": semaforo_label,
        "roi_bar": roi_bar,
    }

    slug = slugify(titulo or "proyecto") or f"proyecto_{proyecto_id}"
    created = 0

    if formatos.get("pdf"):
        pdf_context = dict(context)
        pdf_context["formato"] = "pdf"
        pdf_bytes = _build_presentacion_pdf(request, pdf_context)
        if pdf_bytes:
            pdf_bytes = _merge_pdf_with_documentos(pdf_bytes, anexos_docs, request=request)
            if pdf_bytes:
                nombre = f"presentacion_{slug}_{estilo}.pdf"
                DocumentoProyecto.objects.create(
                    proyecto=proyecto,
                    tipo="presentacion",
                    categoria="presentacion",
                    titulo=f"Presentación RRSS (PDF) · {titulo}",
                    archivo=ContentFile(pdf_bytes, name=nombre),
                )
                created += 1

    if formatos.get("ig_feed"):
        feed_context = dict(context)
        feed_context["formato"] = "ig_feed"
        feed_context["foto_url"] = foto_url_feed
        feed_bytes = _build_presentacion_png(request, feed_context)
        if feed_bytes:
            nombre = f"presentacion_{slug}_{estilo}_feed.png"
            DocumentoProyecto.objects.create(
                proyecto=proyecto,
                tipo="presentacion",
                categoria="presentacion",
                titulo=f"Presentación RRSS (IG Feed) · {titulo}",
                archivo=ContentFile(feed_bytes, name=nombre),
            )
            created += 1

    if formatos.get("ig_story"):
        story_context = dict(context)
        story_context["formato"] = "ig_story"
        story_context["foto_url"] = foto_url_story
        story_bytes = _build_presentacion_png(request, story_context)
        if story_bytes:
            nombre = f"presentacion_{slug}_{estilo}_story.png"
            DocumentoProyecto.objects.create(
                proyecto=proyecto,
                tipo="presentacion",
                categoria="presentacion",
                titulo=f"Presentación RRSS (IG Story) · {titulo}",
                archivo=ContentFile(story_bytes, name=nombre),
            )
            created += 1

    if created:
        messages.success(request, f"Presentación generada ({created} archivo/s).")
    else:
        messages.error(
            request,
            "No se pudo generar la presentación. Revisa dependencias del servidor para WeasyPrint.",
        )

    try:
        difusion_payload = {
            "titulo": titulo,
            "descripcion": descripcion,
            "ubicacion": ubicacion,
            "rentabilidad": rentabilidad,
            "plazo_meses": plazo_meses,
            "acceso_minimo": acceso_minimo,
            "anio": anio,
            "foto_id": foto_id,
            "mapa_id": mapa_id,
            "dossier_id": dossier_id,
            "estilo": estilo,
            "formatos": {
                "pdf": formatos.get("pdf", False),
                "feed": formatos.get("ig_feed", False),
                "story": formatos.get("ig_story", False),
            },
            "anexos": {str(doc_id): True for doc_id in anexos_ids if doc_id},
        }
        extra = getattr(proyecto, "extra", None)
        if not isinstance(extra, dict):
            extra = {}
        extra["difusion"] = _sanitize_for_json(difusion_payload)
        proyecto.extra = extra
        proyecto.save(update_fields=["extra"])
    except Exception:
        pass

    return redirect(f"{reverse('core:proyecto', args=[proyecto_id])}#vista-difusion")


@csrf_exempt
def proyecto_checklist(request, proyecto_id: int):
    try:
        proyecto = Proyecto.objects.get(id=proyecto_id)
    except Proyecto.DoesNotExist:
        return JsonResponse({"ok": False, "error": "Proyecto no encontrado"}, status=404)

    if request.method == "GET":
        _ensure_checklist_defaults(proyecto)
        items = []
        for it in ChecklistItem.objects.filter(proyecto=proyecto).order_by("fase", "fecha_objetivo", "id"):
            items.append({
                "id": it.id,
                "fase": it.fase,
                "titulo": it.titulo,
                "descripcion": it.descripcion,
                "responsable": it.responsable,
                "fecha_objetivo": it.fecha_objetivo.isoformat() if it.fecha_objetivo else "",
                "estado": it.estado,
                "gasto_id": it.gasto_id,
            })
        return JsonResponse({"ok": True, "items": items})

    if request.method != "POST":
        return JsonResponse({"ok": False, "error": "Método no permitido"}, status=405)

    try:
        data = json.loads(request.body or "{}")
        return JsonResponse({"ok": False, "error": "Las tareas son predefinidas"}, status=405)
    except Exception as e:
        return JsonResponse({"ok": False, "error": str(e)}, status=400)


@csrf_exempt
def proyecto_checklist_detalle(request, proyecto_id: int, item_id: int):
    try:
        item = ChecklistItem.objects.select_related("proyecto").get(id=item_id, proyecto_id=proyecto_id)
    except ChecklistItem.DoesNotExist:
        return JsonResponse({"ok": False, "error": "Item no encontrado"}, status=404)

    if request.method == "DELETE":
        return JsonResponse({"ok": False, "error": "No se permite borrar tareas"}, status=405)

    if request.method not in ("PUT", "PATCH"):
        return JsonResponse({"ok": False, "error": "Método no permitido"}, status=405)

    try:
        data = json.loads(request.body or "{}")
        if "descripcion" in data:
            item.descripcion = (data.get("descripcion") or "").strip() or None
        if "responsable" in data:
            item.responsable = (data.get("responsable") or "").strip() or None
        if "fecha_objetivo" in data:
            item.fecha_objetivo = _parse_date(data.get("fecha_objetivo")) or item.fecha_objetivo
        if "estado" in data:
            item.estado = (data.get("estado") or item.estado)
            if item.estado == "hecho" and not item.fecha_objetivo:
                item.fecha_objetivo = timezone.now().date()

        item.save()
        return JsonResponse({"ok": True})
    except Exception as e:
        return JsonResponse({"ok": False, "error": str(e)}, status=400)


@csrf_exempt
def proyecto_participaciones(request, proyecto_id: int):
    try:
        proyecto = Proyecto.objects.get(id=proyecto_id)
    except Proyecto.DoesNotExist:
        return JsonResponse({"ok": False, "error": "Proyecto no encontrado"}, status=404)

    if request.method == "GET":
        capital_objetivo = Decimal("0")
        try:
            snap = getattr(proyecto, "snapshot_datos", {}) or {}
            capital_objetivo = _capital_objetivo_desde_memoria(proyecto, snap)
            capital_objetivo = Decimal(str(capital_objetivo))
        except Exception:
            capital_objetivo = Decimal("0")

        participaciones = []
        qs = Participacion.objects.filter(proyecto=proyecto).select_related("cliente").order_by("-id")
        total_confirmadas = qs.filter(estado="confirmada").aggregate(total=Sum("importe_invertido")).get("total") or Decimal("0")
        total_confirmadas = _parse_decimal(total_confirmadas) or Decimal("0")
        for p in qs:
            pct = None
            if capital_objetivo > 0:
                pct = (p.importe_invertido / capital_objetivo) * Decimal("100")
            elif total_confirmadas > 0:
                pct = (p.importe_invertido / total_confirmadas) * Decimal("100")
            else:
                pct = p.porcentaje_participacion
            participaciones.append({
                "id": p.id,
                "cliente_id": p.cliente_id,
                "cliente_nombre": p.cliente.nombre,
                "importe_invertido": float(p.importe_invertido),
                "porcentaje_participacion": float(pct) if pct is not None else None,
                "fecha": p.creado.isoformat(),
                "estado": p.estado,
            })
        total = sum([p["importe_invertido"] for p in participaciones]) if participaciones else 0
        return JsonResponse({"ok": True, "participaciones": participaciones, "total": total})

    if request.method != "POST":
        return JsonResponse({"ok": False, "error": "Método no permitido"}, status=405)

    try:
        data = json.loads(request.body or "{}")
        cliente_id = data.get("cliente_id")
        importe = _parse_decimal(data.get("importe_invertido"))
        if not cliente_id or importe is None:
            return JsonResponse({"ok": False, "error": "Faltan campos obligatorios"}, status=400)

        try:
            cliente = Cliente.objects.get(id=cliente_id)
        except Cliente.DoesNotExist:
            return JsonResponse({"ok": False, "error": "Cliente no encontrado"}, status=404)

        porcentaje = None
        try:
            snap = getattr(proyecto, "snapshot_datos", {}) or {}
            capital_objetivo = _capital_objetivo_desde_memoria(proyecto, snap)
            capital_objetivo = Decimal(str(capital_objetivo))
            if capital_objetivo > 0:
                porcentaje = (importe / capital_objetivo) * Decimal("100")
        except Exception:
            porcentaje = None

        Participacion.objects.create(
            proyecto=proyecto,
            cliente=cliente,
            importe_invertido=importe,
            porcentaje_participacion=porcentaje,
            estado="confirmada",
        )
        return JsonResponse({"ok": True})
    except Exception as e:
        return JsonResponse({"ok": False, "error": str(e)}, status=400)


@csrf_exempt
def proyecto_participacion_detalle(request, proyecto_id: int, participacion_id: int):
    try:
        part = Participacion.objects.select_related("proyecto").get(id=participacion_id, proyecto_id=proyecto_id)
    except Participacion.DoesNotExist:
        return JsonResponse({"ok": False, "error": "Participación no encontrada"}, status=404)

    if request.method == "PATCH":
        try:
            data = json.loads(request.body or "{}")
            if "estado" in data:
                nuevo_estado = (data.get("estado") or part.estado)
                if nuevo_estado != part.estado:
                    part.estado = nuevo_estado
                    # Comunicación automática al inversor
                    try:
                        perfil = getattr(part.cliente, "perfil_inversor", None)
                        if perfil and _notificar_inversores_habilitado(part.proyecto):
                            titulo = "Actualización de tu inversión"
                            mensaje = f"Tu participación en {part.proyecto.nombre} ha cambiado a estado: {nuevo_estado}."
                            _crear_comunicacion(request, perfil, part.proyecto, titulo, mensaje)
                    except Exception:
                        pass
            part.save()
            return JsonResponse({"ok": True})
        except Exception as e:
            return JsonResponse({"ok": False, "error": str(e)}, status=400)

    if request.method == "DELETE":
        part.delete()
        return JsonResponse({"ok": True})

    return JsonResponse({"ok": False, "error": "Método no permitido"}, status=405)


@csrf_exempt
def proyecto_solicitudes(request, proyecto_id: int):
    try:
        proyecto = Proyecto.objects.get(id=proyecto_id)
    except Proyecto.DoesNotExist:
        return JsonResponse({"ok": False, "error": "Proyecto no encontrado"}, status=404)

    if request.method == "GET":
        solicitudes = []
        for s in SolicitudParticipacion.objects.filter(proyecto=proyecto).select_related("inversor", "inversor__cliente"):
            decision_by = None
            try:
                if s.decision_by:
                    decision_by = s.decision_by.get_full_name() or s.decision_by.get_username()
            except Exception:
                decision_by = None
            solicitudes.append({
                "id": s.id,
                "cliente_nombre": s.inversor.cliente.nombre,
                "importe_solicitado": float(s.importe_solicitado),
                "estado": s.estado,
                "fecha": s.creado.isoformat(),
                "decision_by": decision_by,
                "decision_at": s.decision_at.isoformat() if s.decision_at else None,
            })
        return JsonResponse({"ok": True, "solicitudes": solicitudes})

    return JsonResponse({"ok": False, "error": "Método no permitido"}, status=405)


@csrf_exempt
def proyecto_solicitud_detalle(request, proyecto_id: int, solicitud_id: int):
    try:
        solicitud = SolicitudParticipacion.objects.select_related("proyecto", "inversor", "inversor__cliente").get(
            id=solicitud_id, proyecto_id=proyecto_id
        )
    except SolicitudParticipacion.DoesNotExist:
        return JsonResponse({"ok": False, "error": "Solicitud no encontrada"}, status=404)

    if request.method != "PATCH":
        return JsonResponse({"ok": False, "error": "Método no permitido"}, status=405)

    try:
        data = json.loads(request.body or "{}")
        estado = (data.get("estado") or "").strip()
        if not data.get("confirm"):
            return JsonResponse({"ok": False, "error": "Confirmación requerida"}, status=400)
        if estado not in ("aprobada", "rechazada", "pendiente"):
            return JsonResponse({"ok": False, "error": "Estado inválido"}, status=400)
        solicitud.estado = estado
        if estado == "pendiente":
            solicitud.decision_by = None
            solicitud.decision_at = None
        else:
            solicitud.decision_by = request.user if request.user.is_authenticated else None
            solicitud.decision_at = timezone.now()
        solicitud.save()

        if estado == "aprobada":
            # Crear participación confirmada si no existe una igual
            Participacion.objects.create(
                proyecto=solicitud.proyecto,
                cliente=solicitud.inversor.cliente,
                importe_invertido=solicitud.importe_solicitado,
                estado="confirmada",
            )
        # Comunicación automática
        try:
            titulo = "Estado de tu solicitud"
            mensaje = f"Tu solicitud en {solicitud.proyecto.nombre} ha sido {estado}."
            if _notificar_inversores_habilitado(solicitud.proyecto):
                _crear_comunicacion(request, solicitud.inversor, solicitud.proyecto, titulo, mensaje)
        except Exception:
            pass
        return JsonResponse({"ok": True})
    except Exception as e:
        return JsonResponse({"ok": False, "error": str(e)}, status=400)


def proyecto_difusion(request, proyecto_id: int):
    if request.method != "POST":
        return redirect(f"{reverse('core:proyecto', args=[proyecto_id])}#vista-inversores")
    if not (is_admin_user(request.user) or use_custom_permissions(request.user)):
        messages.error(request, "No tienes permisos para difundir proyectos.")
        return redirect(f"{reverse('core:proyecto', args=[proyecto_id])}#vista-inversores")

    proyecto = get_object_or_404(Proyecto, id=proyecto_id)
    clientes_ids = []
    for raw in request.POST.getlist("difusion_clientes"):
        try:
            clientes_ids.append(int(raw))
        except Exception:
            continue

    clientes = list(Cliente.objects.filter(id__in=clientes_ids).order_by("nombre"))
    proyecto.difusion_clientes.set(clientes)

    accion = (request.POST.get("accion") or "").strip().lower()
    if accion != "enviar":
        messages.success(request, "Destinatarios de difusión actualizados.")
        return redirect(f"{reverse('core:proyecto', args=[proyecto_id])}#vista-inversores")

    if not clientes:
        messages.error(request, "Selecciona al menos un destinatario para difundir el proyecto.")
        return redirect(f"{reverse('core:proyecto', args=[proyecto_id])}#vista-inversores")

    perfiles = []
    perfiles_map = {}
    for perfil in InversorPerfil.objects.filter(cliente__in=clientes).select_related("cliente"):
        perfiles.append(perfil)
        perfiles_map[perfil.cliente_id] = perfil
    for cliente in clientes:
        if cliente.id not in perfiles_map:
            perfil, _ = InversorPerfil.objects.get_or_create(cliente=cliente)
            perfiles.append(perfil)

    proyecto_id_val = proyecto.id
    for perfil in perfiles:
        visibles = perfil.proyectos_visibles if isinstance(perfil.proyectos_visibles, list) else []
        visibles = [int(v) for v in visibles if str(v).isdigit()]
        if proyecto_id_val not in visibles:
            visibles.append(proyecto_id_val)
            perfil.proyectos_visibles = visibles
            perfil.save(update_fields=["proyectos_visibles"])

    snapshot = _get_snapshot_comunicacion(proyecto)
    resultado_mem = _resultado_desde_memoria(proyecto, snapshot) if isinstance(snapshot, dict) else {}

    attachment = None
    try:
        presentaciones = DocumentoProyecto.objects.filter(
            proyecto=proyecto,
            categoria="presentacion",
        ).order_by("-creado", "-id")
        for doc in presentaciones:
            if (doc.archivo.name or "").lower().endswith(".pdf"):
                pdf_bytes = _documento_pdf_bytes(request, doc)
                if pdf_bytes:
                    nombre = os.path.basename(doc.archivo.name) or "presentacion.pdf"
                    attachment = [(nombre, pdf_bytes, "application/pdf")]
                break
    except Exception:
        attachment = None

    enviados = 0
    for perfil in perfiles:
        part = SimpleNamespace(
            cliente=perfil.cliente,
            importe_invertido=0,
            beneficio_neto_override=None,
            beneficio_override_data={},
        )
        ctx = _build_comunicacion_context(proyecto, part, snapshot, resultado_mem, 0.0)
        try:
            ctx["portal_link"] = request.build_absolute_uri(
                reverse("core:inversor_portal", args=[perfil.token])
            )
        except Exception:
            ctx["portal_link"] = ""
        titulo, mensaje = _render_comunicacion_template("presentacion", ctx)
        if not titulo or not mensaje:
            continue
        _crear_comunicacion(request, perfil, proyecto, titulo, mensaje, attachments=attachment)
        enviados += 1

    if enviados:
        messages.success(request, f"Difusión enviada a {enviados} destinatarios.")
    else:
        messages.error(request, "No se pudo enviar la difusión.")
    return redirect(f"{reverse('core:proyecto', args=[proyecto_id])}#vista-inversores")


@csrf_exempt
def proyecto_comunicaciones(request, proyecto_id: int):
    try:
        proyecto = Proyecto.objects.get(id=proyecto_id)
    except Proyecto.DoesNotExist:
        return JsonResponse({"ok": False, "error": "Proyecto no encontrado"}, status=404)

    if request.method == "GET":
        comunicaciones = []
        for c in ComunicacionInversor.objects.filter(proyecto=proyecto).select_related("inversor", "inversor__cliente"):
            comunicaciones.append({
                "id": c.id,
                "cliente_nombre": c.inversor.cliente.nombre,
                "titulo": c.titulo,
                "mensaje": c.mensaje,
                "fecha": c.creado.isoformat(),
            })
        docs = []
        for doc in DocumentoProyecto.objects.filter(proyecto=proyecto, categoria="inmueble").order_by("-creado", "-id"):
            nombre = (doc.archivo.name or "").lower()
            if nombre and not nombre.endswith(".pdf"):
                continue
            docs.append({
                "id": doc.id,
                "titulo": doc.titulo,
                "categoria": doc.categoria,
            })
        templates = [
            {"key": k, "label": v.get("label", k)}
            for k, v in _comunicacion_templates().items()
        ]
        return JsonResponse(
            {"ok": True, "comunicaciones": comunicaciones, "templates": templates, "documentos": docs}
        )

    if request.method != "POST":
        return JsonResponse({"ok": False, "error": "Método no permitido"}, status=405)

    try:
        data = json.loads(request.body or "{}")
        template_key = (data.get("template_key") or "").strip()
        preview_only = bool(data.get("preview_only"))
        doc_ids = data.get("doc_ids") or []
        if not isinstance(doc_ids, list):
            doc_ids = []
        anexos = list(
            DocumentoProyecto.objects.filter(
                proyecto=proyecto,
                categoria="inmueble",
                id__in=doc_ids,
            )
        )

        participaciones = (
            Participacion.objects.filter(proyecto=proyecto, estado="confirmada")
            .select_related("cliente")
            .order_by("creado", "id")
        )
        total_destinatarios = participaciones.count()

        total_proj = (
            Participacion.objects.filter(proyecto=proyecto, estado="confirmada")
            .aggregate(total=Sum("importe_invertido"))
            .get("total")
            or 0
        )
        total_proj = float(total_proj or 0)

        snapshot = _get_snapshot_comunicacion(proyecto)
        resultado_mem = _resultado_desde_memoria(proyecto, snapshot) if isinstance(snapshot, dict) else {}

        def _build_context(part: Participacion, perfil: InversorPerfil | None = None) -> dict:
            ctx = _build_comunicacion_context(proyecto, part, snapshot, resultado_mem, total_proj)
            if perfil and request is not None:
                try:
                    portal_url = request.build_absolute_uri(reverse("core:inversor_portal", args=[perfil.token]))
                    ctx["portal_link"] = portal_url
                except Exception:
                    ctx["portal_link"] = ""
            else:
                ctx["portal_link"] = ""
            return ctx

        if template_key:
            if not total_destinatarios:
                return JsonResponse({"ok": False, "error": "No hay inversores confirmados en el proyecto."}, status=400)

            if preview_only:
                part = participaciones.first()
                perfil = InversorPerfil.objects.filter(cliente=part.cliente).first()
                ctx = _build_context(part, perfil=perfil)
                titulo, mensaje = _render_comunicacion_template(template_key, ctx)
                return JsonResponse(
                    {
                        "ok": True,
                        "titulo": titulo,
                        "mensaje": mensaje,
                        "destinatarios": total_destinatarios,
                    }
                )

            count = 0
            for part in participaciones:
                perfil, _ = InversorPerfil.objects.get_or_create(cliente=part.cliente)
                ctx = _build_context(part, perfil=perfil)
                titulo, mensaje = _render_comunicacion_template(template_key, ctx)
                if not titulo or not mensaje:
                    continue
                attachments = None
                carta_pdf = _build_carta_pdf(request, titulo, mensaje, perfil, proyecto)
                merged_pdf = _merge_pdf_with_anexos(carta_pdf, anexos, request=request) if carta_pdf else None
                if merged_pdf:
                    attachments = [("carta_inversure.pdf", merged_pdf, "application/pdf")]
                _crear_comunicacion(request, perfil, proyecto, titulo, mensaje, attachments=attachments)
                count += 1
            return JsonResponse({"ok": True, "enviadas": count})

        titulo = (data.get("titulo") or "").strip()
        mensaje = (data.get("mensaje") or "").strip()
        if not titulo or not mensaje:
            return JsonResponse({"ok": False, "error": "Título y mensaje son obligatorios"}, status=400)

        count = 0
        for part in participaciones:
            perfil, _ = InversorPerfil.objects.get_or_create(cliente=part.cliente)
            attachments = None
            carta_pdf = _build_carta_pdf(request, titulo, mensaje, perfil, proyecto)
            merged_pdf = _merge_pdf_with_anexos(carta_pdf, anexos, request=request) if carta_pdf else None
            if merged_pdf:
                attachments = [("carta_inversure.pdf", merged_pdf, "application/pdf")]
            _crear_comunicacion(request, perfil, proyecto, titulo, mensaje, attachments=attachments)
            count += 1
        return JsonResponse({"ok": True, "enviadas": count})
    except Exception as e:
        return JsonResponse({"ok": False, "error": str(e)}, status=400)


def inversor_comunicacion_preview(request, perfil_id: int):
    if request.method != "POST":
        return JsonResponse({"ok": False, "error": "Método no permitido"}, status=405)
    if not request.user.is_authenticated:
        return JsonResponse({"ok": False, "error": "No autorizado"}, status=403)
    perfil = get_object_or_404(InversorPerfil, id=perfil_id)
    try:
        data = json.loads(request.body or "{}")
        proyecto_id = data.get("proyecto_id")
        if not proyecto_id:
            return JsonResponse({"ok": False, "error": "Proyecto requerido"}, status=400)
        proyecto = get_object_or_404(Proyecto, id=proyecto_id)

        template_key = (data.get("template_key") or "").strip()
        preview_only = bool(data.get("preview_only"))
        titulo = (data.get("titulo") or "").strip()
        mensaje = (data.get("mensaje") or "").strip()

        part = (
            Participacion.objects.filter(
                cliente=perfil.cliente,
                proyecto=proyecto,
                estado="confirmada",
            )
            .order_by("creado", "id")
            .first()
        )
        if not part:
            return JsonResponse(
                {"ok": False, "error": "El inversor no tiene participación confirmada en este proyecto."},
                status=400,
            )

        snapshot = _get_snapshot_comunicacion(proyecto)
        resultado_mem = _resultado_desde_memoria(proyecto, snapshot) if isinstance(snapshot, dict) else {}
        total_proj = (
            Participacion.objects.filter(proyecto=proyecto, estado="confirmada")
            .aggregate(total=Sum("importe_invertido"))
            .get("total")
            or 0
        )
        total_proj = float(total_proj or 0)
        ctx = _build_comunicacion_context(proyecto, part, snapshot, resultado_mem, total_proj)
        if request is not None:
            try:
                portal_url = request.build_absolute_uri(reverse("core:inversor_portal", args=[perfil.token]))
                ctx["portal_link"] = portal_url
            except Exception:
                ctx["portal_link"] = ""
        else:
            ctx["portal_link"] = ""

        if template_key:
            titulo, mensaje = _render_comunicacion_template(template_key, ctx)
        if not titulo or not mensaje:
            return JsonResponse({"ok": False, "error": "Título y mensaje son obligatorios"}, status=400)

        if preview_only:
            return JsonResponse({"ok": True, "titulo": titulo, "mensaje": mensaje})

        doc_ids = data.get("doc_ids") or []
        if not isinstance(doc_ids, list):
            doc_ids = []
        anexos = list(
            DocumentoProyecto.objects.filter(
                proyecto=proyecto,
                categoria="inmueble",
                id__in=doc_ids,
            )
        )

        carta_pdf, carta_error = _build_carta_pdf_with_error(request, titulo, mensaje, perfil, proyecto)
        merged_pdf = _merge_pdf_with_anexos(carta_pdf, anexos, request=request) if carta_pdf else None
        if not merged_pdf:
            detalle = f": {carta_error}" if carta_error else ""
            return JsonResponse({"ok": False, "error": f"No se pudo generar el PDF{detalle}"}, status=400)

        filename = f"carta_inversor_{perfil.id}_{proyecto.id}.pdf"
        response = HttpResponse(merged_pdf, content_type="application/pdf")
        response["Content-Disposition"] = f'inline; filename="{filename}"'
        return response
    except Exception as e:
        return JsonResponse({"ok": False, "error": str(e)}, status=400)
