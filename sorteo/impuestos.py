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


# =============================================================================
# Tipos reducidos
# =============================================================================
#
# El catálogo es DELIBERADAMENTE PARCIAL. Cada comunidad tiene sus propios
# supuestos, con límites de valor, edad, empadronamiento y plazos, y cambian
# todos los años. Aquí solo están los que se han podido contrastar; el resto se
# consulta con la gestoría.
#
# Y una decisión de diseño que importa: **ningún tipo reducido se aplica solo**.
# El software no puede verificar si se cumplen los requisitos —que la sociedad
# tenga la actividad principal correcta, que se declare en escritura, que se
# revenda dentro de plazo—, y aplicar uno indebidamente significa pagar después
# la diferencia más intereses. Se ofrecen como candidatos, con sus requisitos a
# la vista, y alguien decide.
#
# `perfil` son las condiciones que deben darse para que el supuesto ni siquiera
# se ofrezca. `requisitos` es lo que hay que cumplir y acreditar.

SUPUESTOS_REDUCIDOS = {
    "andalucia": [
        {
            "clave": "reventa_profesional",
            "nombre": "Adquisición por profesional inmobiliario para reventa",
            "tipo": Decimal("2"),
            "perfil": {"empresa_inmobiliaria": True, "reventa": True},
            "limite_valor": Decimal("500000"),
            "requisitos": [
                "La actividad principal debe ser construcción, promoción o compraventa de inmuebles por cuenta propia.",
                "El inmueble se incorpora al activo circulante (existencias).",
                "La intención de revender debe declararse en la escritura.",
                "Desde 2026: revender en 2 años y valor máximo de 500.000 € incluidos anexos y garajes.",
            ],
            "aviso": "Si no se revende dentro del plazo hay que ingresar la "
            "diferencia con el tipo general más intereses de demora.",
        }
    ],
    "madrid": [
        {
            "clave": "reventa_profesional",
            "nombre": "Adquisición por profesional inmobiliario para reventa",
            "tipo": Decimal("2"),
            "perfil": {"empresa_inmobiliaria": True, "reventa": True},
            "requisitos": [
                "Solo sociedades: no lo pueden aplicar los empresarios individuales.",
                "Actividad principal de construcción, promoción o compraventa de inmuebles.",
                "Debe constar en escritura que el inmueble entra en existencias para su reventa.",
                "Plazo de reventa: 2 años.",
            ],
            "aviso": "Si no se revende dentro del plazo hay que ingresar la "
            "diferencia con el tipo general más intereses de demora.",
        }
    ],
    "murcia": [
        {
            "clave": "reventa_profesional",
            "nombre": "Adquisición por profesional inmobiliario para reventa",
            "tipo": Decimal("2"),
            "perfil": {"empresa_inmobiliaria": True, "reventa": True},
            "requisitos": [
                "Aplicable tanto a sociedades como a empresarios individuales.",
                "Sujeción al Plan General de Contabilidad del sector inmobiliario, con el inmueble en existencias.",
                "Confirmar el plazo de reventa vigente.",
            ],
            "aviso": "Si no se revende dentro del plazo hay que ingresar la "
            "diferencia con el tipo general más intereses de demora.",
        }
    ],
    "aragon": [
        {
            "clave": "reventa_profesional",
            "nombre": "Adquisición por profesional inmobiliario para reventa",
            "tipo": Decimal("2"),
            "perfil": {"empresa_inmobiliaria": True, "reventa": True},
            "revisar": True,
            "requisitos": [
                "Dato sin contrastar del todo: confirmar tipo, plazo y requisitos con la gestoría antes de aplicarlo.",
            ],
            "aviso": "Si no se revende dentro del plazo hay que ingresar la "
            "diferencia con el tipo general más intereses de demora.",
        }
    ],
    "valencia": [
        {
            "clave": "joven",
            "nombre": "Menor de 35 años, primera vivienda habitual",
            "tipo": Decimal("6"),
            "perfil": {"joven": True, "vivienda_habitual": True},
            "requisitos": [
                "Base liquidable máxima de 30.000 € en tributación individual y 47.000 € en conjunta.",
            ],
        },
        {
            "clave": "familia_discapacidad",
            "nombre": "Familia numerosa, discapacidad ≥ 65 % o víctima de violencia",
            "tipo": Decimal("4"),
            "perfil": {"vivienda_habitual": True},
            "limite_valor": Decimal("180000"),
            "requisitos": ["Vivienda habitual de valor no superior a 180.000 €."],
        },
    ],
    "rioja": [
        {
            "clave": "joven",
            "nombre": "Menor de 40 años",
            "tipo": Decimal("4"),
            "perfil": {"joven": True, "vivienda_habitual": True},
            "requisitos": ["Baja al 3 % en municipios pequeños."],
        },
        {
            "clave": "vpo_discapacidad",
            "nombre": "VPO o discapacidad ≥ 33 %",
            "tipo": Decimal("5"),
            "perfil": {"vivienda_habitual": True},
            "requisitos": [],
        },
    ],
}


