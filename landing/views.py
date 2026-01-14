from django.shortcuts import get_object_or_404, render

from .models import Hero, Noticia, Seccion


def landing_home(request):
    hero = Hero.objects.filter(activo=True).order_by("-actualizado", "-id").first()
    secciones = Seccion.objects.filter(activo=True).order_by("orden", "id")
    noticias = Noticia.objects.filter(estado="publicado").order_by("-fecha_publicacion", "-id")[:3]
    return render(
        request,
        "landing/home.html",
        {
            "hero": hero,
            "secciones": secciones,
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
