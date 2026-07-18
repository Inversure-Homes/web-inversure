from __future__ import annotations

from copy import deepcopy
from decimal import Decimal

from core.views import _build_inversor_context


def test_build_inversor_context_preserves_precedence_and_inputs():
    inv_calc = {
        "existing": "calc",
        "from_snap": "calc",
        "empty_text": "",
        "none_value": None,
        "zero_int": 0,
        "zero_decimal": Decimal("0"),
        "false_value": False,
        "keep_list": [],
    }
    inv_snap = {
        "from_snap": "snap",
        "missing": "snap",
        "empty_text": "snap-text",
        "none_value": "snap-none",
        "snap_empty_text": "",
        "snap_empty_list": [],
        "zero_int": 10,
        "zero_decimal": Decimal("9"),
        "false_value": True,
        "keep_list": [1],
    }

    original_calc = deepcopy(inv_calc)
    original_snap = deepcopy(inv_snap)

    result = _build_inversor_context(inv_calc, inv_snap)

    assert result == {
        "existing": "calc",
        "from_snap": "calc",
        "empty_text": "snap-text",
        "none_value": "snap-none",
        "snap_empty_text": "",
        "snap_empty_list": [],
        "zero_int": 0,
        "zero_decimal": Decimal("0"),
        "false_value": False,
        "keep_list": [],
        "missing": "snap",
    }
    assert result is not inv_calc
    assert inv_calc == original_calc
    assert inv_snap == original_snap
