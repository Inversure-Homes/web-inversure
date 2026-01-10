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
]