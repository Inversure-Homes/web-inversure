"""
Escenarios y dimensionado del sorteo.

Funciona con o sin `Sorteo` creado: las funciones toman una `Config` plana, de
modo que se puede estudiar si compensa rifar un inmueble **antes** de comprarlo
y sin ensuciar el ERP con proyectos ficticios.

La aritmética de una rifa tiene una particularidad que la hace poco intuitiva:
**la tasa sobre actividades de juego se anticipa sobre las participaciones
emitidas, no sobre las vendidas**. Emitir de más no es gratis.

De ahí salen las dos conclusiones que este módulo calcula:

1. El umbral de rentabilidad tiene un suelo estructural: por mucho que se
   diluyan los gastos fijos, nunca baja del tipo de la tasa (20 % o 7 %).
2. Para un mismo objetivo de ingresos, **subir el precio y emitir menos
   participaciones reduce el número de papeletas que hay que colocar**. Cuesta
   conversión, pero es estructuralmente más seguro.
"""

from decimal import Decimal, ROUND_CEILING, ROUND_HALF_UP

CIEN = Decimal("100")
DOS = Decimal("0.01")

# Cuántas participaciones compra de media cada persona. Solo se usa para
# traducir papeletas a compradores, que es lo que se puede estimar de verdad.
PARTICIPACIONES_POR_COMPRADOR = Decimal("3")


class Config:
    """Parámetros de un sorteo, real o hipotético."""

    def __init__(
        self,
        precio,
        emitidas,
        valor_premio=0,
        minimo=None,
        asume_ingreso_cuenta=True,
        tasa_pct=20,
        comision_pct="2.30",
    ):
        self.precio = Decimal(precio)
        self.emitidas = int(emitidas)
        self.valor_premio = Decimal(valor_premio or 0)
        self.minimo = int(minimo) if minimo else None
        self.asume_ingreso_cuenta = bool(asume_ingreso_cuenta)
        self.tasa = Decimal(tasa_pct) / CIEN
        self.comision = Decimal(comision_pct) / CIEN

    @classmethod
    def desde_sorteo(cls, sorteo):
        return cls(
            precio=sorteo.precio_participacion,
            emitidas=sorteo.total_participaciones,
            valor_premio=sorteo.inmueble_valor,
            minimo=sorteo.minimo_participaciones,
            asume_ingreso_cuenta=sorteo.organizador_asume_ingreso_cuenta,
            tasa_pct=sorteo.tasa_juego_porcentaje,
            comision_pct=sorteo.comision_pago_porcentaje,
        )


def _eur(valor):
    return Decimal(valor).quantize(DOS, rounding=ROUND_HALF_UP)


def _techo(valor):
    return int(Decimal(valor).to_integral_value(rounding=ROUND_CEILING))


def ingreso_a_cuenta(valor_premio, asume_organizador=True):
    """19 % sobre el valor del premio incrementado en un 20 %."""
    if not valor_premio or not asume_organizador:
        return Decimal("0")
    return _eur(Decimal(valor_premio) * Decimal("1.20") * Decimal("0.19"))


def evaluar(cfg, vendidas, gastos_base, emitidas=None, precio=None):
    """
    Resultado de vender `vendidas` participaciones.

    La tasa se calcula sobre lo emitido; la comisión, solo sobre lo vendido.
    """
    precio = Decimal(precio if precio is not None else cfg.precio)
    emitidas = int(emitidas if emitidas is not None else cfg.emitidas)

    ingresos = precio * vendidas
    tasa = _eur(precio * emitidas * cfg.tasa)
    comision = _eur(ingresos * cfg.comision)
    ia = ingreso_a_cuenta(cfg.valor_premio, cfg.asume_ingreso_cuenta)
    costes = Decimal(gastos_base) + ia + tasa + comision

    return {
        "vendidas": vendidas,
        "porcentaje": int(Decimal(vendidas * 100) / emitidas) if emitidas else 0,
        "ingresos": _eur(ingresos),
        "tasa": tasa,
        "comision": comision,
        "ingreso_cuenta": ia,
        "costes": _eur(costes),
        "resultado": _eur(ingresos - costes),
    }


