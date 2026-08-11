from __future__ import annotations

from datetime import date
from decimal import Decimal
from unittest.mock import patch

import pytest
from django.http import HttpResponse
from django.urls import reverse

from core import views as core_views
from core.models import GastoProyecto, IngresoProyecto

from .factories import ProyectoFactory

pytestmark = pytest.mark.django_db


def _fake_render(request, template_name, context=None, *args, **kwargs):
    _fake_render.captured = {
        "template_name": template_name,
        "context": context or {},
    }
    return HttpResponse("captured")


def test_lista_proyectos_calls_resultado_helper_once_for_one_project(verified_client):
    project = ProyectoFactory(nombre="Proyecto reutilización", estado="captacion")
    GastoProyecto.objects.create(
        proyecto=project,
        fecha=date(2026, 1, 1),
        categoria="adquisicion",
        concepto="Compraventa inmueble",
        importe=Decimal("100000.00"),
        importe_estimado=Decimal("100000.00"),
        importe_real=Decimal("100000.00"),
        estado="confirmado",
        imputable_inversores=True,
        pagado=True,
    )
    IngresoProyecto.objects.create(
        proyecto=project,
        fecha=date(2026, 6, 1),
        tipo="venta",
        concepto="Venta final",
        importe=Decimal("140000.00"),
        importe_estimado=Decimal("140000.00"),
        importe_real=Decimal("140000.00"),
        estado="confirmado",
        imputable_inversores=True,
        pagado=True,
    )

    with (
        patch("core.views.render", side_effect=_fake_render),
        patch("core.views._resultado_desde_memoria", wraps=core_views._resultado_desde_memoria) as spy,
    ):
        response = verified_client.get(reverse("core:lista_proyectos"))

    assert response.status_code == 200
    assert spy.call_count == 1
    assert [call.args[0].id for call in spy.call_args_list] == [project.id]

    captured = _fake_render.captured
    assert captured["template_name"] == "core/lista_proyectos.html"

    proyectos = list(captured["context"]["proyectos"])
    assert len(proyectos) == 1

    proyecto_ctx = proyectos[0]
    assert proyecto_ctx.id == project.id
    assert proyecto_ctx.capital_objetivo == pytest.approx(100000.0)
    assert proyecto_ctx.roi == pytest.approx(40.0)


def test_lista_proyectos_preserves_roi_when_capital_objective_derivation_fails(verified_client):
    class _ResultadoConRoi:
        def get(self, key, default=None):
            if key == "roi":
                return 40.0
            raise RuntimeError("capital objetivo failed")

    project = ProyectoFactory(nombre="Proyecto resiliente", estado="captacion")
    GastoProyecto.objects.create(
        proyecto=project,
        fecha=date(2026, 1, 1),
        categoria="adquisicion",
        concepto="Compraventa inmueble",
        importe=Decimal("100000.00"),
        importe_estimado=Decimal("100000.00"),
        importe_real=Decimal("100000.00"),
        estado="confirmado",
        imputable_inversores=True,
        pagado=True,
    )
    IngresoProyecto.objects.create(
        proyecto=project,
        fecha=date(2026, 6, 1),
        tipo="venta",
        concepto="Venta final",
        importe=Decimal("140000.00"),
        importe_estimado=Decimal("140000.00"),
        importe_real=Decimal("140000.00"),
        estado="confirmado",
        imputable_inversores=True,
        pagado=True,
    )

    with (
        patch("core.views.render", side_effect=_fake_render),
        patch("core.views._resultado_desde_memoria", return_value=_ResultadoConRoi()) as spy,
    ):
        response = verified_client.get(reverse("core:lista_proyectos"))

    assert response.status_code == 200
    assert spy.call_count == 1
    assert [call.args[0].id for call in spy.call_args_list] == [project.id]

    captured = _fake_render.captured
    assert captured["template_name"] == "core/lista_proyectos.html"

    proyectos = list(captured["context"]["proyectos"])
    assert len(proyectos) == 1

    proyecto_ctx = proyectos[0]
    assert proyecto_ctx.id == project.id
    assert proyecto_ctx.capital_objetivo == pytest.approx(0.0)
    assert proyecto_ctx.roi == pytest.approx(40.0)
