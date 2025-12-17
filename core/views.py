from django.shortcuts import render

def simulador(request):
    resultado = {
        "inversion_total": 111111,
        "beneficio_bruto": 222222,
        "rentabilidad": 33.33,
        "rentabilidad_anual": 44.44,
    }

    return render(
        request,
        "core/simulador.html",
        {
            "resultado": resultado,
        }
    )
