"""
Puente entre el sorteo y la economía del proyecto en el ERP.

La venta de participaciones se vuelca al `Proyecto` como ingresos, para que la
memoria económica y el PDF de rentabilidad funcionen sin tocarlos. Se consolida
**por día**: con miles de pedidos, un apunte por cada uno haría ilegible la
memoria.
"""

from decimal import Decimal

from django.db.models import Count, Sum
from django.db.models.functions import TruncDate

from core.models import GastoProyecto, IngresoProyecto

from .models import Interesado, Pedido

# Prefijo con el que se reconocen los apuntes generados por el sorteo, para
# poder actualizarlos sin duplicar.
MARCA = "[sorteo]"


def consolidar_ingresos(sorteo):
    """
    Crea o actualiza un `IngresoProyecto` por cada día con ventas.

    Idempotente: se puede ejecutar tantas veces como haga falta. Reconoce sus
    propios apuntes por el prefijo del concepto.
    """
    dias = (
        Pedido.objects.filter(sorteo=sorteo, estado=Pedido.Estado.PAGADO)
        .annotate(dia=TruncDate("pagado_en"))
        .values("dia")
        .annotate(pedidos=Count("id"), papeletas=Count("papeletas"))
        .order_by("dia")
    )

    tocados = 0
    for fila in dias:
        if not fila["dia"]:
            continue
        importe = Decimal(fila["papeletas"]) * sorteo.precio_participacion
        concepto = "{} Venta de participaciones · {}".format(MARCA, fila["dia"].isoformat())
        IngresoProyecto.objects.update_or_create(
            proyecto=sorteo.proyecto,
            concepto=concepto,
            defaults={
                "fecha": fila["dia"],
                "tipo": "otro",
                "importe": importe,
                "importe_real": importe,
                "estado": "confirmado",
                "pagado": True,
                "observaciones": "{} participaciones en {} pedidos. Apunte "
                "generado automáticamente por la app de sorteos.".format(fila["papeletas"], fila["pedidos"]),
            },
        )
        tocados += 1
    return tocados


def gastos_previstos(sorteo):
    """
    Gastos que la propia mecánica de la rifa genera, calculados a partir de la
    configuración del sorteo. Sirven para el panel y para dar de alta los
    apuntes en el proyecto.

    La tasa sobre actividades de juego se calcula sobre las participaciones
    EMITIDAS, no sobre las vendidas: se paga igual se venda todo o la mitad.
    """
    emitido = sorteo.total_participaciones * sorteo.precio_participacion
    tipo = Decimal(sorteo.tasa_juego_porcentaje) / Decimal("100")
    tasa = (emitido * tipo).quantize(Decimal("0.01"))

    valor = valor_premio(sorteo)
    ingreso_cuenta = (valor * Decimal("1.20") * Decimal("0.19")).quantize(Decimal("0.01"))

    filas = [
        {
            "concepto": "Tasa sobre actividades de juego ({:.10g} % de los ingresos brutos)".format(
                sorteo.tasa_juego_porcentaje
            ),
            "categoria": "legales",
            "importe": tasa,
            "nota": "Se anticipa sobre las {} participaciones emitidas.".format(sorteo.total_participaciones),
        }
    ]
    if sorteo.organizador_asume_ingreso_cuenta and valor:
        filas.append(
            {
                "concepto": "Ingreso a cuenta del IRPF sobre el premio",
                "categoria": "legales",
                "importe": ingreso_cuenta,
                "nota": "19 % sobre el valor del premio incrementado en un 20 %.",
            }
        )
    return filas


def crear_gastos_previstos(sorteo):
    """Da de alta en el proyecto los gastos propios de la rifa. Idempotente."""
    creados = 0
    for fila in gastos_previstos(sorteo):
        concepto = "{} {}".format(MARCA, fila["concepto"])
        _, nuevo = GastoProyecto.objects.get_or_create(
            proyecto=sorteo.proyecto,
            concepto=concepto,
            defaults={
                "fecha": sorteo.fecha_inicio_venta,
                "categoria": fila["categoria"],
                "importe": fila["importe"],
                "importe_estimado": fila["importe"],
                "estado": "estimado",
                "observaciones": fila["nota"],
            },
        )
        creados += int(nuevo)
    return creados


def demanda(sorteo):
    """
    Qué dice la lista de espera.

    Es la única medida de demanda disponible antes de comprar el inmueble, así
    que conviene mirarla junto al umbral de rentabilidad: si los interesados no
    se acercan a esa cifra, el sorteo no se sostiene.
    """
    activos = Interesado.objects.filter(sorteo=sorteo, baja_en__isnull=True)
    total = activos.count()
    participaciones = activos.aggregate(n=Sum("participaciones_estimadas"))["n"] or 0

    por_precio = []
    acumulado = 0
    for valor, etiqueta in reversed(Interesado.Precio.choices):
        n = activos.filter(precio_maximo=valor).count()
        acumulado += n
        por_precio.insert(
            0,
            {
                "etiqueta": etiqueta,
                "personas": n,
                "aceptarian": acumulado,
                "porcentaje": round(acumulado * 100 / total) if total else 0,
            },
        )

    return {
        "personas": total,
        "participaciones": participaciones,
        "media": round(participaciones / total, 1) if total else 0,
        "por_precio": por_precio,
        "provincias": list(
            activos.exclude(provincia="").values("provincia").annotate(n=Count("id")).order_by("-n")[:6]
        ),
    }