# Comunidades donde SÍ se ha contrastado el supuesto de reventa profesional.
# Fuera de esta lista el sistema no promete nada.
CON_REVENTA_PROFESIONAL = {"andalucia", "madrid", "murcia", "aragon"}

# Avisos informativos por comunidad, para lo que conviene saber aunque no se
# traduzca en un tipo aplicable.
NOTAS_COMUNIDAD = {
    "cataluna": "La bonificación del 70 % de la cuota por reventa profesional "
    "quedó suprimida el 27 de marzo de 2025: las adquisiciones posteriores no "
    "la tienen.",
    "valencia": "Las bonificaciones de la cuota van ligadas a eficiencia "
    "energética, accesibilidad o destino al alquiler, no a la simple reventa.",
}


def supuestos_aplicables(comunidad, perfil=None):
    """
    Tipos reducidos que **podrían** aplicar, dado el perfil de la operación.

    No decide: filtra. La comprobación real de requisitos es de la gestoría.
    """
    perfil = perfil or {}
    candidatos = []
    for supuesto in SUPUESTOS_REDUCIDOS.get(comunidad, []):
        if all(perfil.get(k) == v for k, v in supuesto["perfil"].items()):
            candidatos.append(supuesto)
    return candidatos


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
    supuesto=None,
    perfil=None,
):
    """
    Impuesto de la compra. Devuelve importe, tipo aplicado y de dónde sale.

    Con `supuesto` se aplica un tipo reducido concreto, que alguien ha decidido
    aplicar a sabiendas. Sin él se calcula al tipo general y, si el perfil da
    para alguno, se devuelven como `candidatos` para que se vean.

    No sustituye a una gestoría: no contempla todos los supuestos de todas las
    comunidades ni los tramos de las que aplican escala.
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
            "supuesto": None,
            "base": base,
            "importe": importe,
            "candidatos": [],
            "avisos": avisos,
        }

    datos = TIPOS_ITP.get(comunidad)
    if datos is None:
        return {
            "impuesto": "ITP",
            "tipo": None,
            "base": base,
            "importe": Decimal("0"),
            "candidatos": [],
            "avisos": ["Indica la comunidad autónoma para calcular el ITP."],
        }

    if comunidad in NOTAS_COMUNIDAD:
        avisos.append(NOTAS_COMUNIDAD[comunidad])

    perfil = perfil or {}
    if (
        perfil.get("empresa_inmobiliaria")
        and perfil.get("reventa")
        and comunidad not in CON_REVENTA_PROFESIONAL
        and comunidad not in NOTAS_COMUNIDAD
    ):
        avisos.append(
            "No consta un tipo reducido por reventa profesional en {}. "
            "Muchas comunidades lo tienen: conviene preguntarlo antes de "
            "escriturar, porque después no se puede rectificar.".format(datos["nombre"])
        )

    candidatos = supuestos_aplicables(comunidad, perfil)
    elegido = None
    if supuesto:
        elegido = next((s for s in candidatos if s["clave"] == supuesto), None)
        if elegido is None:
            avisos.append(
                "El tipo reducido «{}» no consta como aplicable en {}: se calcula al tipo general.".format(
                    supuesto, datos["nombre"]
                )
            )

    if elegido:
        limite = elegido.get("limite_valor")
        if limite and base > limite:
            avisos.append(
                "El valor supera el límite de {:.0f} € del tipo reducido: se aplica el general.".format(limite)
            )
            elegido = None

    if elegido and elegido.get("revisar"):
        avisos.append("Este supuesto está en el catálogo sin contrastar del todo. No lo des por bueno sin confirmarlo.")

    if elegido:
        avisos.extend(elegido.get("requisitos", []))
        if elegido.get("aviso"):
            avisos.append(elegido["aviso"])
        return {
            "impuesto": "ITP",
            "tipo": elegido["tipo"],
            "supuesto": elegido["nombre"],
            "base": base,
            "importe": _eur(base * elegido["tipo"] / CIEN),
            "candidatos": candidatos,
            "avisos": avisos,
        }

    for c in candidatos:
        avisos.append(
            "Podría aplicar el tipo reducido del {:.10g} % por «{}». Habría que comprobar los requisitos.".format(
                c["tipo"], c["nombre"]
            )
        )

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
        "supuesto": None,
        "base": base,
        "importe": _eur(base * datos["tipo"] / CIEN),
        "candidatos": candidatos,
        "avisos": avisos,
    }
