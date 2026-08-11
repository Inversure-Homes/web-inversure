"""
Comparador de escenarios de desinversión.

Un inmueble se puede vender o se puede rifar, y hasta ahora esas dos rutas se
medían en herramientas distintas: el simulador para la venta y la calculadora
del sorteo para la rifa. Nadie las ponía una al lado de la otra, que es
justamente lo que hay que mirar antes de comprar.

Las dos rutas no son comparables solo por el beneficio:

- La **venta** tiene un techo (el precio de mercado) y un riesgo de plazo: si
  no se vende, se mantiene el activo y se sigue esperando.
- La **rifa** puede superar el valor de mercado, pero casi todo su coste es
  fijo —la tasa se paga sobre lo emitido— y el riesgo es de colocación: si no
  se venden suficientes participaciones, se pierde dinero.

Por eso el comparador devuelve, además del beneficio, el **plazo** y una
medida de riesgo de cada ruta.
"""

from decimal import ROUND_CEILING, ROUND_HALF_UP, Decimal

from .calculadora import Config, escenarios
from .impuestos import Operacion, calcular

CIEN = Decimal("100")

# Cuántos compradores distintos hay que convencer antes de que la campaña deje
# de ser realista. Son un juicio, no una ley: una rifa local llega sin esfuerzo
# a unos cientos de personas; pasar del millar exige campaña seria y
# presupuesto. Se tocan aquí si la experiencia dice otra cosa.
COMPRADORES_HOLGADO = 400
COMPRADORES_LIMITE = 1000


def _eur(v):
    return Decimal(v).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)


def _num(valor, decimales=0):
    """
    Importe en formato español: 10.746 €, no 10746.00 €.

    Estas cadenas se componen aquí y no en la plantilla, así que el formato hay
    que darlo aquí también.
    """
    texto = "{:,.{}f}".format(Decimal(valor), decimales)
    entera, _, decimal = texto.partition(".")
    entera = entera.replace(",", ".")
    return "{},{}".format(entera, decimal) if decimal else entera


def _pct(parte, sobre):
    if not sobre:
        return Decimal("0")
    return (Decimal(parte) * CIEN / Decimal(sobre)).quantize(Decimal("0.1"))


def coste_entrada(datos):
    """Lo que cuesta poner el inmueble en balance, con su impuesto."""
    precio = Decimal(datos.get("precio_compra") or 0)
    impuesto = calcular(
        precio,
        datos.get("comunidad") or "",
        datos.get("operacion") or Operacion.ITP,
        valor_referencia=datos.get("valor_referencia"),
        supuesto=datos.get("supuesto_reducido") or None,
        perfil={"empresa_inmobiliaria": True, "reventa": True},
    )
    otros = Decimal(datos.get("otros_gastos") or 0)
    return {
        "precio": precio,
        "impuesto": impuesto,
        "otros": otros,
        "total": _eur(precio + impuesto["importe"] + otros),
    }


def escenario_venta(datos, entrada):
    """Venta ordinaria: se vende al precio estimado y se acabó."""
    ingresos = Decimal(datos.get("precio_venta") or 0)
    comision = Decimal(datos.get("comision_venta_pct") or 0) / CIEN * ingresos
    costes = entrada["total"] + _eur(comision)
    beneficio = _eur(ingresos - costes)
    meses = int(datos.get("meses_venta") or 0)

    return {
        "nombre": "Venta ordinaria",
        "ingresos": _eur(ingresos),
        "costes": _eur(costes),
        "beneficio": beneficio,
        "roi": _pct(beneficio, entrada["total"]),
        "meses": meses,
        "por_mes": _eur(beneficio / meses) if meses else None,
        "riesgo": "El precio de venta es una estimación y el plazo puede "
        "alargarse, pero si no se vende el inmueble sigue en balance: no se "
        "pierde, se retrasa.",
        "tope": "Limitado por el precio de mercado.",
    }


def escenario_rifa(datos, entrada):
    """Rifa: puede superar el valor de mercado, pero hay que colocarla."""
    cfg = Config(
        precio=datos.get("precio_participacion") or 10,
        emitidas=datos.get("participaciones") or 1,
        valor_premio=datos.get("precio_compra") or 0,
        tasa_pct=datos.get("tasa_pct") or 20,
        comision_pct=datos.get("comision_pago_pct") or "2.30",
    )
    resultado = escenarios(cfg, entrada["total"])
    pleno = resultado["filas"][2]
    meses = int(datos.get("meses_rifa") or 0)

    return {
        "nombre": "Rifa",
        "ingresos": pleno["ingresos"],
        "costes": pleno["costes"],
        "beneficio": pleno["resultado"],
        "roi": _pct(pleno["resultado"], entrada["total"]),
        "meses": meses,
        "por_mes": _eur(pleno["resultado"] / meses) if meses else None,
        "umbral": resultado["umbral"],
        "umbral_porcentaje": resultado["umbral_porcentaje"],
        "compradores": resultado["compradores"],
        "cancelacion": resultado["filas"][0]["resultado"],
        "riesgo": "Hay que colocar {} participaciones ({} %) solo para no "
        "perder dinero, porque la tasa se paga sobre lo emitido. Si no se "
        "llega y se cancela, se reintegra todo y el inmueble se conserva.".format(
            _num(resultado["umbral"]), resultado["umbral_porcentaje"]
        ),
        "tope": "Puede superar el valor de mercado del inmueble.",
        "detalle": resultado,
    }


