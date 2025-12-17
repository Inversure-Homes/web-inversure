from django.urls import path
from .views import simulador

urlpatterns = [
    path("", simulador, name="home"),
]
