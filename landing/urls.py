from django.urls import path

from . import views

app_name = "landing"

urlpatterns = [
    path("legacy/", views.landing_home, name="home"),
    path("noticias/", views.noticias_list, name="noticias_list"),
    path("noticias/<slug:slug>/", views.noticia_detail, name="noticia_detail"),
    path("privacidad/", views.privacidad, name="privacidad"),
    path("cookies/", views.cookies, name="cookies"),
    path("terminos/", views.terminos, name="terminos"),
    path("marketing/", views.marketing_dashboard, name="marketing_dashboard"),
    path("marketing/hero/", views.hero_edit, name="hero_edit"),
    path("marketing/hero/<int:hero_id>/", views.hero_edit, name="hero_edit_id"),
    path("marketing/seccion/nueva/", views.seccion_edit, name="seccion_new"),
    path("marketing/seccion/<int:seccion_id>/", views.seccion_edit, name="seccion_edit"),
    path("marketing/seccion/<int:seccion_id>/borrar/", views.seccion_delete, name="seccion_delete"),
    path("marketing/noticia/nueva/", views.noticia_edit, name="noticia_new"),
    path("marketing/noticia/<int:noticia_id>/", views.noticia_edit, name="noticia_edit"),
    path("marketing/noticia/<int:noticia_id>/borrar/", views.noticia_delete, name="noticia_delete"),
    path("marketing/media/", views.media_library, name="media_library"),
    path("marketing/media/<int:asset_id>/borrar/", views.media_delete, name="media_delete"),
]
