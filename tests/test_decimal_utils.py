from __future__ import annotations

import ast
import inspect
from decimal import Decimal, getcontext

import pytest

from core import decimal_utils
from core.decimal_utils import (
    HUNDRED,
    MONEY_QUANTUM,
    ONE,
    PERCENTAGE_QUANTUM,
    ZERO,
    DecimalConversionError,
    percentage_to_ratio,
    quantize_money,
    quantize_percentage,
    ratio_to_percentage,
    to_decimal,
)

pytestmark = pytest.mark.unit


def test_public_constants_are_decimal_instances():
    assert ZERO == Decimal("0")
    assert ONE == Decimal("1")
    assert HUNDRED == Decimal("100")
    assert MONEY_QUANTUM == Decimal("0.01")
    assert PERCENTAGE_QUANTUM == Decimal("0.0001")


def test_to_decimal_preserves_decimal_identity():
    value = Decimal("123.4500")

    result = to_decimal(value)

    assert result is value


@pytest.mark.parametrize(
    ("value", "expected"),
    [
        (7, Decimal("7")),
        (-7, Decimal("-7")),
        (0, Decimal("0")),
        ("  +12.3400  ", Decimal("12.3400")),
        ("-7.5", Decimal("-7.5")),
        ("1e3", Decimal("1E+3")),
        (0.1, Decimal("0.1")),
        (12345678901234567890, Decimal("12345678901234567890")),
    ],
)
def test_to_decimal_supports_common_numeric_inputs(value, expected):
    assert to_decimal(value) == expected


@pytest.mark.parametrize("value", [None, "", "   "])
def test_to_decimal_rejects_missing_values_without_default(value):
    with pytest.raises(DecimalConversionError):
        to_decimal(value)


def test_to_decimal_uses_explicit_default_for_missing_values():
    assert to_decimal(None, default=Decimal("7.5")) == Decimal("7.5")
    assert to_decimal("   ", default="8.25") == Decimal("8.25")


@pytest.mark.parametrize("value", ["bad-value", object(), True, False, float("nan"), float("inf")])
def test_to_decimal_rejects_invalid_values(value):
    with pytest.raises(DecimalConversionError):
        to_decimal(value)


def test_to_decimal_rejects_invalid_value_even_with_default_when_default_is_invalid():
    with pytest.raises(DecimalConversionError):
        to_decimal("bad", default="also-bad")


def test_quantize_money_rounds_half_up_to_two_decimals():
    assert quantize_money(Decimal("10")) == Decimal("10.00")
    assert quantize_money("1.234") == Decimal("1.23")
    assert quantize_money("1.235") == Decimal("1.24")
    assert quantize_money(Decimal("-1.235")) == Decimal("-1.24")
    assert quantize_money(0) == Decimal("0.00")
    assert isinstance(quantize_money(1.2), Decimal)


def test_quantize_percentage_uses_explicit_four_decimal_precision():
    assert quantize_percentage(Decimal("12")) == Decimal("12.0000")
    assert quantize_percentage("12.345678") == Decimal("12.3457")
    assert quantize_percentage("-12.34565") == Decimal("-12.3457")
    assert quantize_percentage("0.00005") == Decimal("0.0001")
    assert quantize_percentage(0) == Decimal("0.0000")


@pytest.mark.parametrize(
    ("percentage", "expected_ratio"),
    [
        (25, Decimal("0.25")),
        (0, Decimal("0")),
        (100, Decimal("1")),
        (-25, Decimal("-0.25")),
        (250, Decimal("2.5")),
    ],
)
def test_percentage_to_ratio_converts_percentages_to_ratios(percentage, expected_ratio):
    assert percentage_to_ratio(percentage) == expected_ratio


@pytest.mark.parametrize(
    ("ratio", "expected_percentage"),
    [
        (Decimal("0.25"), Decimal("25")),
        (0, Decimal("0")),
        (-0.25, Decimal("-25")),
        (Decimal("2.5"), Decimal("250")),
    ],
)
def test_ratio_to_percentage_converts_ratios_to_percentages(ratio, expected_percentage):
    assert ratio_to_percentage(ratio) == expected_percentage


def test_percentage_and_ratio_round_trip_for_representable_values():
    percentage = Decimal("12.5")
    ratio = percentage_to_ratio(percentage)

    assert ratio == Decimal("0.125")
    assert ratio_to_percentage(ratio) == percentage


def test_percentage_and_ratio_helpers_accept_explicit_defaults():
    assert percentage_to_ratio(None, default=Decimal("15")) == Decimal("0.15")
    assert ratio_to_percentage(None, default=Decimal("0.15")) == Decimal("15")


def test_decimal_context_is_not_modified():
    context = getcontext()
    before = (
        context.prec,
        context.rounding,
        context.Emax,
        context.Emin,
        context.capitals,
        context.clamp,
        context.traps.copy(),
    )

    quantize_money("1.235")
    quantize_percentage("12.345678")
    percentage_to_ratio("12.5")
    ratio_to_percentage("0.125")

    after = (
        context.prec,
        context.rounding,
        context.Emax,
        context.Emin,
        context.capitals,
        context.clamp,
        context.traps.copy(),
    )

    assert after == before


def test_module_remains_pure_and_does_not_import_infrastructure_layers():
    source = inspect.getsource(decimal_utils)
    tree = ast.parse(source)

    imported_modules: set[str] = set()
    for node in tree.body:
        if isinstance(node, ast.Import):
            imported_modules.update(alias.name.split(".")[0] for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module:
            imported_modules.add(node.module.split(".")[0])

    assert imported_modules == {"decimal", "typing", "__future__"}
