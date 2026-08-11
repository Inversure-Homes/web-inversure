from django.urls import path

from . import views_erp, views_estudios

app_name = "sorteo_erp"

urlpatterns = [
    path("", views_erp.lista, name="lista"),
    path("calculadora/", views_erp.calculadora_libre, name="calculadora_libre"),
    path("estudios/", views_estudios.lista, name="estudios"),
    path("estudios/nuevo/", views_estudios.editar, name="estudio_nuevo"),
    path("estudios/<int:pk>/", views_estudios.detalle, name="estudio"),
    path("estudios/<int:pk>/editar/", views_estudios.editar, name="estudio_editar"),
    path("estudios/<int:pk>/duplicar/", views_estudios.duplicar, name="estudio_duplicar"),
    path("estudios/<int:pk>/convertir/", views_estudios.convertir, name="estudio_convertir"),
    path("<int:pk>/", views_erp.detalle, name="detalle"),
    path("<int:pk>/venta/", views_erp.venta_manual, name="venta_manual"),
    path("<int:pk>/calculadora/", views_erp.calculadora, name="calculadora"),
    path("<int:pk>/sincronizar/", views_erp.sincronizar, name="sincronizar"),
    path("<int:pk>/cerrar/", views_erp.cerrar_venta_vista, name="cerrar_venta"),
    path("<int:pk>/relacion/", views_erp.relacion, name="relacion"),
    path("<int:pk>/csv/", views_erp.exportar, name="exportar"),
]
