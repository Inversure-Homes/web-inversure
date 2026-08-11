import json

from django import forms
from django.http import Http404, JsonResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.views.decorators.http import require_POST

from django.utils import timezone

from .correo import confirmar_alta, confirmar_pedido
from .models import Interesado, Papeleta, Pedido, Sorteo
from .services import (
    ErrorSorteo,
    confirmar_pago,
    liberar_caducadas,
    reservar_cantidad,
    reservar_numeros,
)


def _sorteo_activo():
    """
    El sorteo que se muestra en /sorteo/.

    Solo puede haber uno a la vez: la normativa obliga a que las rifas
    ocasionales tengan periodicidad mínima anual. En borrador la página existe
    igualmente, pero muestra la lista de espera en lugar de la compra.
    """
    for estado in (Sorteo.Estado.EN_VENTA, Sorteo.Estado.SORTEADO, None):
        qs = Sorteo.objects.select_related("organizador")
        sorteo = (qs.filter(estado=estado) if estado else qs).first()
        if sorteo:
            return sorteo
    raise Http404("No hay ningún sorteo publicado.")


def _ip(request):
    reenviada = request.META.get("HTTP_X_FORWARDED_FOR", "")
    if reenviada:
        return reenviada.split(",")[0].strip()
    return request.META.get("REMOTE_ADDR")


def _ocupadas(sorteo):
    """
    Solo los números NO libres.

    Con 5.000 participaciones, mandar la rejilla entera al navegador en cada
    sondeo serían cientos de kB por usuario. Se manda la excepción, no la
    norma: el cliente asume que el resto está libre.
    """
    return [
        {"n": numero, "e": estado}
        for numero, estado in sorteo.papeletas.exclude(
            estado=Papeleta.Estado.LIBRE
        )
        .order_by("numero")
        .values_list("numero", "estado")
    ]


class AltaForm(forms.Form):
    """
    Lista de espera. No es una compra: no hay precio comprometido, ni números
    asignados, ni pago.

    Se pide lo mínimo para poder avisar, más dos datos que sirven para decidir
    el dimensionado. Nada de DNI ni dirección: no hacen falta para un email.
    """

    nombre = forms.CharField(max_length=120, label="Nombre")
    email = forms.EmailField(label="Email")
    telefono = forms.CharField(max_length=30, required=False, label="Teléfono (opcional)")
    provincia = forms.CharField(max_length=60, required=False, label="Provincia (opcional)")
    participaciones_estimadas = forms.IntegerField(
        min_value=1, max_value=500, initial=1,
        label="¿Cuántas participaciones te interesarían?",
    )
    precio_maximo = forms.ChoiceField(
        choices=Interesado.Precio.choices,
        label="¿Hasta qué precio por participación?",
    )
    mayor_edad = forms.BooleanField(label="Declaro ser mayor de 18 años")
    acepta_aviso = forms.BooleanField(
        label="Quiero recibir un aviso por email cuando se abra la venta"
    )

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        for nombre, campo in self.fields.items():
            if isinstance(campo.widget, forms.CheckboxInput):
                continue
            css = "sorteo-select" if nombre == "precio_maximo" else ""
            campo.widget.attrs.setdefault("class", css)


def portada(request):
    sorteo = _sorteo_activo()

    # En borrador todavía no hay autorización, así que no se puede vender:
    # la página recoge interés, no pedidos.
    if sorteo.estado == Sorteo.Estado.BORRADOR:
        return _alta(request, sorteo)

    liberar_caducadas(sorteo)
    acta = getattr(sorteo, "acta", None)
    return render(
        request,
        "sorteo/portada.html",
        {
            "sorteo": sorteo,
            "acta": acta,
            "ocupadas_json": json.dumps(_ocupadas(sorteo)),
        },
    )


def _alta(request, sorteo):
    form = AltaForm(request.POST or None)
    guardado = False

    if request.method == "POST" and form.is_valid():
        datos = form.cleaned_data
        interesado, _ = Interesado.objects.update_or_create(
            sorteo=sorteo,
            email=datos["email"],
            defaults={
                "nombre": datos["nombre"],
                "telefono": datos["telefono"],
                "provincia": datos["provincia"],
                "participaciones_estimadas": datos["participaciones_estimadas"],
                "precio_maximo": datos["precio_maximo"],
                "mayor_edad": datos["mayor_edad"],
                "acepta_aviso": datos["acepta_aviso"],
                "ip": _ip(request),
                "baja_en": None,
            },
        )
        confirmar_alta(interesado)
        guardado = True
        form = AltaForm()

    return render(
        request,
        "sorteo/alta.html",
        {"sorteo": sorteo, "form": form, "guardado": guardado},
    )


