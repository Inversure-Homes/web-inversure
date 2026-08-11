"""
Vistas del sorteo dentro del ERP (/app/sorteos/).

Separadas de las públicas a propósito: estas van tras login y con permisos, y
extienden `core/base.html`. Reutilizan `can_proyectos` en lugar de un permiso
nuevo — un sorteo es un proyecto, y con una rifa al año la granularidad extra
no aporta nada.
"""

import csv
from decimal import Decimal, InvalidOperation

from django import forms
from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.core.paginator import Paginator
from django.db.models import Q
from django.http import HttpResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.template.loader import render_to_string

from accounts.utils import resolve_permissions

from .calculadora import Config, escenarios, recomendar
from .correo import confirmar_pedido
from .economia import (
    consolidar_ingresos,
    crear_gastos_previstos,
    demanda,
    gastos_base,
    resumen_economico,
)
from .models import Pedido, Sorteo
from .notaria import cerrar_venta, datos_relacion
from .services import ErrorSorteo, registrar_venta_manual


def _puede(user):
    if user.is_superuser:
        return True
    return bool(resolve_permissions(user).get("can_proyectos"))


class VentaManualForm(forms.Form):
    """Alta de una venta presencial: efectivo, transferencia o talonario."""

    nombre = forms.CharField(max_length=120, label="Nombre y apellidos")
    email = forms.EmailField(label="Email")
    telefono = forms.CharField(max_length=30, required=False, label="Teléfono")
    cantidad = forms.IntegerField(min_value=1, initial=1, label="Nº de participaciones")
    numeros = forms.CharField(
        required=False,
        label="Números concretos (opcional)",
        help_text="Separados por comas. Si se deja vacío, se asignan al azar.",
    )
    medio_pago = forms.CharField(
        max_length=60,
        required=False,
        label="Medio de pago",
        help_text="Efectivo, transferencia, Bizum…",
    )

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        for campo in self.fields.values():
            campo.widget.attrs.setdefault("class", "form-control form-control-sm")

    def clean_numeros(self):
        crudo = (self.cleaned_data.get("numeros") or "").strip()
        if not crudo:
            return []
        try:
            return sorted({int(n) for n in crudo.replace(" ", "").split(",") if n})
        except ValueError as exc:
            raise forms.ValidationError("Usa números separados por comas.") from exc

    def clean(self):
        datos = super().clean()
        numeros = datos.get("numeros") or []
        if numeros:
            datos["cantidad"] = len(numeros)
        return datos


@login_required
def lista(request):
    if not _puede(request.user):
        return redirect("core:home")

    sorteos = Sorteo.objects.select_related("proyecto", "organizador").all()
    return render(
        request,
        "sorteo/erp_lista.html",
        {"sorteos": sorteos, "titulo": "Sorteos"},
    )


@login_required
def detalle(request, pk):
    if not _puede(request.user):
        return redirect("core:home")

    sorteo = get_object_or_404(Sorteo.objects.select_related("proyecto", "organizador"), pk=pk)

    pedidos = Pedido.objects.filter(sorteo=sorteo).exclude(estado=Pedido.Estado.CADUCADO).prefetch_related("papeletas")
    busqueda = (request.GET.get("q") or "").strip()
    if busqueda:
        pedidos = pedidos.filter(
            Q(nombre__icontains=busqueda)
            | Q(email__icontains=busqueda)
            | Q(codigo__icontains=busqueda)
            | Q(telefono__icontains=busqueda)
        )

    pagina = Paginator(pedidos, 50).get_page(request.GET.get("p"))

    return render(
        request,
        "sorteo/erp_detalle.html",
        {
            "sorteo": sorteo,
            "resumen": resumen_economico(sorteo),
            "demanda": demanda(sorteo),
            "gastos": sorteo.proyecto.gastos_proyecto.all().order_by("fecha"),
            "ingresos": sorteo.proyecto.ingresos.all().order_by("-fecha")[:12],
            "pagina": pagina,
            "busqueda": busqueda,
            "form": VentaManualForm(),
            "acta": getattr(sorteo, "acta", None),
            "titulo": sorteo.titulo,
        },
    )


