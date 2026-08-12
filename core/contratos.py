"""
Contrato de préstamo para los inversores de Conciertos.

El contrato es siempre el mismo texto; lo que cambia son las partes, el importe
y las fechas. Aquí vive lo que hay que calcular para rellenarlo: el calendario
de liquidaciones, el vencimiento y el importe en letra, que en un documento con
efectos jurídicos no puede escribirse a ojo.
"""

from datetime import date
from decimal import ROUND_HALF_UP, Decimal

# --- Importe en letra ------------------------------------------------------
#
# Un contrato pone la cantidad en letra y en cifra, y si discrepan manda la
# letra. Escribirla a mano en cada contrato es pedir una errata cara.

UNIDADES = (
    "", "uno", "dos", "tres", "cuatro", "cinco", "seis", "siete", "ocho", "nueve",
    "diez", "once", "doce", "trece", "catorce", "quince", "dieciséis", "diecisiete",
    "dieciocho", "diecinueve", "veinte", "veintiuno", "veintidós", "veintitrés",
    "veinticuatro", "veinticinco", "veintiséis", "veintisiete", "veintiocho", "veintinueve",
)
DECENAS = ("", "", "", "treinta", "cuarenta", "cincuenta", "sesenta", "setenta", "ochenta", "noventa")
CENTENAS = (
    "", "ciento", "doscientos", "trescientos", "cuatrocientos", "quinientos",
    "seiscientos", "setecientos", "ochocientos", "novecientos",
)


def _hasta_999(n: int) -> str:
    if n == 0:
        return ""
    if n == 100:
        return "cien"
    centena, resto = divmod(n, 100)
    partes = []
    if centena:
        partes.append(CENTENAS[centena])
    if resto:
        if resto < 30:
            partes.append(UNIDADES[resto])
        else:
            decena, unidad = divmod(resto, 10)
            partes.append(DECENAS[decena] + (" y " + UNIDADES[unidad] if unidad else ""))
    return " ".join(partes)


def _apocopado(texto: str) -> str:
    """«uno» → «un», «veintiuno» → «veintiún», delante del sustantivo."""
    if texto.endswith("veintiuno"):
        return texto[: -len("veintiuno")] + "veintiún"
    if texto == "uno" or texto.endswith(" uno"):
        return texto[:-3] + "un"
    return texto


def importe_en_letra(importe) -> str:
    """
    «50000» → «CINCUENTA MIL EUROS». Con céntimos si los hay.

    En mayúsculas porque así aparece en el contrato, y porque destaca sobre la
    cifra entre paréntesis.
    """
    cantidad = Decimal(importe or 0).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
    entera = int(cantidad)
    centimos = int((cantidad - entera) * 100)

    if entera == 0:
        texto = "cero"
        de = ""
    else:
        millones, resto = divmod(entera, 1_000_000)
        miles, unidades = divmod(resto, 1000)
        partes = []
        if millones:
            partes.append("un millón" if millones == 1 else _hasta_999(millones) + " millones")
        if miles:
            partes.append("mil" if miles == 1 else _apocopado(_hasta_999(miles)) + " mil")
        if unidades:
            partes.append(_hasta_999(unidades))
        texto = " ".join(partes)
        # «un millón DE euros», pero «un millón trescientos mil euros».
        de = " de" if millones and not resto else ""

    # Delante de un sustantivo masculino se apocopa: un euro, veintiún euros,
    # treinta y un euros. En un contrato esto se lee, y se nota.
    texto = _apocopado(texto)
    texto += de
    texto += " euro" if entera == 1 else " euros"
    if centimos:
        texto += " con {} céntimo{}".format(_apocopado(_hasta_999(centimos)), "" if centimos == 1 else "s")
    return texto.upper()


# --- Fechas ----------------------------------------------------------------


