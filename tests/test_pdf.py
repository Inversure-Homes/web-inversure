import sys
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

import pytest
from django.contrib.messages.storage.fallback import FallbackStorage
from django.contrib.sessions.middleware import SessionMiddleware
from django.http import HttpResponse
from django.test import RequestFactory

from core import views as core_views

from .factories import EstudioFactory, UserFactory

pytestmark = pytest.mark.django_db


def test_build_presentacion_pdf_uses_weasyprint_mock(monkeypatch):
    request = RequestFactory().get("/")
    captured = {}

    class _FakeHTML:
        def __init__(self, string, base_url=None):
            captured["string"] = string
            captured["base_url"] = base_url

        def write_pdf(self, **kwargs):
            # `**kwargs` porque el real recibe `font_config`, que se comparte
            # para no destruir el font map de Pango en cada PDF.
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
    request.user = UserFactory(is_superuser=True, is_staff=True)
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
    request = RequestFactory().get("/", {"html": "1"})
    request.user = UserFactory(is_superuser=True, is_staff=True)

    response = core_views.pdf_estudio_preview(request, estudio.id)

    assert response.status_code == 200
    assert "Informe de rentabilidad" in response.content.decode("utf-8")


def test_pdf_estudio_preview_devuelve_un_pdf_de_verdad():
    """Sin `?html=1` sale un PDF, no HTML que el navegador tenga que imprimir."""
    estudio = EstudioFactory(datos={"valor_adquisicion": 100000, "precio_transmision": 140000})
    request = RequestFactory().get("/")
    request.user = UserFactory(is_superuser=True, is_staff=True)

    response = core_views.pdf_estudio_preview(request, estudio.id)

    assert response["Content-Type"] == "application/pdf"
    assert response.content[:5] == b"%PDF-"


def test_pdf_estudio_preview_exige_permiso():
    estudio = EstudioFactory(datos={"valor_adquisicion": 100000})
    request = RequestFactory().get("/")
    request.user = UserFactory()
    SessionMiddleware(lambda r: None).process_request(request)
    request._messages = FallbackStorage(request)

    response = core_views.pdf_estudio_preview(request, estudio.id)

    assert response.status_code == 302


def test_pdf_memoria_economica_devuelve_un_pdf_de_verdad(db):
    from core.models import Proyecto

    proyecto = Proyecto.objects.create(nombre="COIN")
    request = RequestFactory().get("/")
    request.user = UserFactory(is_superuser=True, is_staff=True)

    response = core_views.pdf_memoria_economica(request, proyecto.id)

    assert response["Content-Type"] == "application/pdf"
    assert response.content[:5] == b"%PDF-"
    assert "memoria-economica-coin.pdf" in response["Content-Disposition"]


def test_pdf_memoria_economica_sigue_exponiendo_el_contexto():
    """
    La auditoría de métricas y varias pruebas capturan el contexto
    interceptando `core.views.render`. Si el informe dejara de pasar por ahí,
    esas comprobaciones se quedarían ciegas sin que fallara nada.
    """
    from core.models import Proyecto

    proyecto = Proyecto.objects.create(nombre="COIN")
    request = RequestFactory().get("/")
    request.user = UserFactory(is_superuser=True, is_staff=True)
    captured = {}

    def _fake_render(request, template_name, context=None, *args, **kwargs):
        captured["template_name"] = template_name
        captured["context"] = context or {}
        return HttpResponse("captured")

    with patch.object(core_views, "render", side_effect=_fake_render):
        core_views.pdf_memoria_economica(request, proyecto.id)

    assert captured["template_name"] == "core/pdf_memoria_economica.html"
    assert "resumen" in captured["context"]


def test_pdf_memoria_economica_exige_permiso():
    from core.models import Proyecto

    proyecto = Proyecto.objects.create(nombre="COIN")
    request = RequestFactory().get("/")
    request.user = UserFactory()
    SessionMiddleware(lambda r: None).process_request(request)
    request._messages = FallbackStorage(request)

    response = core_views.pdf_memoria_economica(request, proyecto.id)

    assert response.status_code == 302