def umbral(cfg, gastos_base, emitidas=None, precio=None):
    """
    Participaciones que hay que vender para no perder dinero.

    n = (fijos + ingreso a cuenta + tasa) / (precio × (1 − comisión))
    """
    precio = Decimal(precio if precio is not None else cfg.precio)
    emitidas = int(emitidas if emitidas is not None else cfg.emitidas)
    if precio <= 0 or emitidas <= 0:
        return 0

    tasa = precio * emitidas * cfg.tasa
    ia = ingreso_a_cuenta(cfg.valor_premio, cfg.asume_ingreso_cuenta)
    denominador = precio * (Decimal("1") - cfg.comision)
    if denominador <= 0:
        return emitidas
    return min(emitidas, _techo((Decimal(gastos_base) + ia + tasa) / denominador))


def escenarios(cfg, gastos_base):
    """
    Los tres escenarios que importan, del peor al mejor.

    El de cancelación es el que nadie calcula y el que de verdad acota el
    riesgo: si no se alcanza el mínimo se reintegra todo, se pierden los gastos
    ya incurridos, **pero el inmueble no se entrega y sigue en balance**. La
    pérdida no es el coste total, ni de lejos.
    """
    gastos_base = Decimal(gastos_base)
    n = umbral(cfg, gastos_base)
    minimo = cfg.minimo or n

    filas = [
        {
            "nombre": "Se cancela por no alcanzar el mínimo",
            "detalle": "Se reintegra el importe a todos los participantes. Se "
            "pierden los gastos ya incurridos, pero el inmueble no se entrega "
            "y permanece en balance.",
            "tono": "danger",
            **evaluar(cfg, 0, gastos_base),
        },
        {
            "nombre": "Se celebra vendiendo solo el mínimo",
            "detalle": "El peor escenario en el que el sorteo sí se celebra y "
            "hay que entregar el inmueble.",
            "tono": "warning",
            **evaluar(cfg, minimo, gastos_base),
        },
        {
            "nombre": "Se agotan las participaciones",
            "detalle": "Escenario objetivo.",
            "tono": "success",
            **evaluar(cfg, cfg.emitidas, gastos_base),
        },
    ]

    # En la cancelación no se entrega el inmueble: su coste no es una pérdida.
    cancelacion = filas[0]
    cancelacion["resultado"] = _eur(
        -(gastos_base - cfg.valor_premio) - cancelacion["tasa"]
    )
    cancelacion["nota_resultado"] = (
        "Sin contar el inmueble, que se conserva. Pendiente de confirmar con "
        "la gestoría si la tasa ya anticipada es recuperable."
    )

    return {
        "filas": filas,
        "umbral": n,
        "umbral_porcentaje": (
            int(Decimal(n * 100) / cfg.emitidas) if cfg.emitidas else 0
        ),
        "compradores": _techo(Decimal(n) / PARTICIPACIONES_POR_COMPRADOR),
        "suelo_estructural": int(
            (cfg.tasa / (Decimal("1") - cfg.comision)) * CIEN
        ),
        "minimo": minimo,
    }


def recomendar(cfg, gastos_base, margen_objetivo, precios=None):
    """
    Para cada precio candidato, cuántas participaciones emitir para alcanzar el
    margen objetivo, y cuántas hay que colocar para no perder.

    Se ordena por papeletas a vender, no por margen: entre dos combinaciones que
    dan lo mismo, la buena es la que exige convencer a menos gente.
    """
    gastos_base = Decimal(gastos_base)
    precios = precios or [Decimal(x) for x in ("5", "10", "15", "20", "25", "50")]
    margen = Decimal(margen_objetivo)
    ia = ingreso_a_cuenta(cfg.valor_premio, cfg.asume_ingreso_cuenta)
    denominador = Decimal("1") - cfg.tasa - cfg.comision

    opciones = []
    for precio in precios:
        precio = Decimal(precio)
        if denominador <= 0 or precio <= 0:
            continue

        bruto = (gastos_base + ia + margen) / denominador
        emitidas = _techo(bruto / precio)
        if emitidas < 1:
            continue

        n = umbral(cfg, gastos_base, emitidas=emitidas, precio=precio)
        opciones.append(
            {
                "precio": _eur(precio),
                "emitidas": emitidas,
                "bruto": _eur(Decimal(emitidas) * precio),
                "umbral": n,
                "umbral_porcentaje": int(Decimal(n * 100) / emitidas),
                "compradores": _techo(Decimal(n) / PARTICIPACIONES_POR_COMPRADOR),
                "resultado_pleno": evaluar(
                    cfg, emitidas, gastos_base, emitidas=emitidas, precio=precio
                )["resultado"],
                "probabilidad": "1 entre {}".format(emitidas),
            }
        )

    opciones.sort(key=lambda o: o["umbral"])
    return opciones
