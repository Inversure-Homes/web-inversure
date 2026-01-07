from django.urls import path
from . import views

app_name = "core"

urlpatterns = [
    path("", views.home, name="home"),
    path("simulador/", views.simulador, name="simulador"),
    path("guardar-estudio/", views.guardar_estudio, name="guardar_estudio"),
    path("convertir-a-proyecto/<int:estudio_id>/", views.convertir_a_proyecto, name="convertir_a_proyecto"),
    path(
        "estudios/pdf/<int:estudio_id>/",
        views.pdf_estudio_preview,
        name="pdf_estudio_rentabilidad"
    ),

    # Listados
    path("estudios/", views.lista_estudio, name="lista_estudio"),
    path("estudios/borrar/<int:estudio_id>/", views.borrar_estudio, name="borrar_estudio"),
    path("proyectos/", views.lista_proyectos, name="lista_proyectos"),
]