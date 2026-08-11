import csv

from django import forms
from django.contrib import admin, messages
from django.http import HttpResponse
from django.shortcuts import redirect, render
from django.urls import path, reverse
from django.utils.html import format_html

from .models import (
    ActaSorteo,
    Interesado,
    Organizador,
    Papeleta,
    Pedido,
    Sorteo,
)
from .correo import avisar_ganador
from .services import ErrorSorteo, registrar_acta


@admin.register(Organizador)
class OrganizadorAdmin(admin.ModelAdmin):
    list_display = ("nombre", "nif", "autorizacion_dgoj", "email")
    search_fields = ("nombre", "nif", "autorizacion_dgoj")


class ActaForm(forms.Form):
    numero_premiado = forms.IntegerField(
        min_value=1, label="Participación premiada según el acta"
    )
    protocolo = forms.CharField(max_length=120, label="Nº de protocolo del acta")
    fecha = forms.DateField(
        label="Fecha del acta", widget=forms.DateInput(attrs={"type": "date"})
    )


@admin.register(Sorteo)
class SorteoAdmin(admin.ModelAdmin):
    list_display = (
        "titulo",
        "estado",
        "fecha_sorteo",
        "vendidas_col",
        "recaudado_col",
        "acciones",
    )
    list_filter = ("estado",)
    search_fields = ("titulo", "slug")
    prepopulated_fields = {"slug": ("titulo",)}
    readonly_fields = ("creado_en", "actualizado_en")
    fieldsets = (
        (None, {"fields": ("proyecto", "organizador", "titulo", "slug", "estado")}),
        (
            "Premio",
            {
                "fields": (
                    "premio_descripcion",
                    "inmueble_direccion",
                    "inmueble_superficie",
                    "inmueble_referencia_catastral",
                    "inmueble_datos_registrales",
                    "inmueble_valor",
                    "inmueble_cargas",
                    "inmueble_gastos",
                )
            },
        ),
        (
            "Venta",
            {
                "fields": (
                    "precio_participacion",
                    "total_participaciones",
                    "max_por_pedido",
                    "reserva_minutos",
                    "fecha_inicio_venta",
                    "fecha_fin_venta",
                    "territorio",
                )
            },
        ),
        (
            "Sorteo",
            {
                "fields": (
                    "fecha_sorteo",
                    "hora_sorteo",
                    "notaria_nombre",
                    "notaria_poblacion",
                )
            },
        ),
        (
            "Condiciones de las bases",
            {
                "description": "Apartados 8 y 9 de las bases. Sin el mínimo de "
                "participaciones, el apartado 9 sale marcado como pendiente en "
                "la web.",
                "fields": (
                    "minimo_participaciones",
                    "dias_reintegro",
                    "organizador_asume_ingreso_cuenta",
                    "importe_ingreso_cuenta",
                    "tasa_juego_porcentaje",
                    "comision_pago_porcentaje",
                    "caducidad_premio_meses",
                    "version_bases",
                ),
            },
        ),
        ("Auditoría", {"fields": ("creado_en", "actualizado_en")}),
    )

    @admin.display(description="Vendidas")
    def vendidas_col(self, obj):
        return "{} / {}".format(obj.vendidas, obj.total_participaciones)

    @admin.display(description="Recaudado")
    def recaudado_col(self, obj):
        return "{:.2f} €".format(obj.recaudado)

    @admin.display(description="Acta")
    def acciones(self, obj):
        if hasattr(obj, "acta"):
            return "nº {}".format(obj.acta.numero_premiado)
        url = reverse("admin:sorteo_sorteo_acta", args=[obj.pk])
        return format_html('<a class="button" href="{}">Registrar acta</a>', url)

    def get_urls(self):
        extra = [
            path(
                "<int:pk>/acta/",
                self.admin_site.admin_view(self.vista_acta),
                name="sorteo_sorteo_acta",
            )
        ]
        return extra + super().get_urls()

    def save_model(self, request, obj, form, change):
        super().save_model(request, obj, form, change)
        creadas = obj.generar_papeletas()
        if creadas:
            self.message_user(
                request, "Se han generado {} papeletas.".format(creadas)
            )

    def vista_acta(self, request, pk):
        """
        Registro del acta notarial.

        Va aparte del formulario normal porque es irreversible y porque hay que
        validar contra las papeletas vendidas antes de guardar nada.
        """
        sorteo = self.get_object(request, pk)
        if sorteo is None:
            return redirect("admin:sorteo_sorteo_changelist")

        if hasattr(sorteo, "acta"):
            self.message_user(
                request, "Este sorteo ya tiene acta registrada.", messages.WARNING
            )
            return redirect("admin:sorteo_sorteo_changelist")

        form = ActaForm(request.POST or None)
        if request.method == "POST" and form.is_valid():
            try:
                registrar_acta(
                    sorteo,
                    form.cleaned_data["numero_premiado"],
                    form.cleaned_data["protocolo"],
                    form.cleaned_data["fecha"],
                    usuario=request.user,
                )
            except ErrorSorteo as exc:
                form.add_error("numero_premiado", str(exc))
            else:
                avisar_ganador(sorteo.acta)
                self.message_user(
                    request,
                    "Acta registrada, resultado publicado y aviso enviado a la "
                    "persona premiada.",
                )
                return redirect("admin:sorteo_sorteo_changelist")

        return render(
            request,
            "sorteo/admin_acta.html",
            {
                **self.admin_site.each_context(request),
                "sorteo": sorteo,
                "form": form,
                "title": "Registrar acta · {}".format(sorteo.titulo),
            },
        )


