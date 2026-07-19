from datetime import date

import pytest

from core.views import _build_project_plazo_context


@pytest.mark.parametrize(
    ("estado_lower", "fecha_reserva_calc", "expected_modo", "expected_hasta", "expected_dias"),
    [
        ("reservado", date(2026, 1, 10), "compra_a_reserva", "2026-01-10", 9),
        ("abierto", date(2026, 1, 10), "dias_desde_compra", "2026-01-20", 19),
    ],
)
def test_build_project_plazo_context_builds_expected_keys_for_closed_and_open_states(
    estado_lower,
    fecha_reserva_calc,
    expected_modo,
    expected_hasta,
    expected_dias,
):
    result = _build_project_plazo_context(
        date(2026, 1, 1),
        fecha_reserva_calc,
        estado_lower,
        hoy=date(2026, 1, 20),
    )

    assert result == {
        "plazo_compra_reserva_dias": expected_dias,
        "plazo_compra_reserva_desde": "2026-01-01",
        "plazo_compra_reserva_hasta": expected_hasta,
        "plazo_compra_reserva_modo": expected_modo,
    }


@pytest.mark.parametrize(
    ("fecha_compra_calc", "fecha_reserva_calc", "estado_lower", "hoy"),
    [
        (None, date(2026, 1, 10), "reservado", date(2026, 1, 20)),
        (date(2026, 1, 21), date(2026, 1, 10), "reservado", date(2026, 1, 20)),
    ],
)
def test_build_project_plazo_context_returns_empty_dict_without_valid_span(
    fecha_compra_calc,
    fecha_reserva_calc,
    estado_lower,
    hoy,
):
    assert (
        _build_project_plazo_context(
            fecha_compra_calc,
            fecha_reserva_calc,
            estado_lower,
            hoy=hoy,
        )
        == {}
    )
