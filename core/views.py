from django.shortcuts import render

def simulador(request):
    resultado = None

    def f(v):
        try:
            return float(v)
        except:
            return 0.0

    if request.method == "POST":
        precio_compra = f(request.POST.get("precio_compra"))
        precio_venta = f(request.POST.get("precio_venta"))
        meses = f(request.POST.get("meses"))

        gastos = (
            f(request.POST.get("gestoria_compra")) +
            f(request.POST.get("captacion")) +
            f(request.POST.get("otros_adquisicion")) +
            f(request.POST.get("reforma")) +
            f(request.POST.get("limpieza_inicial")) +
            f(request.POST.get("mobiliario")) +
            f(request.POST.get("otros_iniciales")) +
            f(request.POST.get("comunidad")) +
            f(request.POST.get("ibi")) +
            f(request.POST.get("seguros")) +
            f(request.POST.get("suministros")) +
            f(request.POST.get("limpieza_periodica")) +
            f(request.POST.get("incidencias")) +
            f(request.POST.get("otros_recurrentes")) +
            f(request.POST.get("plusvalia")) +
            f(request.POST.get("inmobiliaria")) +
            f(request.POST.get("gestoria_venta")) +
            f(request.POST.get("otros_venta"))
        )

        inversion_total = precio_compra + gastos
        beneficio_bruto = precio_venta - inversion_total

        rentabilidad = 0.0
        rentabilidad_anual = 0.0

        if inversion_total > 0:
            rentabilidad = (beneficio_bruto / inversion_total) * 100
            if meses > 0:
                rentabilidad_anual = rentabilidad * (12 / meses)

        resultado = {
            "inversion_total": round(inversion_total, 2),
            "beneficio_bruto": round(beneficio_bruto, 2),
            "rentabilidad": round(rentabilidad, 2),
            "rentabilidad_anual": round(rentabilidad_anual, 2),
        }

    # Debug visible en la página (para ver qué llega)
    debug_info = {
        "method": request.method,
        "post_keys": list(request.POST.keys()),
        "post_dict": {k: request.POST.get(k) for k in request.POST.keys()},
        "resultado": resultado,
    }

    return render(request, "core/simulador.html", {
        "resultado": resultado,
        "debug": debug_info,
    })
