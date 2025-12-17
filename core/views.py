from django.shortcuts import render

def simulador(request):
    resultado = None

    # 🔹 Entramos aquí si el formulario ha enviado datos
    if request.POST:

        def to_float(valor):
            try:
                return float(valor)
            except:
                return 0.0

        precio_compra = to_float(request.POST.get("precio_compra"))
        precio_venta = to_float(request.POST.get("precio_venta"))
        meses = to_float(request.POST.get("meses"))

        gestoria_compra = to_float(request.POST.get("gestoria_compra"))
        captacion = to_float(request.POST.get("captacion"))
        otros_adquisicion = to_float(request.POST.get("otros_adquisicion"))

        reforma = to_float(request.POST.get("reforma"))
        limpieza_inicial = to_float(request.POST.get("limpieza_inicial"))
        mobiliario = to_float(request.POST.get("mobiliario"))
        otros_iniciales = to_float(request.POST.get("otros_iniciales"))

        comunidad = to_float(request.POST.get("comunidad"))
        ibi = to_float(request.POST.get("ibi"))
        seguros = to_float(request.POST.get("seguros"))
        suministros = to_float(request.POST.get("suministros"))
        limpieza_periodica = to_float(request.POST.get("limpieza_periodica"))
        incidencias = to_float(request.POST.get("incidencias"))
        otros_recurrentes = to_float(request.POST.get("otros_recurrentes"))

        plusvalia = to_float(request.POST.get("plusvalia"))
        inmobiliaria = to_float(request.POST.get("inmobiliaria"))
        gestoria_venta = to_float(request.POST.get("gestoria_venta"))
        otros_venta = to_float(request.POST.get("otros_venta"))

        gastos_totales = (
            gestoria_compra + captacion + otros_adquisicion +
            reforma + limpieza_inicial + mobiliario + otros_iniciales +
            comunidad + ibi + seguros + suministros +
            limpieza_periodica + incidencias + otros_recurrentes +
            plusvalia + inmobiliaria + gestoria_venta + otros_venta
        )

        inversion_total = precio_compra + gastos_totales
        beneficio_bruto = precio_venta - inversion_total

        rentabilidad = 0
        rentabilidad_anual = 0

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

    return render(request, "core/simulador.html", {
        "resultado": resultado
    })
