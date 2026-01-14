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
]
