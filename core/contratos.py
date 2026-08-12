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


def calendario_liquidaciones(firma: date, meses: int, cada: int = 2):
    """
    Los vencimientos de intereses, uno por período.

    Se calculan desde la firma en vez de escribirse a mano: el contrato original
    los traía tecleados, y ahí es donde se cuelan los errores de año.
    """
    periodos = []
    numero = 1
    transcurridos = cada
    while transcurridos <= meses:
        periodos.append(
            {
                "numero": numero,
                "desde_mes": transcurridos - cada + 1,
                "hasta_mes": transcurridos,
                "vencimiento": sumar_meses(firma, transcurridos),
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
