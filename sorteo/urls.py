from django.urls import path

from . import views

app_name = "sorteo"

urlpatterns = [
    path("", views.portada, name="portada"),
    path("bases/", views.bases, name="bases"),
    path("baja/<uuid:token>/", views.baja, name="baja"),
    path("estado/", views.estado, name="estado"),
    path("reservar/", views.reservar, name="reservar"),
    path("pago/<uuid:pedido_id>/", views.pago_pendiente, name="pago"),
    path("pedido/<uuid:pedido_id>/", views.pedido, name="pedido"),
]
