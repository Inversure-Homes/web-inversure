from django.shortcuts import get_object_or_404, render

from .models import Noticia


def landing_home(request):
    hero = {
        "tag": "Inversión inmobiliaria con trazabilidad real",
        "title": "Control total de cada operación",
        "subtitle": "Seguimiento económico, documental y operativo para inversores y equipo interno en un solo sistema.",
        "cta_primary_text": "Entrar en la plataforma",
        "cta_primary_url": "/app/login/",
        "cta_secondary_text": "Últimas noticias",
        "cta_secondary_url": "#noticias",
        "meta": [
            {"value": "+120", "label": "operaciones analizadas"},
            {"value": "100", "label": "trazabilidad documental"},
            {"value": "24h", "label": "tiempo de respuesta"},
        ],
        "panel_title": "Estado del proyecto",
        "panel_text": "Documento, gastos y retornos alineados para comité.",
        "panel_footer": "Progreso operativo actualizado",
    }
    secciones = [
        {
            "icon": "bi-shield-check",
            "title": "Control de inversión",
            "text": "Seguimiento total del capital desde captación hasta liquidación.",
        },
        {
            "icon": "bi-journal-bookmark",
            "title": "Memoria económica",
            "text": "Registro de gastos e ingresos con estimados y reales.",
        },
        {
            "icon": "bi-graph-up-arrow",
            "title": "Rentabilidad transparente",
            "text": "KPIs claros y documentación verificable en cada etapa.",
        },
    ]
    proyectos = [
        {
            "titulo": "COÍN",
            "ubicacion": "Málaga",
            "anio": "2025",
            "plazo": "3 meses",
            "rentabilidad": "11,63 %",
            "acceso_minimo": "10.000 €",
            "inversion_total": "148.000 €",
            "beneficio_estimado": "17.200 €",
            "estado": "En curso",
        },
        {
            "titulo": "Sotogrande",
            "ubicacion": "Cádiz",
            "anio": "2025",
            "plazo": "3 meses",
            "rentabilidad": "4,16 %",
            "acceso_minimo": "10.000 €",
            "inversion_total": "240.000 €",
            "beneficio_estimado": "9.980 €",
            "estado": "Finalizado",
        },
        {
            "titulo": "Torremolinos",
            "ubicacion": "Málaga",
            "anio": "2025",
            "plazo": "3 meses",
            "rentabilidad": "8,22 %",
            "acceso_minimo": "10.000 €",
            "inversion_total": "162.000 €",
            "beneficio_estimado": "13.300 €",
            "estado": "Finalizado",
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
    noticias = Noticia.objects.filter(estado="publicado").order_by("-fecha_publicacion", "-id")[:3]
    return render(
        request,
        "landing/home.html",
        {
            "hero": hero,
            "secciones": secciones,
            "proyectos": proyectos,
            "quienes_somos": quienes_somos,
            "transparencia": transparencia,
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
