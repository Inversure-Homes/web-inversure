from django.contrib.auth.decorators import login_required, user_passes_test
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse

from .forms import HeroForm, NoticiaForm, SeccionForm, MediaAssetForm
from .models import Hero, Noticia, Seccion, MediaAsset


def _is_marketing(user):
    return user.is_authenticated and (user.is_staff or user.groups.filter(name="marketing").exists())


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


@login_required
@user_passes_test(_is_marketing)
def marketing_dashboard(request):
    hero = Hero.objects.order_by("-actualizado", "-id").first()
    secciones = Seccion.objects.order_by("orden", "id")
    noticias = Noticia.objects.order_by("-fecha_publicacion", "-id")[:20]
    return render(
        request,
        "landing/marketing_dashboard.html",
        {
            "hero": hero,
            "secciones": secciones,
            "noticias": noticias,
        },
    )


@login_required
@user_passes_test(_is_marketing)
def hero_edit(request, hero_id=None):
    hero = Hero.objects.filter(id=hero_id).first() if hero_id else Hero.objects.order_by("-actualizado", "-id").first()
    if request.method == "POST":
        form = HeroForm(request.POST, request.FILES, instance=hero)
        if form.is_valid():
            form.save()
            return redirect("landing:marketing_dashboard")
    else:
        form = HeroForm(instance=hero)
    return render(request, "landing/hero_form.html", {"form": form, "hero": hero})


@login_required
@user_passes_test(_is_marketing)
def seccion_edit(request, seccion_id=None):
    seccion = Seccion.objects.filter(id=seccion_id).first() if seccion_id else None
    if request.method == "POST":
        form = SeccionForm(request.POST, request.FILES, instance=seccion)
        if form.is_valid():
            form.save()
            return redirect("landing:marketing_dashboard")
    else:
        form = SeccionForm(instance=seccion)
    return render(request, "landing/seccion_form.html", {"form": form, "seccion": seccion})


@login_required
@user_passes_test(_is_marketing)
def seccion_delete(request, seccion_id):
    seccion = get_object_or_404(Seccion, id=seccion_id)
    if request.method == "POST":
        seccion.delete()
        return redirect("landing:marketing_dashboard")
    return render(request, "landing/confirm_delete.html", {"obj": seccion, "titulo": "Eliminar sección"})


@login_required
@user_passes_test(_is_marketing)
def noticia_edit(request, noticia_id=None):
    noticia = Noticia.objects.filter(id=noticia_id).first() if noticia_id else None
    if request.method == "POST":
        form = NoticiaForm(request.POST, request.FILES, instance=noticia)
        if form.is_valid():
            form.save()
            return redirect("landing:marketing_dashboard")
    else:
        form = NoticiaForm(instance=noticia)
    return render(request, "landing/noticia_form.html", {"form": form, "noticia": noticia})


@login_required
@user_passes_test(_is_marketing)
def noticia_delete(request, noticia_id):
    noticia = get_object_or_404(Noticia, id=noticia_id)
    if request.method == "POST":
        noticia.delete()
        return redirect("landing:marketing_dashboard")
    return render(request, "landing/confirm_delete.html", {"obj": noticia, "titulo": "Eliminar noticia"})


@login_required
@user_passes_test(_is_marketing)
def media_library(request):
    if request.method == "POST":
        form = MediaAssetForm(request.POST, request.FILES)
        if form.is_valid():
            form.save()
            return redirect("landing:media_library")
    else:
        form = MediaAssetForm()
    assets = MediaAsset.objects.all()
    return render(
        request,
        "landing/marketing_media.html",
        {"form": form, "assets": assets},
    )


@login_required
@user_passes_test(_is_marketing)
def media_delete(request, asset_id):
    asset = get_object_or_404(MediaAsset, id=asset_id)
    if request.method == "POST":
        asset.delete()
        return redirect("landing:media_library")
    return render(request, "landing/confirm_delete.html", {"obj": asset, "titulo": "Eliminar imagen"})
