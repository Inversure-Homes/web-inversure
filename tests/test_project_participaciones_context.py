from __future__ import annotations

from decimal import Decimal
from types import SimpleNamespace

from core.views import _build_project_participaciones_context


def test_build_project_participaciones_context_uses_capital_objetivo_and_preserves_existing_values():
    participaciones = [
        SimpleNamespace(importe_invertido=Decimal("25"), porcentaje_participacion=None),
        SimpleNamespace(importe_invertido=Decimal("10"), porcentaje_participacion=Decimal("12.5")),
        SimpleNamespace(importe_invertido=Decimal("75"), porcentaje_participacion=None),
    ]

    result = _build_project_participaciones_context(
        participaciones,
        Decimal("100"),
        Decimal("80"),
    )

    assert result is participaciones
    assert [p.porcentaje_participacion for p in participaciones] == [
        Decimal("25"),
        Decimal("12.5"),
        Decimal("75"),
    ]


def test_build_project_participaciones_context_uses_confirmed_total_when_capital_objetivo_is_zero():
    participaciones = [SimpleNamespace(importe_invertido=Decimal("20"), porcentaje_participacion=None)]

    assert _build_project_participaciones_context([], Decimal("100"), Decimal("80")) == []
    _build_project_participaciones_context(participaciones, Decimal("0"), Decimal("50"))

    assert participaciones[0].porcentaje_participacion == Decimal("40")
