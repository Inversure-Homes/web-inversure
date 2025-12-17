from django.contrib import admin
from django.urls import path
from core.views import simulador, operaciones

urlpatterns = [
    path("admin/", admin.site.urls),
    path("", simulador, name="home"),
    path("simulador/", simulador, name="simulador"),
    path("operaciones/", operaciones, name="operaciones"),
]
