import sys
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

import pytest
from django.http import HttpResponse
from django.test import RequestFactory

from core import views as core_views

from .factories import EstudioFactory

pytestmark = pytest.mark.django_db


def test_build_presentacion_pdf_uses_weasyprint_mock(monkeypatch):
    request = RequestFactory().get("/")
    captured = {}

    class _FakeHTML:
        def __init__(self, string, base_url=None):
            captured["string"] = string
            captured["base_url"] = base_url

        def write_pdf(self):
            return b"pdf-bytes"

    monkeypatch.setitem(sys.modules, "weasyprint", SimpleNamespace(HTML=_FakeHTML))

    with patch.object(core_views, "_build_presentacion_html", return_value="<html></html>") as mock_html:
        pdf = core_views._build_presentacion_pdf(request, {"titulo": "Demo"})

    assert pdf == b"pdf-bytes"
    mock_html.assert_called_once_with(request, {"titulo": "Demo"})
    assert captured["base_url"] == "http://testserver/"


def test_ratio_metrics_are_not_rendered_as_currency_symbols():
    root = Path(__file__).resolve().parents[1]

    proyecto_template = (root / "core/templates/core/proyecto.html").read_text(encoding="utf-8")
    pdf_template = (root / "core/templates/core/pdf_estudio_rentabilidad.html").read_text(encoding="utf-8")

    assert 'data-decimals="2">{{ resultado.ratio_euro }}</span> €' not in proyecto_template
    assert "{{ snapshot.kpis.ratio_euro_beneficio|es_number }} €" not in pdf_template


def test_pdf_estudio_preview_rebuilds_metrics_from_study_payload():
    estudio = EstudioFactory(
        datos={
            "valor_adquisicion": 100000,
            "precio_transmision": 140000,
            "beneficio": 40000,
            "roi": 40.0,
            "comision_inversure_pct": 10,
            "impuesto_sociedades_pct": 25,
            "snapshot": {
                "inversor": {
                    "beneficio_neto": 22222,
                    "roi_neto": 22.22,
                    "beneficio_neto_tras_impuestos": 11111,
                    "roi_neto_tras_impuestos": 11.11,
                },
                "kpis": {"metricas": {"roi": 88.0, "beneficio": 88888}},
            },
            "kpis": {"metricas": {"beneficio": 99999}},
            "economico": {"beneficio_estimado": 77777},
        },
    )
    request = RequestFactory().get("/")
    captured = {}

    def _fake_render(request, template_name, context=None, *args, **kwargs):
        captured["template_name"] = template_name
        captured["context"] = context or {}
        return HttpResponse("captured")

    with patch.object(core_views, "render", side_effect=_fake_render):
        response = core_views.pdf_estudio_preview(request, estudio.id)

    assert response.status_code == 200
    assert captured["template_name"] == "core/pdf_estudio_rentabilidad.html"
    metricas = captured["context"]["metricas"]
    inversor = captured["context"]["inversor"]
    snapshot = captured["context"]["snapshot"]

    assert metricas["valor_adquisicion"] == 100000.0
    assert metricas["beneficio"] == 40000.0
    assert metricas["roi"] == 40.0
    assert snapshot["kpis"]["metricas"]["roi"] == 40.0
    assert snapshot["economico"]["beneficio_estimado"] == 77777.0
    assert inversor["inversion_total"] == 100000.0
    assert inversor["comision_inversure_pct"] == 10.0
    assert inversor["comision_inversure_eur"] == 4000.0
    assert inversor["beneficio_neto"] == 36000.0
    # El PDF conserva el alias legacy `roi_neto` del payload del estudio.
    assert inversor["roi_neto"] == 40.0
    assert inversor["beneficio_neto_tras_impuestos"] == 27000.0
    assert inversor["roi_neto_tras_impuestos"] == 27.0


def test_pdf_estudio_preview_renders_real_template():
    estudio = EstudioFactory(
        datos={
            "valor_adquisicion": 100000,
            "precio_transmision": 140000,
            "beneficio": 40000,
            "roi": 40.0,
            "comision_inversure_pct": 10,
            "impuesto_sociedades_pct": 25,
            "snapshot": {
                "inversor": {
                    "beneficio_neto": 22222,
                    "roi_neto": 22.22,
                    "beneficio_neto_tras_impuestos": 11111,
                    "roi_neto_tras_impuestos": 11.11,
                },
                "kpis": {"metricas": {"roi": 88.0, "beneficio": 88888}},
            },
            "kpis": {"metricas": {"beneficio": 99999}},
            "economico": {"beneficio_estimado": 77777},
        },
    )
    request = RequestFactory().get("/")

    response = core_views.pdf_estudio_preview(request, estudio.id)

    assert response.status_code == 200
    assert "Informe de rentabilidad" in response.content.decode("utf-8")
