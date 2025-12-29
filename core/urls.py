from django.urls import path
from . import views

app_name = "core"

urlpatterns = [
    path("", views.home, name="home"),
    path("simulador/<int:proyecto_id>/", views.simulador, name="simulador"),
    path("simulador-basico/", views.simulador_basico, name="simulador_basico"),
    path(
        "simulaciones/guardar/",
        views.guardar_simulacion,
        name="guardar_simulacion",
    ),
    path(
        "simulaciones/borrar/<int:simulacion_id>/",
        views.borrar_simulacion,
        name="borrar_simulacion",
    ),
    path(
        "simulaciones/<int:simulacion_id>/convertir/",
        views.convertir_simulacion_a_proyecto,
        name="convertir_simulacion_a_proyecto",
    ),
    path("estudios/", views.lista_estudios, name="lista_estudio"),
    path(
        "estudios/<int:proyecto_id>/pdf/",
        views.generar_pdf_estudio,
        name="generar_pdf_estudio",
    ),
    path(
        "estudios/<int:proyecto_id>/aprobar/",
        views.aprobar_proyecto,
        name="aprobar_proyecto",
    ),
    path("proyectos/", views.lista_proyectos, name="lista_proyectos"),
    path(
        "proyectos/<int:proyecto_id>/gastos/",
        views.proyecto_gastos,
        name="proyecto_gastos",
    ),
    path(
        "proyectos/<int:proyecto_id>/inversores/",
        views.participacion_create,
        name="participacion_create",
    ),
    path("clientes/", views.clientes, name="clientes"),
    path("clientes/nuevo/", views.cliente_create, name="cliente_create"),
    path("clientes/<int:cliente_id>/editar/", views.cliente_edit, name="cliente_edit"),
    path("clientes/importar/", views.clientes_import, name="clientes_import"),
    path(
        "proyectos/cambiar-estado/<int:proyecto_id>/",
        views.cambiar_estado_proyecto,
        name="cambiar_estado_proyecto",
    ),
]
