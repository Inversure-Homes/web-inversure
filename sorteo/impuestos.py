"""
Impuesto de la compra del inmueble: ITP o IVA.

Módulo de funciones puras, sin modelos. Vive aquí porque lo usa el sorteo, pero
no tiene nada específico de rifas: cuando el simulador lo necesite, se mueve a
`core` sin tocar nada más.

Dos ejes deciden el resultado:

- **Quién vende.** Si es un particular o una empresa fuera de su actividad, la
  compra va por ITP, cuyo tipo fija cada comunidad autónoma. Si es un promotor
  y es primera entrega, va por IVA más AJD.
- **Dónde está el inmueble.** El ITP está cedido a las comunidades y va del 4 %
  al 10 % largo.

Y una regla que se olvida a menudo: desde 2022 **la base imponible del ITP es
el mayor entre el precio escriturado y el valor de referencia de Catastro**.
Comprar barato no siempre baja el impuesto.
"""

from decimal import ROUND_HALF_UP, Decimal

CIEN = Decimal("100")

# Tipo general del ITP para segunda transmisión, en porcentaje.
#
# CIFRAS DE 2026. Los tipos los fija cada comunidad y cambian con sus
# presupuestos: conviene revisarlos una vez al año. Los que llevan `escala`
# tienen tramos y aquí figura el tipo de entrada, así que sobre importes altos
# se quedan cortos.
TIPOS_ITP = {
    "andalucia": {"nombre": "Andalucía", "tipo": Decimal("7")},
    "aragon": {"nombre": "Aragón", "tipo": Decimal("8")},
    "asturias": {"nombre": "Asturias", "tipo": Decimal("8")},
    "baleares": {"nombre": "Baleares", "tipo": Decimal("8"), "escala": True},
    "canarias": {"nombre": "Canarias", "tipo": Decimal("6.5")},
    "cantabria": {"nombre": "Cantabria", "tipo": Decimal("10")},
    "castilla_la_mancha": {"nombre": "Castilla-La Mancha", "tipo": Decimal("9")},
    "castilla_leon": {"nombre": "Castilla y León", "tipo": Decimal("8")},
    "cataluna": {"nombre": "Cataluña", "tipo": Decimal("10")},
    "valencia": {"nombre": "Comunitat Valenciana", "tipo": Decimal("10")},
    "extremadura": {"nombre": "Extremadura", "tipo": Decimal("8"), "escala": True},
    "galicia": {"nombre": "Galicia", "tipo": Decimal("9")},
    "madrid": {"nombre": "Madrid", "tipo": Decimal("6")},
    "murcia": {"nombre": "Murcia", "tipo": Decimal("8")},
    "navarra": {"nombre": "Navarra", "tipo": Decimal("6")},
    "pais_vasco": {"nombre": "País Vasco", "tipo": Decimal("4"), "escala": True},
    "rioja": {"nombre": "La Rioja", "tipo": Decimal("7")},
    "ceuta": {"nombre": "Ceuta", "tipo": Decimal("6"), "revisar": True},
    "melilla": {"nombre": "Melilla", "tipo": Decimal("6"), "revisar": True},
}

COMUNIDADES = [(clave, datos["nombre"]) for clave, datos in TIPOS_ITP.items()]

# IVA de una plaza de garaje en primera entrega, comprada suelta. Si va unida a
# una vivienda en la misma operación y no son más de dos, tributa al 10 %.
IVA_GARAJE_SUELTO = Decimal("21")
IVA_GARAJE_CON_VIVIENDA = Decimal("10")

# AJD medio. Varía entre el 0,5 % y el 2 % según comunidad, así que es un
# parámetro y no una tabla: aquí solo se usa como valor de partida.
AJD_POR_DEFECTO = Decimal("1.5")


class Operacion:
    ITP = "itp"
    IVA = "iva"
    OPCIONES = [
        (ITP, "ITP · compra a particular o segunda transmisión"),
        (IVA, "IVA + AJD · primera entrega de promotor"),
    ]


def _eur(valor):
    return Decimal(valor).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)


def base_imponible(precio, valor_referencia=None):
    """
    Base del impuesto: el mayor entre el precio y el valor de referencia.

    Desde 2022 Hacienda no acepta sin más el importe escriturado. Si el valor
    de referencia de Catastro es más alto, es ese el que manda.
    """
    precio = Decimal(precio or 0)
    referencia = Decimal(valor_referencia or 0)
    return max(precio, referencia)


def calcular(
    precio,
    comunidad,
    operacion=Operacion.ITP,
    valor_referencia=None,
    con_vivienda=False,
    ajd=None,
):
    """
    Impuesto de la compra. Devuelve importe, tipo aplicado y de dónde sale.

    No sustituye a una gestoría: no contempla tipos reducidos por edad, familia
    numerosa, VPO ni los tramos de las comunidades con escala.
    """
    base = base_imponible(precio, valor_referencia)
    avisos = []

    if base > Decimal(precio or 0):
        avisos.append(
            "Se aplica el valor de referencia de Catastro ({:.2f} €) por ser mayor que el precio.".format(base)
        )

    if operacion == Operacion.IVA:
        tipo = IVA_GARAJE_CON_VIVIENDA if con_vivienda else IVA_GARAJE_SUELTO
        tipo_ajd = Decimal(ajd if ajd is not None else AJD_POR_DEFECTO)
        importe = _eur(base * tipo / CIEN) + _eur(base * tipo_ajd / CIEN)
        avisos.append("AJD estimado al {:.10g} %: varía entre el 0,5 % y el 2 % según comunidad.".format(tipo_ajd))
        return {
            "impuesto": "IVA + AJD",
            "tipo": tipo,
            "tipo_ajd": tipo_ajd,
            "base": base,
            "importe": importe,
            "avisos": avisos,
        }

    datos = TIPOS_ITP.get(comunidad)
    if datos is None:
        return {
            "impuesto": "ITP",
            "tipo": None,
            "base": base,
            "importe": Decimal("0"),
            "avisos": ["Indica la comunidad autónoma para calcular el ITP."],
        }

    if datos.get("escala"):
        avisos.append(
            "{} aplica una escala por tramos. Este es el tipo de entrada, así "
            "que sobre importes altos se queda corto.".format(datos["nombre"])
        )
    if datos.get("revisar"):
        avisos.append("El tipo de {} hay que confirmarlo: puede tener bonificaciones propias.".format(datos["nombre"]))

    return {
        "impuesto": "ITP",
        "tipo": datos["tipo"],
        "base": base,
        "importe": _eur(base * datos["tipo"] / CIEN),
        "avisos": avisos,
    }