def sumar_meses(desde: date, meses: int) -> date:
    """Misma fecha N meses después, ajustando los meses cortos."""
    import calendar

    total = desde.month - 1 + meses
    anio = desde.year + total // 12
    mes = total % 12 + 1
    dia = min(desde.day, calendar.monthrange(anio, mes)[1])
    return date(anio, mes, dia)


def primero_de_mes_siguiente(fecha: date) -> date:
    """
    Redondea al día 1 sin quedarse corto. Si ya es día 1, se queda.

    Es la regla que Inversure venía usando a mano: un contrato firmado el 23 de
    junio liquidaba el 1 de septiembre, no el 23 de agosto. Pagar siempre en día
    1 cuadra con la tesorería; el aniversario de la firma no le importa a nadie.
    """
    if fecha.day == 1:
        return fecha
    if fecha.month == 12:
        return date(fecha.year + 1, 1, 1)
    return date(fecha.year, fecha.month + 1, 1)


def calendario_liquidaciones(firma: date, meses: int, cada: int = 2, en_dia_uno: bool = True):
    """
    Los vencimientos de intereses, uno por período.

    Se calculan desde la firma en vez de escribirse a mano: el contrato original
    los traía tecleados, y ahí es donde se cuelan los errores de año.

    Por defecto se pagan el día 1, que es como se venía haciendo. Con
    `en_dia_uno=False` se paga en el aniversario de la firma.
    """
    periodos = []
    numero = 1
    transcurridos = cada
    while transcurridos <= meses:
        fin = sumar_meses(firma, transcurridos)
        periodos.append(
            {
                "numero": numero,
                "desde_mes": transcurridos - cada + 1,
                "hasta_mes": transcurridos,
                "vencimiento": primero_de_mes_siguiente(fin) if en_dia_uno else fin,
            }
        )
        numero += 1
        transcurridos += cada
    return periodos


def condiciones(participacion, firma: date | None = None) -> dict:
    """
    Todo lo que el contrato necesita calcular a partir de la participación.

    El interés se expresa por período de dos meses, como en el contrato firmado.
    Se muestra también el total del año porque un 5 % bimensual son seis
    períodos, y conviene que la cifra anual esté a la vista y no haya que
    deducirla.
    """
    firma = firma or participacion.contrato_fecha or participacion.fecha_aportacion or date.today()
    meses = int(participacion.contrato_meses or 12)
    interes = Decimal(participacion.contrato_interes_bimensual or 0)
    capital = Decimal(participacion.importe_invertido or 0)

    periodos = calendario_liquidaciones(firma, meses)
    por_periodo = (capital * interes / 100).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)

    return {
        "firma": firma,
        "vencimiento": sumar_meses(firma, meses),
        "meses": meses,
        "capital": capital,
        "capital_letra": importe_en_letra(capital),
        "interes_periodo": interes,
        "interes_total_pct": interes * len(periodos),
        "importe_por_periodo": por_periodo,
        "intereses_totales": por_periodo * len(periodos),
        "periodos": periodos,
    }


# --- Cuenta en participación ----------------------------------------------
#
# El contrato de los proyectos inmobiliarios. No es un préstamo: la cláusula
# 1.2 lo niega expresamente, y de esa distinción dependen el tratamiento fiscal
# y que la pérdida del partícipe quede limitada a su aportación.

MESES_NEGOCIO = 6
PARTICIPACION_MINIMA = Decimal("10000")


