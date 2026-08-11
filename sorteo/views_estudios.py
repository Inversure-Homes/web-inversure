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

from core.models import Proyecto

from .comparador import comparar, desde_proyecto
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

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["proyecto"].required = False
        self.fields["proyecto"].empty_label = "Sin proyecto (inmueble hipotético)"
        for campo in self.fields.values():
            css = "form-select" if hasattr(campo, "choices") else "form-control"
            campo.widget.attrs.setdefault("class", css + " form-control-sm")


@login_required
def lista(request):
    if not _puede(request.user):
        return redirect("core:home")

    estudios = []
    for estudio in EstudioRifa.objects.select_related("proyecto", "sorteo"):
        analisis = comparar(estudio.como_datos())
        estudios.append({"estudio": estudio, "analisis": analisis})

    return render(
        request,
        "sorteo/erp_estudios.html",
        {"estudios": estudios, "titulo": "Estudios de rifa"},
    )


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