def gastos_base(sorteo):
    """
    Gastos reales del proyecto, excluidos los que calcula la propia app.

    Son los que no dependen del dimensionado del sorteo —la plaza, su ITP, la
    notaría, la gestoría— y por tanto los que la calculadora toma como dato
    fijo al proponer precio y número de participaciones.
    """
    total = Decimal("0")
    for g in GastoProyecto.objects.filter(proyecto=sorteo.proyecto):
        if (g.concepto or "").startswith(MARCA):
            continue
        total += g.importe_real or g.importe or Decimal("0")

    if total:
        return total

    # Sin gastos registrados, se toman los de la ficha del proyecto. Es el caso
    # normal al empezar: se rellena el proyecto y no se ha dado de alta ningún
    # gasto todavía. Sin esto la calculadora vería cero y daría cifras absurdas.
    return coste_adquisicion(sorteo.proyecto)


# Campos de la ficha del proyecto que componen el coste de adquisición. Se
# listan explícitamente para que se vea qué entra y qué no.
CAMPOS_ADQUISICION = (
    "precio_compra_inmueble",
    "itp",
    "notaria",
    "registro",
    "otros_gastos_compra",
    "reforma",
)


def coste_adquisicion(proyecto):
    total = Decimal("0")
    for campo in CAMPOS_ADQUISICION:
        total += getattr(proyecto, campo, None) or Decimal("0")
    return total


def desglose_gastos_base(sorteo):
    """De dónde salen los gastos fijos, para poder enseñarlo en el panel."""
    manuales = [
        g for g in GastoProyecto.objects.filter(proyecto=sorteo.proyecto) if not (g.concepto or "").startswith(MARCA)
    ]
    if manuales:
        return {
            "origen": "gastos",
            "total": sum((g.importe_real or g.importe or Decimal("0")) for g in manuales),
            "filas": [
                {
                    "concepto": g.concepto,
                    "importe": g.importe_real or g.importe or Decimal("0"),
                }
                for g in manuales
            ],
        }

    proyecto = sorteo.proyecto
    filas = [
        {
            "concepto": proyecto._meta.get_field(campo).verbose_name or campo,
            "importe": getattr(proyecto, campo, None) or Decimal("0"),
        }
        for campo in CAMPOS_ADQUISICION
        if getattr(proyecto, campo, None)
    ]
    return {
        "origen": "ficha",
        "total": coste_adquisicion(proyecto),
        "filas": filas,
    }


def valor_premio(sorteo):
    """
    Valor del premio para el ingreso a cuenta del IRPF.

    Si no se ha indicado en el sorteo se toma el precio de compra del proyecto,
    que es lo que se quiere el 95 % de las veces.
    """
    return sorteo.inmueble_valor or sorteo.proyecto.precio_compra_inmueble or Decimal("0")


def resumen_economico(sorteo):
    """
    Cifras para el panel del ERP.

    La que importa de verdad es `faltan_equilibrio`: cuántas participaciones
    quedan por vender para dejar de perder dinero.
    """
    vendidas = sorteo.vendidas
    recaudado = vendidas * sorteo.precio_participacion

    # Base + los gastos que genera la propia rifa. No hay doble conteo porque
    # `gastos_base` excluye los apuntes marcados, y así el umbral sale correcto
    # tanto si ya se han volcado al proyecto como si todavía no.
    coste_total = gastos_base(sorteo) + sum(f["importe"] for f in gastos_previstos(sorteo))

    precio = sorteo.precio_participacion or Decimal("1")
    equilibrio = int(-(-coste_total // precio)) if coste_total else 0
    faltan = max(0, equilibrio - vendidas)

    return {
        "vendidas": vendidas,
        "reservadas": sorteo.reservadas,
        "disponibles": sorteo.disponibles,
        "porcentaje": sorteo.porcentaje_vendido,
        "recaudado": recaudado,
        "objetivo": sorteo.objetivo,
        "coste_total": coste_total,
        "resultado": recaudado - coste_total,
        "equilibrio": equilibrio,
        "faltan_equilibrio": faltan,
        "porcentaje_equilibrio": (
            round(equilibrio * 100 / sorteo.total_participaciones) if sorteo.total_participaciones else 0
        ),
        "minimo": sorteo.minimo_participaciones,
        "faltan_minimo": (max(0, sorteo.minimo_participaciones - vendidas) if sorteo.minimo_participaciones else None),
    }
