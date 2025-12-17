
from django.shortcuts import render
 from .models import Operacion
from django.http import HttpResponse

# =====================
# UTILIDADES
# =====================
def to_float(valor):
    try:
        if valor is None or valor == "":
            return 0.0
        return float(str(valor).replace(",", "."))
    except (TypeError, ValueError):
        return 0.0

BASE_CONTEXT = {
    "beneficio_bruto": 0,
    "itp": 0,
    "notaria": 0,
    "registro": 0,
}
# =====================
# SIMULADOR
# =====================
def simulador(request):
    return render(request, "core/simulador.html")
# =====================
# OPERACIONES
# =====================
def operaciones(request):
    operaciones = Operacion.objects.all().order_by("-id")
    return render(request, "core/operaciones.html", {
        "operaciones": operaciones
    })

