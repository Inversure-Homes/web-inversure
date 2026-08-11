"""
Estudios de rifa: el banco de pruebas.

Aquí se guardan escenarios sobre inmuebles que a lo mejor ni se han comprado,
se comparan entre sí, y solo el que convence se convierte en `Sorteo` real.
Mismo patrón que el `Estudio` del ERP para el resto de operaciones.
"""

from django import forms
from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.shortcuts import get_object_or_404, redirect, render
from django.views.decorators.http import require_POST

from core.models import Proyecto

from .comparador import comparar, desde_proyecto
from .impuestos import opciones_reducidas
from .models import EstudioRifa, Organizador, Sorteo
from .views_erp import _puede


class EstudioForm(forms.ModelForm):
    class Meta:
        model = EstudioRifa
        fields = [
            "nombre",
            "proyecto",
            "precio_compra",
            "valor_referencia",
            "comunidad",
            "operacion_compra",
            "supuesto_reducido",
            "otros_gastos",
            "precio_participacion",
            "participaciones",
            "minimo_participaciones",
            "tasa_juego_porcentaje",
            "comision_pago_porcentaje",
            "precio_venta_estimado",
            "meses_venta",
            "meses_rifa",
            "notas",
        ]
        widgets = {"notas": forms.Textarea(attrs={"rows": 3})}
        labels = {
            "precio_compra": "Precio de compra (€)",
            "valor_referencia": "Valor de referencia de Catastro (€)",
            "comunidad": "Comunidad autónoma",
            "operacion_compra": "Impuesto de la compra",
            "supuesto_reducido": "Tipo reducido",
            "otros_gastos": "Otros gastos de compra (€)",
            "precio_participacion": "Precio por participación (€)",
            "participaciones": "Participaciones a emitir",
            "minimo_participaciones": "Mínimo para celebrar el sorteo",
            "tasa_juego_porcentaje": "Tasa de juego (%)",
            "comision_pago_porcentaje": "Comisión de la pasarela (%)",
            "precio_venta_estimado": "Precio de venta estimado (€)",
            "meses_venta": "Meses hasta vender",
            "meses_rifa": "Meses hasta sortear",
        }
        help_texts = {
            "tasa_juego_porcentaje": "20 % general; 7 % si se declara benéfica o de utilidad pública.",
            "minimo_participaciones": "Por debajo de esta cifra el sorteo se "
            "puede cancelar con reintegro. Apartado 9 de las bases.",
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["proyecto"].required = False
        # Texto libre no: el tipo reducido se elige de los que existen.
        self.fields["supuesto_reducido"] = forms.ChoiceField(
            choices=opciones_reducidas(),
            required=False,
            label="Tipo reducido",
            help_text="Solo se aplica si lo eliges a sabiendas: los requisitos no los puede comprobar el sistema.",
        )
        self.fields["proyecto"].empty_label = "Sin proyecto (inmueble hipotético)"
        for campo in self.fields.values():
            # `form-select` da el ancho completo a los desplegables, que con
            # `form-control` se quedaban cortando el texto.
            css = "form-select" if hasattr(campo, "choices") else "form-control"
            campo.widget.attrs.setdefault("class", "{} {}-sm w-100".format(css, css))


@login_required
def lista(request):
    """Los estudios viven dentro de la sección de sorteos, no aparte."""
    return redirect("sorteo_erp:lista")


@login_required
def editar(request, pk=None):
    if not _puede(request.user):
        return redirect("core:home")

    estudio = get_object_or_404(EstudioRifa, pk=pk) if pk else None
    inicial = {}

    # Precarga desde un proyecto existente: ?proyecto=<id>
    proyecto_id = request.GET.get("proyecto")
    if estudio is None and proyecto_id:
        proyecto = Proyecto.objects.filter(pk=proyecto_id).first()
        if proyecto:
            inicial = desde_proyecto(proyecto)
            inicial["proyecto"] = proyecto.pk
            inicial["nombre"] = "Rifa de {}".format(proyecto.nombre)

    form = EstudioForm(request.POST or None, instance=estudio, initial=inicial)
    if request.method == "POST" and form.is_valid():
        nuevo = form.save(commit=False)
        if estudio is None:
            nuevo.creado_por = request.user
        nuevo.save()
        messages.success(request, "Estudio guardado.")
        return redirect("sorteo_erp:estudio", pk=nuevo.pk)

    return render(
        request,
        "sorteo/erp_estudio_form.html",
        {
            "form": form,
            "estudio": estudio,
            "titulo": estudio.nombre if estudio else "Nuevo estudio de rifa",
        },
    )


@login_required
def detalle(request, pk):
    if not _puede(request.user):
        return redirect("core:home")

    estudio = get_object_or_404(EstudioRifa.objects.select_related("proyecto", "sorteo"), pk=pk)
    return render(
        request,
        "sorteo/erp_estudio.html",
        {
            "estudio": estudio,
            "analisis": comparar(estudio.como_datos()),
            "titulo": estudio.nombre,
        },
    )


@login_required
def duplicar(request, pk):
    """Copiar un estudio para probar una variante sin perder el original."""
    if not _puede(request.user):
        return redirect("core:home")

    original = get_object_or_404(EstudioRifa, pk=pk)
    copia = EstudioRifa.objects.get(pk=pk)
    copia.pk = None
    copia.sorteo = None
    copia.nombre = "{} (copia)".format(original.nombre)[:160]
    copia.creado_por = request.user
    copia.save()
    messages.success(request, "Estudio duplicado: cambia lo que quieras probar.")
    return redirect("sorteo_erp:estudio_editar", pk=copia.pk)


@login_required
def archivar(request, pk):
    """
    Descartar un estudio sin borrarlo.

    Saber qué se probó y por qué no salió vale para el siguiente, así que no
    hay borrado: se archiva y se puede recuperar.
    """
    if not _puede(request.user):
        return redirect("core:home")

    estudio = get_object_or_404(EstudioRifa, pk=pk)
    estudio.archivado = not estudio.archivado
    estudio.save(update_fields=["archivado"])
    messages.success(
        request,
        "Estudio archivado." if estudio.archivado else "Estudio recuperado.",
    )
    return redirect("sorteo_erp:lista")


@login_required
@require_POST
def borrar(request, pk):
    """
    Borrado definitivo de un estudio.

    Va por POST y no por enlace: un GET que borra lo dispara cualquier
    precarga del navegador o un rastreador.

    Si el estudio ya se convirtió en sorteo se borra igual —es solo el papel de
    trabajo— pero el sorteo se queda, con su economía y sus participaciones.
    """
    if not _puede(request.user):
        return redirect("core:home")

    estudio = get_object_or_404(EstudioRifa, pk=pk)
    nombre = estudio.nombre
    estudio.delete()
    messages.success(request, "Estudio «{}» borrado.".format(nombre))
    return redirect("sorteo_erp:lista")


@login_required
def convertir(request, pk):
    """
    Convierte el estudio en un sorteo real, en borrador.

    Exige un proyecto: el sorteo cuelga de él y ahí vive su economía. Se crea
    en borrador y sin papeletas, para que nada salga a la web hasta que alguien
    complete las bases y la autorización.
    """
    if not _puede(request.user):
        return redirect("core:home")

    estudio = get_object_or_404(EstudioRifa, pk=pk)

    if estudio.sorteo:
        messages.warning(request, "Este estudio ya se convirtió en sorteo.")
        return redirect("sorteo_erp:detalle", pk=estudio.sorteo.pk)

    if not estudio.proyecto:
        messages.error(
            request,
            "Asocia el estudio a un proyecto antes de convertirlo: el sorteo cuelga de él y es donde vive su economía.",
        )
        return redirect("sorteo_erp:estudio", pk=estudio.pk)

    if Sorteo.objects.filter(proyecto=estudio.proyecto).exists():
        messages.error(request, "Ese proyecto ya tiene un sorteo.")
        return redirect("sorteo_erp:estudio", pk=estudio.pk)

    organizador = Organizador.objects.first()
    if organizador is None:
        messages.error(request, "Crea antes un organizador en el administrador.")
        return redirect("sorteo_erp:estudio", pk=estudio.pk)

    import datetime

    from django.utils.text import slugify

    hoy = datetime.date.today()
    sorteo = Sorteo.objects.create(
        proyecto=estudio.proyecto,
        organizador=organizador,
        slug=slugify(estudio.nombre)[:50] or "sorteo-{}".format(estudio.pk),
        titulo=estudio.nombre,
        premio_descripcion=estudio.proyecto.nombre,
        precio_participacion=estudio.precio_participacion,
        total_participaciones=estudio.participaciones,
        minimo_participaciones=estudio.minimo_participaciones,
        tasa_juego_porcentaje=estudio.tasa_juego_porcentaje,
        comision_pago_porcentaje=estudio.comision_pago_porcentaje,
        comunidad=estudio.comunidad,
        operacion_compra=estudio.operacion_compra,
        supuesto_reducido=estudio.supuesto_reducido,
        inmueble_valor=estudio.precio_compra,
        fecha_inicio_venta=hoy,
        fecha_sorteo=hoy + datetime.timedelta(days=180),
        estado=Sorteo.Estado.BORRADOR,
    )
    estudio.sorteo = sorteo
    estudio.save(update_fields=["sorteo"])

    messages.success(
        request,
        "Sorteo creado en borrador. Repasa fechas, notaría y bases antes de generar las papeletas y abrir la venta.",
    )
    return redirect("sorteo_erp:detalle", pk=sorteo.pk)
