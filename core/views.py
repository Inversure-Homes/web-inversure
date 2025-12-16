
from django.shortcuts import render
from .models import Operacion


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


# =====================
# SIMULADOR
# =====================
def simulador(request):
    result = None

    if request.method == "POST":

        # DATOS PRINCIPALES
        precio_compra = to_float(request.POST.get("precio_compra"))
        precio_venta = to_float(request.POST.get("precio_venta"))
        meses = to_float(request.POST.get("meses"))

        # GASTOS AUTOMÁTICOS
        itp = precio_compra * 0.02
        notaria = precio_compra * 0.002
        registro = precio_compra * 0.002

        # ADQUISICIÓN
        gestoria_compra = to_float(request.POST.get("gestoria_compra"))
        comisiones_captacion = to_float(request.POST.get("comisiones_captacion"))
        otros_adquisicion = to_float(request.POST.get("otros_adquisicion"))

        # INVERSIÓN INICIAL
        reforma = to_float(request.POST.get("reforma"))
        limpieza_inicial = to_float(request.POST.get("limpieza_inicial"))
        mobiliario = to_float(request.POST.get("mobiliario"))
        otros_puesta_marcha = to_float(request.POST.get("otros_puesta_marcha"))

        # RECURRENTES
        comunidad = to_float(request.POST.get("comunidad"))
        ibi = to_float(request.POST.get("ibi"))
        seguros = to_float(request.POST.get("seguros"))
        suministros = to_float(request.POST.get("suministros"))
        limpieza = to_float(request.POST.get("limpieza"))
        ocupas = to_float(request.POST.get("ocupas"))
        otros_recurrentes = to_float(request.POST.get("otros_recurrentes"))

        gastos_recurrentes = (
            comunidad + ibi + seguros + suministros +
            limpieza + ocupas + otros_recurrentes
        )

        # VENTA
        plusvalia = to_float(request.POST.get("plusvalia"))
        inmobiliaria = to_float(request.POST.get("inmobiliaria"))
        gestoria_venta = to_float(request.POST.get("gestoria_venta"))
        otros_gastos_venta = to_float(request.POST.get("otros_gastos_venta"))

        gastos_venta = (
            plusvalia +
            inmobiliaria +
            gestoria_venta +
            otros_gastos_venta
        )

        beneficio_bruto = precio_venta - precio_compra - gastos_venta

        result = {
            "beneficio_bruto": beneficio_bruto,
            "itp": itp,
            "notaria": notaria,
            "registro": registro,
        }

    return render(request, "core/simulador.html", result or {})


# =====================
# OPERACIONES
# =====================
def operaciones(request):
    operaciones = Operacion.objects.all().order_by("-id")
    return render(request, "core/operaciones.html", {
        "operaciones": operaciones
    })
