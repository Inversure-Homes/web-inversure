from __future__ import annotations

from decimal import Decimal, InvalidOperation, ROUND_HALF_UP, localcontext
from typing import Final

__all__ = [
    "DecimalConversionError",
    "HUNDRED",
    "MONEY_QUANTUM",
    "ONE",
    "PERCENTAGE_QUANTUM",
    "ZERO",
    "percentage_to_ratio",
    "quantize_money",
    "quantize_percentage",
    "ratio_to_percentage",
    "to_decimal",
]

ZERO: Final = Decimal("0")
ONE: Final = Decimal("1")
HUNDRED: Final = Decimal("100")
MONEY_QUANTUM: Final = Decimal("0.01")
PERCENTAGE_QUANTUM: Final = Decimal("0.0001")

_MISSING = object()


class DecimalConversionError(ValueError):
    """Raised when a value cannot be converted to a finite Decimal."""


def _coerce_decimal(value: object) -> Decimal:
    if isinstance(value, bool):
        raise DecimalConversionError("Boolean values are not valid Decimal inputs.")
    if isinstance(value, Decimal):
        if not value.is_finite():
            raise DecimalConversionError("Non-finite Decimal values are not supported.")
        return value
    if isinstance(value, int):
        return Decimal(value)
    if isinstance(value, float):
        candidate = Decimal(str(value))
    elif isinstance(value, str):
        text = value.strip()
        if not text:
            raise DecimalConversionError("Empty strings are not valid Decimal inputs.")
        try:
            candidate = Decimal(text)
        except InvalidOperation as exc:
            raise DecimalConversionError(f"Unsupported decimal string: {value!r}.") from exc
    else:
        raise DecimalConversionError(f"Unsupported value type: {type(value).__name__}.")

    if not candidate.is_finite():
        raise DecimalConversionError("Non-finite Decimal values are not supported.")
    return candidate


def to_decimal(value: object, *, default: object = _MISSING) -> Decimal:
    """Convert supported numeric-like inputs to a finite Decimal.

    Supported inputs are Decimal, int, float and str. Floats are converted
    through their string representation to avoid Decimal(float) artifacts.
    Boolean values are rejected explicitly.

    If *value* is missing, blank or invalid and *default* is provided, the
    default is converted with the same rules and returned instead.
    """

    try:
        if value is None:
            raise DecimalConversionError("None is not a valid Decimal input.")
        return _coerce_decimal(value)
    except (DecimalConversionError, InvalidOperation, TypeError, ValueError):
        if default is _MISSING:
            raise
        return _coerce_decimal(default)


def _quantize(value: object, quantum: Decimal) -> Decimal:
    decimal_value = to_decimal(value)
    with localcontext() as context:
        context.rounding = ROUND_HALF_UP
        return decimal_value.quantize(quantum)


def quantize_money(value: object) -> Decimal:
    """Round a value to two monetary decimals using HALF_UP semantics."""

    return _quantize(value, MONEY_QUANTUM)


def quantize_percentage(value: object) -> Decimal:
    """Round a percentage value to four decimals for internal financial use."""

    return _quantize(value, PERCENTAGE_QUANTUM)


def percentage_to_ratio(value: object, *, default: object = _MISSING) -> Decimal:
    """Convert a percentage value such as 25 into its ratio representation 0.25."""

    return to_decimal(value, default=default) / HUNDRED


def ratio_to_percentage(value: object, *, default: object = _MISSING) -> Decimal:
    """Convert a ratio value such as 0.25 into its percentage representation 25."""

    return to_decimal(value, default=default) * HUNDRED