def baja(request, token):
    """Revocación del consentimiento. Sin login: el enlace va en cada email."""
    interesado = get_object_or_404(Interesado, token_baja=token)
    if interesado.activo:
        interesado.baja_en = timezone.now()
        interesado.acepta_aviso = False
        interesado.save(update_fields=["baja_en", "acepta_aviso"])
    return render(request, "sorteo/baja.html", {"interesado": interesado})


def bases(request):
    """
    Las bases deben seguir accesibles durante toda la venta y hasta que caduque
    el plazo de reclamación del premio: esta página no se retira al sortear.
    """
    sorteo = _sorteo_activo()
    return render(request, "sorteo/bases.html", {"sorteo": sorteo})


def estado(request):
    sorteo = _sorteo_activo()
    liberar_caducadas(sorteo)
    return JsonResponse(
        {
            "ocupadas": _ocupadas(sorteo),
            "vendidas": sorteo.vendidas,
            "disponibles": sorteo.disponibles,
            "precio": str(sorteo.precio_participacion),
        }
    )


@require_POST
def reservar(request):
    sorteo = _sorteo_activo()
    if not sorteo.abierto:
        return JsonResponse({"error": "La venta está cerrada."}, status=409)

    try:
        cuerpo = json.loads(request.body.decode("utf-8"))
    except (ValueError, UnicodeDecodeError):
        return JsonResponse({"error": "Petición inválida."}, status=400)

    nombre = str(cuerpo.get("nombre") or "").strip()[:120]
    email = str(cuerpo.get("email") or "").strip()[:254]
    telefono = str(cuerpo.get("telefono") or "").strip()[:30]

    if not nombre or "@" not in email or "." not in email.split("@")[-1]:
        return JsonResponse({"error": "Revisa tu nombre y tu email."}, status=400)

    # La normativa prohíbe la participación de menores y exige que las bases
    # estén aceptadas. Se comprueba aquí, no solo en el formulario, y la prueba
    # se guarda con el pedido.
    if cuerpo.get("acepta_bases") is not True or cuerpo.get("mayor_edad") is not True:
        return JsonResponse(
            {
                "error": "Debes declarar que eres mayor de edad y aceptar las "
                "bases del sorteo."
            },
            status=400,
        )

    datos = {"nombre": nombre, "email": email, "telefono": telefono, "ip": _ip(request)}

    # El importe lo calcula siempre el servidor a partir de la cantidad: el
    # cliente no decide cuánto se cobra.
    numeros = cuerpo.get("numeros") or []
    if numeros:
        try:
            numeros = sorted(
                {
                    int(n)
                    for n in numeros
                    if 1 <= int(n) <= sorteo.total_participaciones
                }
            )
        except (TypeError, ValueError):
            return JsonResponse({"error": "Números inválidos."}, status=400)
        cantidad = len(numeros)
    else:
        try:
            cantidad = int(cuerpo.get("cantidad") or 0)
        except (TypeError, ValueError):
            cantidad = 0

    if cantidad < 1:
        return JsonResponse(
            {"error": "Indica cuántas participaciones quieres."}, status=400
        )
    if cantidad > sorteo.max_por_pedido:
        return JsonResponse(
            {
                "error": "Máximo {} participaciones por pedido.".format(
                    sorteo.max_por_pedido
                )
            },
            status=400,
        )

    try:
        if numeros:
            pedido = reservar_numeros(sorteo, numeros, datos)
        else:
            pedido = reservar_cantidad(sorteo, cantidad, datos)
    except ErrorSorteo as exc:
        return JsonResponse(
            {"error": str(exc), "ocupadas": _ocupadas(sorteo)}, status=409
        )

    # TODO(paso 3): crear aquí la sesión de Stripe Checkout y devolver su URL.
    return JsonResponse({"url": "/sorteo/pago/{}/".format(pedido.id)})


def pago_pendiente(request, pedido_id):
    """
    Provisional hasta integrar Stripe (paso 3). Permite recorrer el flujo
    completo y probar la reserva, el consentimiento y el justificante.
    """
    pedido = get_object_or_404(Pedido, pk=pedido_id)
    if pedido.estado == Pedido.Estado.PAGADO:
        return redirect("sorteo:pedido", pedido_id=pedido.id)

    if request.method == "POST":
        confirmado = confirmar_pago(pedido.id)
        if confirmado:
            confirmar_pedido(confirmado)
        return redirect("sorteo:pedido", pedido_id=pedido.id)

    return render(request, "sorteo/pago_pendiente.html", {"pedido": pedido})


def pedido(request, pedido_id):
    pedido = get_object_or_404(
        Pedido.objects.select_related("sorteo", "sorteo__organizador"), pk=pedido_id
    )
    return render(request, "sorteo/pedido.html", {"pedido": pedido})
