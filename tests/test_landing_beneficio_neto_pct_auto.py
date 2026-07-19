from __future__ import annotations

from copy import deepcopy

import pytest

from core.views import _build_landing_beneficio_neto_pct_auto


@pytest.mark.parametrize(
    "landing_config, roi_auto, expected",
    [
        (None, None, None),
        ({}, None, None),
        ({}, 1234.5, "1.234,50"),
        ({"beneficio_neto_pct": ""}, 12.345, "12,35"),
        ({"beneficio_neto_pct": 0}, -12.345, "-12,35"),
        ({"beneficio_neto_pct": "18"}, 12.34, None),
    ],
)
def test_build_landing_beneficio_neto_pct_auto_preserves_formatting_and_fallbacks(
    landing_config,
    roi_auto,
    expected,
):
    original = deepcopy(landing_config) if isinstance(landing_config, dict) else landing_config

    result = _build_landing_beneficio_neto_pct_auto(landing_config, roi_auto)

    assert result == expected
    if isinstance(landing_config, dict):
        assert landing_config == original


def test_build_landing_beneficio_neto_pct_auto_none_leaves_context_unchanged():
    ctx = {"landing_beneficio_neto_pct_auto": "previo", "otra_clave": "valor"}
    landing_beneficio_neto_pct_auto = _build_landing_beneficio_neto_pct_auto({}, None)
    if landing_beneficio_neto_pct_auto is not None:
        ctx["landing_beneficio_neto_pct_auto"] = landing_beneficio_neto_pct_auto

    assert landing_beneficio_neto_pct_auto is None
    assert ctx == {"landing_beneficio_neto_pct_auto": "previo", "otra_clave": "valor"}