def test_los_informes_de_core_no_piden_el_logo_por_url():
    """
    WeasyPrint no es un navegador: un logo por URL le obliga a salir a la red y
    lo deja en blanco si no llega. Va incrustado como data URI.
    """
    from core.models import Proyecto

    proyecto = Proyecto.objects.create(nombre="COIN")
    request = RequestFactory().get("/", {"html": "1"})
    request.user = UserFactory(is_superuser=True, is_staff=True)

    html = core_views.pdf_memoria_economica(request, proyecto.id).content.decode("utf-8")

    assert "data:image/png;base64," in html
    assert 'src="/static' not in html


def test_si_weasyprint_falla_el_informe_sigue_saliendo_en_html():
    """En una pantalla de uso diario vale más el HTML que un error 500."""
    from core.models import Proyecto

    proyecto = Proyecto.objects.create(nombre="COIN")
    request = RequestFactory().get("/")
    request.user = UserFactory(is_superuser=True, is_staff=True)

    class _HTMLQueRevienta:
        def __init__(self, *args, **kwargs):
            raise RuntimeError("falta pango")

    with patch.dict(sys.modules, {"weasyprint": SimpleNamespace(HTML=_HTMLQueRevienta)}):
        response = core_views.pdf_memoria_economica(request, proyecto.id)

    assert response.status_code == 200
    assert "text/html" in response["Content-Type"]


# --- La configuración de fuentes se comparte -------------------------------


@pytest.fixture
def fuentes_limpias():
    """
    Vacía la caché por hilo antes y después.

    Los tests comparten hilo, y hay otros que sustituyen `weasyprint` por un
    doble sin submódulos: si uno de ésos corre antes, deja cacheado que no hay
    configuración y estas comprobaciones se saltarían sin comprobar nada.
    """
    from core.pdf import _local, _vivas

    for _ in range(2):
        if hasattr(_local, "config"):
            del _local.config
        _vivas.clear()
        yield
        return


def test_la_configuracion_de_fuentes_es_la_misma_siempre(fuentes_limpias):
    """
    WeasyPrint monta una `FontConfiguration` nueva por cada `write_pdf()` si no
    se le pasa una, y al recogerla el recolector, Pango desmonta su font map y
    harfbuzz destruye caras de tipografía que ya no valen: el proceso se cae
    entero con SIGSEGV. Se veía como una caída de la suite una de cada doce,
    siempre durante el recolector, que era el momento pero no la causa.

    Compartir una que no se destruye nunca evita esa ruta.
    """
    from core.pdf import _configuracion_fuentes, _vivas

    primera = _configuracion_fuentes()
    if primera is None:
        pytest.skip("WeasyPrint no expone FontConfiguration en este entorno")

    assert _configuracion_fuentes() is primera
    # Y alguien se queda con una referencia fuerte, que es lo que impide que
    # llegue a finalizarse aunque muera el hilo que la creó.
    assert any(v is primera for v in _vivas)


def test_el_pdf_se_genera_con_la_configuracion_compartida(monkeypatch, fuentes_limpias):
    from core import pdf as core_pdf

    recogido = {}

    class _FalsoHTML:
        def __init__(self, string, base_url=None):
            recogido["base_url"] = base_url

        def write_pdf(self, **kwargs):
            recogido["font_config"] = kwargs.get("font_config")
            return b"%PDF-falso"

    monkeypatch.setitem(sys.modules, "weasyprint", SimpleNamespace(HTML=_FalsoHTML))

    esperada = core_pdf._configuracion_fuentes()
    assert esperada is not None, "sin configuración esto no comprobaría nada"
    assert core_pdf.render_pdf("<p>x</p>", "https://ejemplo.test/") == b"%PDF-falso"
    assert recogido["base_url"] == "https://ejemplo.test/"
    assert recogido["font_config"] is esperada


def test_ningun_pdf_se_genera_saltandose_el_ayudante():
    """
    Si alguien vuelve a llamar a `write_pdf()` por su cuenta, vuelve la caída.
    El único sitio que puede hacerlo es `core/pdf.py`.
    """
    from pathlib import Path

    raiz = Path(__file__).resolve().parent.parent
    culpables = []
    for ruta in list(raiz.glob("*/views*.py")) + list(raiz.glob("*/views/*.py")):
        if ".venv" in str(ruta) or ".claude" in str(ruta):
            continue
        if "write_pdf(" in ruta.read_text("utf-8"):
            culpables.append(str(ruta.relative_to(raiz)))

    assert culpables == [], "generan el PDF sin compartir las fuentes: {}".format(culpables)
