from django.urls import path
from . import views

app_name = "core"

urlpatterns = [
    # Home
    path("", views.home, name="home"),

    # Simulador / Estudios
    path("simulador/", views.simulador, name="simulador"),
    path("guardar-estudio/", views.guardar_estudio, name="guardar_estudio"),

    # PDF estudio
    path("estudios/pdf/<int:estudio_id>/", views.pdf_estudio_preview, name="pdf_estudio_preview"),
    path("proyectos/<int:proyecto_id>/memoria/pdf/", views.pdf_memoria_economica, name="pdf_memoria_economica"),

    # Estudios
    path("estudios/nuevo/", views.nuevo_estudio, name="nuevo_estudio"),
    path("estudios/", views.lista_estudio, name="lista_estudio"),
    path("estudios/borrar/<int:estudio_id>/", views.borrar_estudio, name="borrar_estudio"),

    # Conversión a proyecto
    path("convertir-a-proyecto/<int:estudio_id>/", views.convertir_a_proyecto, name="convertir_a_proyecto"),

    # Proyectos
    path("proyectos/", views.lista_proyectos, name="lista_proyectos"),
    # Detalle de proyecto (si existe en views)
    path("proyectos/<int:proyecto_id>/", views.proyecto, name="proyecto"),

    # Autosave / guardado de proyecto (POST)
    path("proyectos/<int:proyecto_id>/guardar/", views.guardar_proyecto, name="guardar_proyecto"),

    # Memoria económica (gastos / ingresos)
    path("proyectos/<int:proyecto_id>/gastos/", views.proyecto_gastos, name="proyecto_gastos"),
    path("proyectos/<int:proyecto_id>/gastos/<int:gasto_id>/", views.proyecto_gasto_detalle, name="proyecto_gasto_detalle"),
    path("proyectos/<int:proyecto_id>/ingresos/", views.proyecto_ingresos, name="proyecto_ingresos"),
    path("proyectos/<int:proyecto_id>/ingresos/<int:ingreso_id>/", views.proyecto_ingreso_detalle, name="proyecto_ingreso_detalle"),
    path("proyectos/<int:proyecto_id>/checklist/", views.proyecto_checklist, name="proyecto_checklist"),
    path("proyectos/<int:proyecto_id>/checklist/<int:item_id>/", views.proyecto_checklist_detalle, name="proyecto_checklist_detalle"),
    path("proyectos/<int:proyecto_id>/participaciones/", views.proyecto_participaciones, name="proyecto_participaciones"),
    path("proyectos/<int:proyecto_id>/participaciones/<int:participacion_id>/", views.proyecto_participacion_detalle, name="proyecto_participacion_detalle"),

    # Clientes
    path("clientes/", views.clientes, name="clientes"),
    path("clientes/nuevo/", views.clientes_form, name="clientes_form"),
    path("clientes/editar/<int:cliente_id>/", views.cliente_edit, name="cliente_edit"),
    path("clientes/importar/", views.clientes_import, name="clientes_import"),
]