def condiciones_cuenta_participe(participacion, firma: date | None = None) -> dict:
    """Lo que el contrato de cuenta partícipe necesita del proyecto y de la participación."""
    proyecto = participacion.proyecto
    firma = firma or participacion.contrato_fecha or participacion.fecha_aportacion or date.today()
    meses = int(participacion.contrato_meses or MESES_NEGOCIO)

    aportacion = Decimal(participacion.importe_invertido or 0)
    adquisicion = Decimal(
        getattr(proyecto, "precio_compra_inmueble", None) or getattr(proyecto, "precio_propiedad", None) or 0
    )
    venta = Decimal(getattr(proyecto, "precio_venta_estimado", None) or 0)

    # El concepto de la transferencia identifica al partícipe y al inmueble: es
    # lo que permite conciliar el ingreso cuando entran varios el mismo día.
    concepto = 'Aportación cuenta partícipe "{}" + {}'.format(
        participacion.cliente.nombre or "", (proyecto.direccion or proyecto.nombre or "").strip()
    )

    return {
        "fecha": firma,
        "meses": meses,
        "vencimiento": sumar_meses(firma, meses),
        "aportacion": aportacion,
        "aportacion_letra": importe_en_letra(aportacion),
        "porcentaje": Decimal(participacion.porcentaje_participacion or 0),
        "valor_adquisicion": adquisicion,
        "adquisicion_letra": importe_en_letra(adquisicion),
        "precio_venta": venta,
        "participacion_minima": PARTICIPACION_MINIMA,
        "minimo_letra": importe_en_letra(PARTICIPACION_MINIMA),
        "concepto_transferencia": concepto,
    }


# --- Baja del inversor -----------------------------------------------------
#
# Ni el préstamo ni la cuenta en participación prevén que el inversor salga
# antes de tiempo: el préstamo solo deja amortizar anticipadamente a la
# prestataria, y la cuenta en participación dura lo que dure el negocio. La
# salida no es un derecho que se ejerza, sino un acuerdo que firman los dos.

DIAS_PAGO_RESCISION = 15


def intereses_devengados(participacion, hasta: date) -> Decimal:
    """
    Lo devengado por un préstamo hasta la fecha de salida.

    Se cuentan los períodos bimensuales completos: el contrato liquida por
    períodos vencidos, no día a día, y cobrar medio período no está pactado.
    """
    firma = participacion.contrato_fecha or participacion.fecha_aportacion
    if not firma or hasta < firma:
        return Decimal("0")

    meses = (hasta.year - firma.year) * 12 + (hasta.month - firma.month)
    if hasta.day < firma.day:
        meses -= 1
    periodos = max(0, min(int(meses // 2), int(participacion.contrato_meses or 12) // 2))

    capital = Decimal(participacion.importe_invertido or 0)
    interes = Decimal(participacion.contrato_interes_bimensual or 0)
    return (capital * interes / 100 * periodos).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)


def condiciones_baja(participacion, fecha: date | None = None, rendimiento=None, motivo: str = "") -> dict:
    """Lo que el acuerdo de resolución necesita saber."""
    fecha = fecha or participacion.fecha_baja or date.today()
    aportacion = Decimal(participacion.importe_invertido or 0)

    if rendimiento is None:
        # En un préstamo lo devengado se calcula; en una cuenta en
        # participación depende del resultado del negocio, que no se conoce
        # hasta cerrarlo, así que se deja a cero y se pone a mano si procede.
        es_prestamo = bool(participacion.contrato_interes_bimensual) and _es_conciertos(participacion.proyecto)
        rendimiento = intereses_devengados(participacion, fecha) if es_prestamo else Decimal("0")

    rendimiento = Decimal(rendimiento or 0)
    total = aportacion + rendimiento

    return {
        "fecha": fecha,
        "contrato_fecha": participacion.contrato_fecha or participacion.fecha_aportacion,
        "aportacion": aportacion,
        "aportacion_letra": importe_en_letra(aportacion),
        "rendimiento": rendimiento,
        "total": total,
        "total_letra": importe_en_letra(total),
        "dias_pago": DIAS_PAGO_RESCISION,
        "motivo": motivo or participacion.motivo_baja or "",
    }


def _es_conciertos(proyecto) -> bool:
    extra = getattr(proyecto, "extra", None) or {}
    tipo = (extra.get("tipo") or "").strip().lower() if isinstance(extra, dict) else ""
    return tipo == "conciertos" or (proyecto.nombre or "").strip().lower() == "conciertos"
