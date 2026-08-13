from django.urls import path

from . import views

app_name = "landing"

urlpatterns = [
    path("", views.landing_home, name="home"),
    # Mismo nombre en dos rutas: `reverse("landing:home")` devolvía «/legacy/»,
    # porque gana la última declarada. Lo destapó el sitemap, que anunciaba
    # «/legacy/» como página principal del sitio.
    path("legacy/", views.landing_home, name="home_legacy"),
    path("mantenimiento/", views.maintenance, name="maintenance"),
    path("noticias/", views.noticias_list, name="noticias_list"),
    path("noticias/<slug:slug>/", views.noticia_detail, name="noticia_detail"),
    path("privacidad/", views.privacidad, name="privacidad"),
    path("cookies/", views.cookies, name="cookies"),
    path("terminos/", views.terminos, name="terminos"),
    path("robots.txt", views.robots, name="robots"),
    path("sitemap.xml", views.sitemap, name="sitemap"),
    path("favicon.ico", views.favicon, name="favicon"),
]
