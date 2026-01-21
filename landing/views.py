from django.shortcuts import get_object_or_404, render
from django.templatetags.static import static
from django.utils import timezone

from core.models import Proyecto
from core.views import _build_dashboard_context
from .models import Noticia


def landing_home(request):
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
            return float(value)
        except Exception:
            return default

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
    estados_finalizados = {"cerrado", "cerrado_positivo", "cerrado_negativo", "finalizado", "vendido"}
    proyectos = []
    for proyecto in (
        Proyecto.objects.filter(mostrar_en_landing=True, estado__in=estados_finalizados).order_by("-id")
    ):
        meses = getattr(proyecto, "meses", None)
        proyectos.append(
            {
                "titulo": proyecto.nombre or getattr(proyecto, "nombre_proyecto", "") or "Proyecto",
                "ubicacion": proyecto.direccion or "—",
                "anio": str(proyecto.fecha.year) if proyecto.fecha else str(timezone.now().year),
                "plazo": f"{int(meses)} meses" if meses else "—",
                "beneficio_neto_pct": _fmt_pct(_as_float(getattr(proyecto, "roi", None))),
                "estado": proyecto.estado or "—",
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
