from decimal import Decimal

from django.core.cache import cache
from django.core.signing import BadSignature, SignatureExpired, TimestampSigner
from django.shortcuts import get_object_or_404, redirect, render
from django.templatetags.static import static
from django.utils import timezone

from core.models import DocumentoProyecto, GastoProyecto, IngresoProyecto, Proyecto
from core.views import _build_dashboard_context, _s3_presigned_url
from .models import LandingLead, Noticia


def landing_home(request):
    signer = TimestampSigner()
    lead_success = request.GET.get("lead")
    lead_error = None
    lead_token = signer.sign(str(timezone.now().timestamp()))

    if request.method == "POST":
        lead_tipo = (request.POST.get("lead_tipo") or "").strip()
        nombre = (request.POST.get("nombre") or "").strip()
        email = (request.POST.get("email") or "").strip()
        telefono = (request.POST.get("telefono") or "").strip()
        capital = (request.POST.get("capital") or "").strip()
        ubicacion = (request.POST.get("ubicacion") or "").strip()
        mensaje = (request.POST.get("mensaje") or "").strip()
        honeypot = (request.POST.get("website") or "").strip()
        token = (request.POST.get("lead_token") or "").strip()
        ip_addr = request.META.get("HTTP_X_FORWARDED_FOR", "").split(",")[0].strip() or request.META.get("REMOTE_ADDR", "")

        errors = []
        if lead_tipo not in ("inversor", "oportunidad"):
            errors.append("tipo")
        if not nombre:
            errors.append("nombre")
        if not email:
            errors.append("email")
        if not mensaje:
            errors.append("mensaje")
        if lead_tipo == "oportunidad" and not ubicacion:
            errors.append("ubicacion")
        if honeypot:
            errors.append("honeypot")

        try:
            token_value = signer.unsign(token, max_age=86400)
            token_time = float(token_value)
            if timezone.now().timestamp() - token_time < 3:
                errors.append("timing")
        except (BadSignature, SignatureExpired, ValueError):
            errors.append("token")

        if ip_addr:
            rate_key = f"landing_lead:{ip_addr}:{lead_tipo or 'any'}"
            try:
                attempts = cache.incr(rate_key)
            except ValueError:
                cache.set(rate_key, 1, timeout=3600)
                attempts = 1
            if attempts > 5:
                errors.append("rate")

        if errors:
            lead_error = {"tipo": lead_tipo or "inversor", "fields": errors}
        else:
            LandingLead.objects.create(
                tipo=lead_tipo,
                nombre=nombre,
                email=email,
                telefono=telefono,
                capital=capital,
                ubicacion=ubicacion,
                mensaje=mensaje,
                origen_url=request.build_absolute_uri(),
                origen_ref=request.META.get("HTTP_REFERER", ""),
            )
            return redirect(f"{request.path}?lead={lead_tipo}")
    def _fmt_pct(value):
        if value is None:
            return "—"
        return f"{value:.2f} %".replace(".", ",")

    def _fmt_int(value):
        if value is None:
            return "—"
        return f"{int(value):,}".replace(",", ".")

    def _as_float(value, default=None):
        try:
            if isinstance(value, str):
                value = value.strip().replace("%", "").replace(",", ".")
            return float(value)
        except Exception:
            return default

    def _roi_memoria(proyecto):
        gastos = list(GastoProyecto.objects.filter(proyecto=proyecto))
        ingresos = list(IngresoProyecto.objects.filter(proyecto=proyecto))
        if not gastos and not ingresos:
            return None

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

        base_precio = proyecto.precio_compra_inmueble or proyecto.precio_propiedad or Decimal("0")
        cats_adq = {"adquisicion", "reforma", "seguridad", "operativos", "financieros", "legales", "otros"}
        gastos_adq_estimado = _sum_importes([_importe_estimado(g) for g in gastos if g.categoria in cats_adq])
        gastos_adq_real = _sum_importes([_importe_real(g) for g in gastos if g.categoria in cats_adq])

        base_est = base_precio + gastos_adq_estimado
        base_real = base_precio + gastos_adq_real

        if ingresos_reales or gastos_reales:
            if base_real > 0:
                return float((beneficio_real / base_real) * Decimal("100"))
        if base_est > 0:
            return float((beneficio_estimado / base_est) * Decimal("100"))
        return None

    hero = {
        "tag": "Inversión inmobiliaria con trazabilidad real",
        "title": "Control total de cada operación",
        "subtitle": "Seguimiento económico, documental y operativo para inversores y equipo interno en un solo sistema.",
        "cta_primary_text": "Entrar en la plataforma",
        "cta_primary_url": "/app/login/",
        "cta_secondary_text": "Últimas noticias",
        "cta_secondary_url": "#noticias",
        "bg_image": "landing/assets/hero_growth.jpg",
        "panel_image": "landing/assets/hero_model.jpg",
        "meta": [
            {"value": "+120", "label": "operaciones analizadas"},
            {"value": "100", "label": "trazabilidad documental"},
            {"value": "24h", "label": "tiempo de respuesta"},
        ],
        "panel_title": "Desviación estimado vs real",
        "panel_text": "",
        "panel_footer": "Resultados del portfolio",
    }
    secciones = [
        {
            "icon": "bi-file-earmark-text",
            "title": "Informe PDF para inversores",
            "text": "Documentos listos para comité y seguimiento con datos anonimizados.",
            "image": "landing/assets/erp_pdf_report.svg",
            "image_alt": "Mockup de informe PDF para inversores",
        },
        {
            "icon": "bi-people",
            "title": "Espacio del inversor",
            "text": "Vista personalizada con métricas clave y evolución de la inversión.",
            "image": "landing/assets/erp_inversor_portal.svg",
            "image_alt": "Mockup del espacio del inversor",
        },
        {
            "icon": "bi-graph-up-arrow",
            "title": "Rentabilidad transparente",
            "text": "KPIs claros y documentación verificable en cada etapa.",
            "image": "landing/assets/erp_kpis.svg",
            "image_alt": "Vista de rentabilidad transparente",
        },
    ]
    def _doc_url(doc):
        key = getattr(doc.archivo, "name", "") or ""
        signed = _s3_presigned_url(key)
        if signed:
            return signed
        try:
            return request.build_absolute_uri(doc.archivo.url)
        except Exception:
            return doc.archivo.url

    proyectos = []
    for proyecto in Proyecto.objects.filter(mostrar_en_landing=True).order_by("-id"):
        extra = getattr(proyecto, "extra", None)
        landing_cfg = extra.get("landing", {}) if isinstance(extra, dict) else {}
        beneficio_raw = landing_cfg.get("beneficio_neto_pct")
        beneficio_val = _as_float(beneficio_raw)
        if beneficio_val is None:
            beneficio_val = _as_float(getattr(proyecto, "roi", None))
        if beneficio_val is None:
            beneficio_val = _roi_memoria(proyecto)
        plazo_raw = landing_cfg.get("plazo_meses")
        plazo_val = _as_float(plazo_raw, _as_float(getattr(proyecto, "meses", None)))
        focus_x = _as_float(landing_cfg.get("imagen_focus_x"), 50.0)
        focus_y = _as_float(landing_cfg.get("imagen_focus_y"), 50.0)
        imagen_url = ""
        imagen_id = landing_cfg.get("imagen_id")
        publicaciones_cfg = extra.get("publicaciones", {}) if isinstance(extra, dict) else {}
        cabecera_id = publicaciones_cfg.get("cabecera_imagen_id")
        if imagen_id:
            try:
                doc = DocumentoProyecto.objects.filter(
                    id=imagen_id,
                    proyecto=proyecto,
                    categoria="fotografias",
                ).first()
                if doc:
                    imagen_url = _doc_url(doc)
            except Exception:
                imagen_url = ""
        if not imagen_url and cabecera_id:
            try:
                doc = DocumentoProyecto.objects.filter(
                    id=cabecera_id,
                    proyecto=proyecto,
                    categoria="fotografias",
                ).first()
                if doc:
                    imagen_url = _doc_url(doc)
            except Exception:
                imagen_url = ""
        if not imagen_url:
            try:
                doc = DocumentoProyecto.objects.filter(
                    proyecto=proyecto,
                    categoria="fotografias",
                ).order_by("-es_principal", "-creado", "-id").first()
                if doc:
                    imagen_url = _doc_url(doc)
            except Exception:
                imagen_url = ""
        proyectos.append(
            {
                "titulo": landing_cfg.get("titulo") or proyecto.nombre or getattr(proyecto, "nombre_proyecto", "") or "Proyecto",
                "ubicacion": landing_cfg.get("ubicacion") or proyecto.direccion or "—",
                "anio": str(proyecto.fecha.year) if proyecto.fecha else str(timezone.now().year),
                "plazo": f"{int(plazo_val)} meses" if plazo_val else "—",
                "beneficio_neto_pct": _fmt_pct(beneficio_val),
                "estado": proyecto.estado or "—",
                "imagen_url": imagen_url,
                "imagen_focus_x": focus_x,
                "imagen_focus_y": focus_y,
                "imagen": "landing/assets/hero_growth.jpg",
            }
        )
    proyectos_qs = Proyecto.objects.all()
    dashboard_ctx = _build_dashboard_context(request.user)
    dashboard_stats = dashboard_ctx.get("dashboard_stats", {})
    dashboard_stats_fmt = dashboard_ctx.get("dashboard_stats_fmt", {})
    beneficio_deviation = dashboard_ctx.get("beneficio_deviation_chart", [])
    total_estimado = sum(_as_float(item.get("estimado"), 0.0) for item in beneficio_deviation)
    total_real = sum(_as_float(item.get("real"), 0.0) for item in beneficio_deviation)
    desviacion_pct = None
    if total_estimado:
        desviacion_pct = (total_real - total_estimado) / total_estimado * 100.0

    estadisticas = [
        {
            "label": "Inversores activos",
            "value": _fmt_int(dashboard_stats.get("inversores_activos")),
            "detail": "con inversión en vigor",
        },
        {
            "label": "Capital en vigor",
            "value": dashboard_stats_fmt.get("capital_en_vigor", "—"),
            "detail": "capital actualmente invertido",
        },
        {
            "label": "Operaciones",
            "value": _fmt_int(dashboard_stats.get("operaciones")),
            "detail": "proyectos registrados",
        },
        {
            "label": "Desviación estimado vs real",
            "value": _fmt_pct(desviacion_pct),
            "detail": "sobre beneficio estimado",
        },
        {
            "label": "Beneficio acumulado",
            "value": dashboard_stats_fmt.get("beneficio_cerrado_roi_neto_total", "—"),
            "detail": "ROI neto total",
        },
        {
            "label": "Beneficio medio por operación",
            "value": dashboard_stats_fmt.get("beneficio_cerrado_roi_neto_medio", "—"),
            "detail": "ROI neto medio",
        },
    ]
    hero["panel_stats"] = [
        {"label": "Desviación", "value": _fmt_pct(desviacion_pct)},
        {
            "label": "ROI neto acumulado",
            "value": dashboard_stats_fmt.get("beneficio_cerrado_roi_neto_total", "—"),
        },
    ]
    quienes_somos = {
        "intro": (
            "Inversure Homes & Investment es una firma especializada en inversión inmobiliaria "
            "que combina análisis riguroso, control operativo y trazabilidad documental para "
            "proteger el capital y maximizar el retorno en plazos eficientes."
        ),
        "historia": (
            "Nacimos con un objetivo claro: profesionalizar la inversión inmobiliaria para ofrecer "
            "operaciones transparentes, con métricas verificables y una gestión operativa cuidada "
            "en cada fase."
        ),
        "equipo": (
            "Un equipo multidisciplinar formado por Miguel Ángel Pérez Rodríguez (CEO / Dirección "
            "Financiera), Ana Portero Palma (Directora Legal), Daniel García García (Responsable "
            "Comercial) y Marta Ximenez Diaz (Administración)."
        ),
        "valores": "Transparencia real, disciplina operativa y foco en la rentabilidad sostenible.",
    }
    transparencia = {
        "titulo": "Transparencia que genera confianza",
        "texto": "Subidas de documentación, informes de comité y comunicaciones a inversores desde un único sistema.",
        "features": [
            "Checklist operativo por fases",
            "Informes PDF para comité e inversores",
            "Histórico completo de movimientos",
        ],
        "stats": [
            {"label": "ROI medio", "value": "18,4%"},
            {"label": "Operaciones activas", "value": "32"},
            {"label": "Documentos gestionados", "value": "1.820"},
        ],
    }
    reseñas = [
        {
            "nombre": "María G.",
            "texto": "Información clara y seguimiento constante. Me dio mucha tranquilidad como inversora.",
            "rating": 5,
        },
        {
            "nombre": "Javier R.",
            "texto": "Comunicación profesional y datos detallados en cada fase. Muy recomendable.",
            "rating": 5,
        },
        {
            "nombre": "Elena M.",
            "texto": "Transparencia total y soporte cercano. Un antes y un después en inversión.",
            "rating": 5,
        },
    ]
    patrocinadores = [
        {"src": "landing/assets/sponsor_benagalbon.png", "alt": "C.D. Benagalbón"},
        {"src": "landing/assets/sponsor_modernia.jpg", "alt": "Grupo Modernia"},
        {"src": "landing/assets/sponsor_logo_1.jpg", "alt": "Fincas Velázquez"},
        {"src": "landing/assets/sponsor_logo_2.jpg", "alt": "Radio Marca"},
        {"src": "landing/assets/sponsor_logo_3.jpg", "alt": "Portero y Palma"},
        {"src": "landing/assets/sponsor_verifika2.png", "alt": "Verifika2"},
    ]
    noticias = Noticia.objects.filter(estado="publicado").order_by("-fecha_publicacion", "-id")[:3]
    return render(
        request,
        "landing/home.html",
        {
            "hero": hero,
            "secciones": secciones,
            "proyectos": proyectos,
            "estadisticas": estadisticas,
            "quienes_somos": quienes_somos,
            "transparencia": transparencia,
            "reseñas": reseñas,
            "patrocinadores": patrocinadores,
            "noticias": noticias,
            "lead_success": lead_success,
            "lead_error": lead_error,
            "lead_token": lead_token,
        },
    )


def noticias_list(request):
    noticias = Noticia.objects.filter(estado="publicado").order_by("-fecha_publicacion", "-id")
    return render(request, "landing/noticias_list.html", {"noticias": noticias})


def noticia_detail(request, slug: str):
    noticia = get_object_or_404(Noticia, slug=slug, estado="publicado")
    return render(request, "landing/noticia_detail.html", {"noticia": noticia})


def privacidad(request):
    return render(request, "landing/privacidad.html")


def cookies(request):
    return render(request, "landing/cookies.html")


def terminos(request):
    return render(request, "landing/terminos.html")


def maintenance(request):
    return render(request, "landing/maintenance.html")
