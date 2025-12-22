from django.urls import path
from . import views

urlpatterns = [
    path("", views.home, name="home"),
    path("simulador/", views.simulador, name="simulador"),
    path("proyecto/borrar/<str:nombre>/", views.borrar_proyecto, name="borrar_proyecto"),
    path("proyectos/", views.lista_proyectos, name="lista_proyectos"),
    path("clientes/", views.clientes, name="clientes"),
    path("clientes/nuevo/", views.cliente_create, name="cliente_create"),
    path("clientes/importar/", views.clientes_import, name="clientes_import"),
]
