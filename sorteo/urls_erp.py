from django.urls import path

from . import views_erp

app_name = "sorteo_erp"

urlpatterns = [
    path("", views_erp.lista, name="lista"),
    path("calculadora/", views_erp.calculadora_libre, name="calculadora_libre"),
    path("<int:pk>/", views_erp.detalle, name="detalle"),
    path("<int:pk>/venta/", views_erp.venta_manual, name="venta_manual"),
    path("<int:pk>/calculadora/", views_erp.calculadora, name="calculadora"),
    path("<int:pk>/sincronizar/", views_erp.sincronizar, name="sincronizar"),
    path("<int:pk>/cerrar/", views_erp.cerrar_venta_vista, name="cerrar_venta"),
    path("<int:pk>/relacion/", views_erp.relacion, name="relacion"),
    path("<int:pk>/csv/", views_erp.exportar, name="exportar"),
]
