from django.urls import path
from . import views

app_name = "core"

urlpatterns = [
    path("", views.home, name="home"),
    path("simulador/", views.simulador_nuevo, name="simulador_nuevo"),
    path("simulador/<int:proyecto_id>/", views.simulador, name="simulador"),
    path(
        "simulaciones/convertir/",
        views.convertir_simulacion_a_proyecto,
        name="convertir_simulacion_a_proyecto",
    ),
    path("estudios/", views.lista_estudios, name="lista_estudio"),
    path(
        "estudios/<int:proyecto_id>/borrar/",
        views.borrar_estudio,
        name="borrar_estudio",
    ),
    path(
        "catastro/obtener/",
        views.catastro_obtener,
        name="catastro_obtener",
    ),
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
        "proyectos/<int:proyecto_id>/",
        views.proyecto_detalle,
        name="proyecto_detalle",
    ),
    path(
        "proyectos/<int:proyecto_id>/presupuesto/",
        views.proyecto_presupuesto,
        name="proyecto_presupuesto",
    ),
    path(
        "proyectos/<int:proyecto_id>/memoria-economica/",
        views.memoria_economica,
        name="memoria_economica",
    ),
    path(
        "proyectos/<int:proyecto_id>/documentos/",
        views.proyecto_documentos,
        name="proyecto_documentos",
    ),
    path(
        "proyectos/<int:proyecto_id>/borrar/",
        views.borrar_proyecto,
        name="borrar_proyecto",
    ),
    path(
        "proyectos/<int:proyecto_id>/gastos/",
        views.proyecto_gastos,
        name="proyecto_gastos",
    ),
    path(
        "proyectos/<int:proyecto_id>/gastos/nuevo/",
        views.proyecto_gasto_nuevo,
        name="proyecto_gasto_nuevo",
    ),
    path(
        "proyectos/<int:proyecto_id>/inversores/",
        views.participacion_create,
        name="participacion_create",
    ),
    path(
        "proyectos/<int:proyecto_id>/inversores/lista/",
        views.proyecto_inversores,
        name="proyecto_inversores",
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
