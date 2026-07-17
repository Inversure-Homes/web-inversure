import sys
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

from django.test import RequestFactory

from core import views as core_views


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