@admin.register(Pedido)
class PedidoAdmin(admin.ModelAdmin):
    list_display = (
        "codigo",
        "nombre",
        "email",
        "numeros_col",
        "importe",
        "estado",
        "creado_en",
    )
    list_filter = ("estado", "sorteo")
    search_fields = ("codigo", "nombre", "email", "telefono", "id")
    date_hierarchy = "creado_en"
    actions = ["exportar_csv"]

    # Un pedido es un registro contable y la prueba del consentimiento: se
    # consulta y se exporta, no se edita a mano.
    def has_add_permission(self, request):
        return False

    def has_change_permission(self, request, obj=None):
        return False

    @admin.display(description="Números")
    def numeros_col(self, obj):
        return obj.numeros_texto

    @admin.display(description="Exportar seleccionados a CSV")
    def exportar_csv(self, request, queryset):
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
                "version_bases",
                "acepta_bases_en",
                "ip",
                "creado_en",
            ]
        )
        for p in queryset.prefetch_related("papeletas"):
            escritor.writerow(
                [
                    p.codigo,
                    p.nombre,
                    p.email,
                    p.telefono,
                    p.numeros_texto,
                    p.importe,
                    p.estado,
                    p.version_bases,
                    p.acepta_bases_en.isoformat(),
                    p.ip or "",
                    p.creado_en.isoformat(),
                ]
            )
        return respuesta


@admin.register(Papeleta)
class PapeletaAdmin(admin.ModelAdmin):
    list_display = ("numero", "sorteo", "estado", "pedido")
    list_filter = ("estado", "sorteo")
    search_fields = ("numero",)

    def has_add_permission(self, request):
        return False


@admin.register(Interesado)
class InteresadoAdmin(admin.ModelAdmin):
    list_display = (
        "nombre", "email", "provincia", "participaciones_estimadas",
        "precio_maximo", "activo", "creado_en",
    )
    list_filter = ("precio_maximo", "provincia", "sorteo")
    search_fields = ("nombre", "email", "telefono", "provincia")
    date_hierarchy = "creado_en"
    readonly_fields = ("token_baja", "ip", "creado_en")

    @admin.display(boolean=True, description="Activo")
    def activo(self, obj):
        return obj.activo


@admin.register(ActaSorteo)
class ActaSorteoAdmin(admin.ModelAdmin):
    list_display = ("sorteo", "numero_premiado", "protocolo", "fecha", "registrado_por")

    def has_add_permission(self, request):
        return False

    def has_change_permission(self, request, obj=None):
        return False

    def has_delete_permission(self, request, obj=None):
        return False