def comparar(datos):
    """
    Mide las dos rutas sobre el mismo inmueble.

    No declara un ganador con una fórmula: las dos rutas tienen riesgos de
    naturaleza distinta y eso no se resuelve con un número. Lo que hace es
    poner las cifras juntas y decir en qué se diferencian.
    """
    entrada = coste_entrada(datos)
    venta = escenario_venta(datos, entrada)
    rifa = escenario_rifa(datos, entrada)

    diferencia = _eur(rifa["beneficio"] - venta["beneficio"])
    lecturas = []

    if diferencia > 0:
        lecturas.append(
            "A pleno, la rifa deja {} € más que la venta. Pero ese resultado "
            "exige colocar el {} % de las participaciones; la venta no tiene "
            "esa condición.".format(_num(diferencia), rifa["umbral_porcentaje"])
        )
    else:
        lecturas.append(
            "Incluso agotando las participaciones, la rifa deja {} € menos "
            "que la venta. Con ese margen no compensa el riesgo de "
            "colocación.".format(_num(abs(diferencia)))
        )

    if venta["por_mes"] and rifa["por_mes"]:
        mejor = "rifa" if rifa["por_mes"] > venta["por_mes"] else "venta"
        lecturas.append(
            "Por mes de capital inmovilizado: {} €/mes la venta frente a {} €/mes la rifa. Gana la {}.".format(
                _num(venta["por_mes"]), _num(rifa["por_mes"]), mejor
            )
        )

    if rifa["umbral_porcentaje"] > 75:
        lecturas.append(
            "Un umbral del {} % es alto: deja poquísimo margen de error en la campaña de venta.".format(
                rifa["umbral_porcentaje"]
            )
        )

    # Veredicto para el KPI de decisión.
    #
    # Manda el número ABSOLUTO de compradores, no el porcentaje del umbral. El
    # porcentaje engaña: emitir más participaciones lo baja un punto mientras
    # multiplica por cinco la gente a la que hay que convencer, y vender es un
    # problema de personas, no de proporciones.
    compradores = rifa["compradores"]
    if diferencia <= 0:
        decision = {
            "texto": "Vender",
            "tono": "secondary",
            "motivo": "La venta ordinaria deja más y sin riesgo de colocación.",
        }
    elif compradores > COMPRADORES_LIMITE:
        decision = {
            "texto": "Revisar",
            "tono": "danger",
            "motivo": "Hacen falta {} compradores distintos: exige una campaña seria y con presupuesto.".format(
                _num(compradores)
            ),
        }
    elif compradores > COMPRADORES_HOLGADO:
        decision = {
            "texto": "Rifar con cautela",
            "tono": "warning",
            "motivo": "Compensa, pero hay que convencer a {} personas.".format(_num(compradores)),
        }
    else:
        decision = {
            "texto": "Rifar",
            "tono": "success",
            "motivo": "Buen resultado y bastan {} compradores.".format(_num(compradores)),
        }

    return {
        "entrada": entrada,
        "venta": venta,
        "rifa": rifa,
        "decision": decision,
        # Las plantillas no pueden construir listas: se les da hecha.
        "rutas": [venta, rifa],
        "diferencia": diferencia,
        "lecturas": lecturas,
    }


def desde_proyecto(proyecto):
    """
    Precarga un estudio desde un proyecto del ERP.

    Devuelve las claves del FORMULARIO, no las del comparador: es lo que se usa
    como `initial`. La distinción importa — `precio_venta_estimado` aquí,
    `precio_venta` en `comparar()`.
    """
    otros = Decimal("0")
    for campo in ("notaria", "registro", "otros_gastos_compra", "reforma"):
        otros += getattr(proyecto, campo, None) or Decimal("0")

    return {
        "precio_compra": proyecto.precio_compra_inmueble or Decimal("0"),
        "valor_referencia": proyecto.valor_referencia,
        "otros_gastos": otros,
        "precio_venta_estimado": proyecto.precio_venta_estimado or Decimal("0"),
        "meses_venta": proyecto.meses or 6,
    }


def _techo(v):
    return int(Decimal(v).to_integral_value(rounding=ROUND_CEILING))