@login_required
def venta_manual(request, pk):
    if not _puede(request.user):
        return redirect("core:home")

    sorteo = get_object_or_404(Sorteo, pk=pk)
    form = VentaManualForm(request.POST or None)

    if request.method == "POST" and form.is_valid():
        try:
            pedido = registrar_venta_manual(
                sorteo,
                form.cleaned_data["cantidad"],
                {
                    "nombre": form.cleaned_data["nombre"],
                    "email": form.cleaned_data["email"],
                    "telefono": form.cleaned_data["telefono"],
                    "medio_pago": form.cleaned_data["medio_pago"],
                },
                numeros=form.cleaned_data["numeros"],
                usuario=request.user,
            )
        except ErrorSorteo as exc:
            messages.error(request, str(exc))
        else:
            confirmar_pedido(pedido)
            messages.success(
                request,
                "Participación registrada: {} · números {}".format(pedido.codigo, pedido.numeros_texto),
            )
            return redirect("sorteo_erp:detalle", pk=sorteo.pk)
    elif request.method == "POST":
        for errores in form.errors.values():
            for e in errores:
                messages.error(request, e)

    return redirect("sorteo_erp:detalle", pk=sorteo.pk)


@login_required
def sincronizar(request, pk):
    """Vuelca al proyecto los ingresos por día y los gastos propios de la rifa."""
    if not _puede(request.user):
        return redirect("core:home")

    sorteo = get_object_or_404(Sorteo, pk=pk)
    dias = consolidar_ingresos(sorteo)
    gastos = crear_gastos_previstos(sorteo)
    messages.success(
        request,
        "Economía actualizada: {} día(s) de ventas consolidados y {} gasto(s) creados en el proyecto.".format(
            dias, gastos
        ),
    )
    return redirect("sorteo_erp:detalle", pk=sorteo.pk)


class DimensionadoForm(forms.Form):
    """
    Parámetros de la calculadora.

    Funciona en dos modos. Sobre un sorteo existente se precarga todo del
    modelo y del proyecto. En modo libre —para estudiar si compensa rifar un
    inmueble que aún no se ha comprado— se rellena a mano.
    """

    valor_premio = forms.DecimalField(
        label="Valor del inmueble (€)",
        min_value=0,
        help_text="Precio de compra previsto. Determina el ingreso a cuenta.",
    )
    gastos_base = forms.DecimalField(
        label="Gastos fijos totales (€)",
        min_value=0,
        help_text="Inmueble, ITP, notaría, gestoría, tasa DGOJ… Sin la tasa de "
        "juego ni el ingreso a cuenta, que se calculan solos.",
    )
    margen_objetivo = forms.DecimalField(label="Margen objetivo (€)", min_value=0, initial=15000)
    emitidas = forms.IntegerField(label="Participaciones a emitir", min_value=1, initial=5000)
    precio = forms.DecimalField(
        label="Precio por participación (€)",
        min_value=Decimal("0.01"),
        initial=10,
    )
    tasa_pct = forms.DecimalField(
        label="Tasa de juego (%)",
        min_value=0,
        initial=20,
        help_text="20 % general; 7 % si se declara benéfica o de utilidad pública.",
    )
    comision_pct = forms.DecimalField(label="Comisión de pago (%)", min_value=0, initial=Decimal("2.30"))
    precios = forms.CharField(
        label="Precios a comparar (€)",
        initial="5, 10, 15, 20, 25, 50",
        help_text="Separados por comas.",
    )

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        for campo in self.fields.values():
            campo.widget.attrs.setdefault("class", "form-control form-control-sm")

    def clean_precios(self):
        crudo = self.cleaned_data["precios"]
        try:
            valores = [Decimal(x.strip()) for x in crudo.split(",") if x.strip()]
        except (InvalidOperation, ValueError) as exc:
            raise forms.ValidationError("Usa importes separados por comas.") from exc
        if not valores:
            raise forms.ValidationError("Indica al menos un precio.")
        return valores


