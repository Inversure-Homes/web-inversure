"""
Aranceles de notaría y registro de la propiedad.

Son escalas por tramos fijadas por norma, así que se pueden calcular en lugar
de pedirlas a ojo. Lo que sale es el **arancel base**: la factura final suma
copias, folios, provisiones y el IVA, y aplica la reducción del 5 % del Real
Decreto-ley 8/2010. Por eso el resultado se multiplica por un factor que
aproxima la factura real, y por eso todos estos campos son editables: cuando
llegue la factura de verdad, se pone.
"""

from decimal import ROUND_HALF_UP, Decimal

# Arancel de los notarios, RD 1426/1989, documentos de cuantía.
# Cada tramo: (límite superior, tipo por mil sobre el exceso del tramo anterior)
TRAMOS_NOTARIA = [
    (Decimal("30050.60"), Decimal("4.5")),
    (Decimal("60101.21"), Decimal("1.5")),
    (Decimal("150253.03"), Decimal("1.0")),
    (Decimal("601012.10"), Decimal("0.5")),
    (Decimal("6010121.04"), Decimal("0.3")),
]
BASE_NOTARIA = Decimal("90.151815")

# Arancel de los registradores de la propiedad, RD 1427/1989, anexo I nº 2.
#
# NO CONTRASTADO con la misma solidez que el notarial: cuadra con la práctica
# habitual, pero conviene confirmarlo con la gestoría antes de darlo por bueno.
TRAMOS_REGISTRO = [
    (Decimal("30050.61"), Decimal("1.75")),
    (Decimal("60101.21"), Decimal("1.25")),
    (Decimal("150253.03"), Decimal("0.75")),
    (Decimal("601012.10"), Decimal("0.30")),
    (Decimal("99999999"), Decimal("0.20")),
]
BASE_REGISTRO = Decimal("24.040484")

MINIMO_TRAMO = Decimal("6010.12")

# La factura real ronda esto sobre el arancel base, por copias, folios y demás.
# Es una aproximación, no una regla.
FACTOR_FACTURA_NOTARIA = Decimal("1.8")
FACTOR_FACTURA_REGISTRO = Decimal("1.4")


def _escala(valor, tramos, base):
    valor = Decimal(valor or 0)
    if valor <= 0:
        return Decimal("0")
    if valor <= MINIMO_TRAMO:
        return base

    total = base
    anterior = MINIMO_TRAMO
    for limite, por_mil in tramos:
        if valor <= anterior:
            break
        tramo = min(valor, limite) - anterior
        total += tramo * por_mil / Decimal("1000")
        anterior = limite
    return total


def _eur(valor):
    return Decimal(valor).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)


def notaria(valor):
    """Arancel notarial aproximado a factura, para una compraventa."""
    return _eur(_escala(valor, TRAMOS_NOTARIA, BASE_NOTARIA) * FACTOR_FACTURA_NOTARIA)


def registro(valor):
    """Arancel registral aproximado a factura, para una inscripción."""
    return _eur(_escala(valor, TRAMOS_REGISTRO, BASE_REGISTRO) * FACTOR_FACTURA_REGISTRO)
