from __future__ import annotations

from copy import deepcopy

import pytest

from core.views import _build_estado_inicial_context


@pytest.mark.parametrize(
    "source, expected_kind",
    [
        ({"snapshot": {"estado": "snap"}, "estado": "outer"}, "snapshot"),
        ({"snapshot": [1, 2, 3], "estado": "outer"}, "snapshot"),
        ({"snapshot": "snapshot-texto", "estado": "outer"}, "snapshot"),
        ({"snapshot": True, "estado": "outer"}, "snapshot"),
        ({"snapshot": {}, "estado": "outer"}, "source"),
        ({"snapshot": None, "estado": "outer"}, "source"),
        ({"snapshot": False, "estado": "outer"}, "source"),
        ({"estado": "outer"}, "source"),
    ],
)
def test_build_estado_inicial_context_simulador_preserves_current_selection(source, expected_kind):
    original = deepcopy(source)

    result = _build_estado_inicial_context(source)

    if expected_kind == "snapshot":
        assert result is source["snapshot"]
    else:
        assert result is source

    assert source == original


@pytest.mark.parametrize(
    "source, expected_kind",
    [
        ({"snapshot": {"estado": "snap"}, "estado": "outer"}, "snapshot"),
        ({"snapshot": {}, "estado": "outer"}, "snapshot"),
        ({"snapshot": [1, 2, 3], "estado": "outer"}, "source"),
        ({"snapshot": "snapshot-texto", "estado": "outer"}, "source"),
        ({"snapshot": True, "estado": "outer"}, "source"),
        ({"snapshot": None, "estado": "outer"}, "source"),
        ({"snapshot": False, "estado": "outer"}, "source"),
        ({"estado": "outer"}, "source"),
        ({}, "empty"),
    ],
)
def test_build_estado_inicial_context_proyecto_preserves_current_selection(source, expected_kind):
    original = deepcopy(source)

    result = _build_estado_inicial_context(source, nested_snapshot_only_if_dict=True)

    if expected_kind == "snapshot":
        assert result is source["snapshot"]
    elif expected_kind == "source":
        assert result is source
    else:
        assert result == {}

    assert source == original


@pytest.mark.parametrize("source", [None, "abc", [1, 2], False, 0])
def test_build_estado_inicial_context_invalid_source_falls_back_to_empty_dict(source):
    assert _build_estado_inicial_context(source) == {}
    assert _build_estado_inicial_context(source, nested_snapshot_only_if_dict=True) == {}