def _dimensionar(request, sorteo=None):
    """Motor común de la calculadora, con y sin sorteo creado."""
    if sorteo is not None:
        base = gastos_base(sorteo)
        cfg = Config.desde_sorteo(sorteo)
        inicial = {
            "valor_premio": cfg.valor_premio,
            "gastos_base": base,
            "emitidas": cfg.emitidas,
            "precio": cfg.precio,
            "tasa_pct": sorteo.tasa_juego_porcentaje,
            "comision_pct": sorteo.comision_pago_porcentaje,
            "margen_objetivo": 15000,
        }
    else:
        inicial = {"valor_premio": 18000, "gastos_base": 21160}

    form = DimensionadoForm(request.GET or None, initial=inicial)

    if form.is_valid():
        d = form.cleaned_data
        base = d["gastos_base"]
        cfg = Config(
            precio=d["precio"],
            emitidas=d["emitidas"],
            valor_premio=d["valor_premio"],
            minimo=sorteo.minimo_participaciones if sorteo else None,
            asume_ingreso_cuenta=(sorteo.organizador_asume_ingreso_cuenta if sorteo else True),
            tasa_pct=d["tasa_pct"],
            comision_pct=d["comision_pct"],
        )
        margen = d["margen_objetivo"]
        precios = d["precios"]
    elif sorteo is not None:
        margen, precios = Decimal("15000"), None
    else:
        # Sin sorteo y sin datos válidos: se usa el ejemplo por defecto para que
        # la página muestre algo con lo que empezar a jugar.
        cfg = Config(precio=10, emitidas=5000, valor_premio=18000)
        base, margen, precios = Decimal("21160"), Decimal("15000"), None

    opciones = recomendar(cfg, base, margen, precios)
    return render(
        request,
        "sorteo/erp_calculadora.html",
        {
            "sorteo": sorteo,
            "form": form,
            "cfg": cfg,
            "escenarios": escenarios(cfg, base),
            "opciones": opciones,
            "recomendada": opciones[0] if opciones else None,
            "margen": margen,
            "titulo": "Dimensionado" + (" · {}".format(sorteo.titulo) if sorteo else " de una rifa"),
        },
    )


@login_required
def calculadora_libre(request):
    """
    Estudio previo: ¿compensa rifar este inmueble?

    No requiere sorteo ni proyecto, precisamente para poder responderlo antes
    de comprar nada.
    """
    if not _puede(request.user):
        return redirect("core:home")
    return _dimensionar(request)


@login_required
def calculadora(request, pk):
    if not _puede(request.user):
        return redirect("core:home")
    sorteo = get_object_or_404(Sorteo.objects.select_related("proyecto"), pk=pk)
    return _dimensionar(request, sorteo)


@login_required
def cerrar_venta_vista(request, pk):
    """
    Congela la venta y sella el listado. Irreversible.

    Es el paso previo a llevarle el listado al notario: a partir de aquí la
    relación que se entrega queda fijada y su huella lo demuestra.
    """
    if not _puede(request.user):
        return redirect("core:home")

    sorteo = get_object_or_404(Sorteo, pk=pk)
    if request.method == "POST":
        if sorteo.cerrado_en:
            messages.warning(request, "La venta ya estaba cerrada.")
        else:
            cerrar_venta(sorteo)
            messages.success(
                request,
                "Venta cerrada. Listado sellado con huella {}…".format(sorteo.hash_listado[:16]),
            )
    return redirect("sorteo_erp:detalle", pk=sorteo.pk)


@login_required
def relacion(request, pk):
    """Relación de participaciones vendidas para entregar al notario."""
    if not _puede(request.user):
        return redirect("core:home")

    sorteo = get_object_or_404(Sorteo.objects.select_related("organizador"), pk=pk)
    contexto = datos_relacion(sorteo)
    html = render_to_string("sorteo/relacion_notarial.html", contexto, request)

    if request.GET.get("pdf"):
        from weasyprint import HTML  # defer import

        pdf = HTML(string=html, base_url=request.build_absolute_uri("/")).write_pdf()
        respuesta = HttpResponse(pdf, content_type="application/pdf")
        respuesta["Content-Disposition"] = 'attachment; filename="relacion-participaciones-{}.pdf"'.format(sorteo.slug)
        return respuesta

    return HttpResponse(html)


@login_required
def exportar(request, pk):
    if not _puede(request.user):
        return redirect("core:home")

    sorteo = get_object_or_404(Sorteo, pk=pk)
    respuesta = HttpResponse(content_type="text/csv; charset=utf-8")
    respuesta["Content-Disposition"] = 'attachment; filename="participantes.csv"'
    respuesta.write("﻿")

    escritor = csv.writer(respuesta)
    escritor.writerow(
        [
            "localizador",
            "nombre",
            "email",
            "telefono",
            "numeros",
            "importe",
            "estado",
            "origen",
            "medio_pago",
            "version_bases",
            "acepta_bases_en",
            "ip",
            "creado_en",
        ]
    )
    for p in Pedido.objects.filter(sorteo=sorteo).exclude(estado=Pedido.Estado.CADUCADO).prefetch_related("papeletas"):
        escritor.writerow(
            [
                p.codigo,
                p.nombre,
                p.email,
                p.telefono,
                p.numeros_texto,
                p.importe,
                p.estado,
                p.origen,
                p.medio_pago,
                p.version_bases,
                p.acepta_bases_en.isoformat(),
                p.ip or "",
                p.creado_en.isoformat(),
            ]
        )
    return respuesta
