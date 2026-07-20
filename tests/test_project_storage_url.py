from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import date
from decimal import Decimal
from types import SimpleNamespace

import pytest
from django.test import RequestFactory

from core import views as core_views
from core.views import _build_project_storage_url


@dataclass
class _Archivo:
    name: str = ""
    url_value: str = ""

    @property
    def url(self):
        return self.url_value


class _QuerySetStub(list):
    def filter(self, *args, **kwargs):
        return self

    def order_by(self, *args, **kwargs):
        return self

    def select_related(self, *args, **kwargs):
        return self

    def exclude(self, *args, **kwargs):
        return self


def _make_request(method: str = "GET", path: str = "/proyectos/1/"):
    request = RequestFactory().generic(method, path)
    request.user = SimpleNamespace(username="tester")
    return request


def _patch_project_access(monkeypatch, project):
    monkeypatch.setattr(core_views.Proyecto, "objects", SimpleNamespace(get=lambda *args, **kwargs: project))
    monkeypatch.setattr(core_views, "_user_can_view_project", lambda user, proyecto: True)
    monkeypatch.setattr(core_views, "_user_can_edit_project", lambda user, proyecto: True)
    monkeypatch.setattr(core_views, "_can_preview_facturas", lambda user: True)


@pytest.mark.parametrize(
    ("key", "signed", "expected"),
    [
        ("signed.pdf", "signed://signed.pdf", "signed://signed.pdf"),
        ("plain.pdf", "", "plain-url"),
    ],
)
def test_build_project_storage_url_prefers_signed_url_and_falls_back_to_archivo_url(monkeypatch, key, signed, expected):
    media = SimpleNamespace(archivo=_Archivo(name=key, url_value="plain-url"))

    monkeypatch.setattr(core_views, "_s3_presigned_url", lambda current_key: signed if current_key == key else "")

    original = dict(getattr(media, "__dict__", {}))

    assert _build_project_storage_url(media) == expected
    assert dict(getattr(media, "__dict__", {})) == original


def test_proyecto_gastos_uses_storage_urls_for_facturas_and_fallback_documents(monkeypatch):
    project = SimpleNamespace(id=1)
    docs = _QuerySetStub(
        [
            SimpleNamespace(
                fecha_factura=date(2026, 7, 20),
                importe_factura=Decimal("100.00"),
                archivo=_Archivo(name="factura-doc.pdf", url_value="doc-url"),
            ),
        ]
    )
    gastos = _QuerySetStub(
        [
            SimpleNamespace(
                id=1,
                fecha=date(2026, 7, 20),
                categoria="obra",
                concepto="Directo",
                proveedor="Proveedor A",
                importe=Decimal("100.00"),
                imputable_inversores=True,
                estado=None,
                observaciones=None,
                pagado=False,
                factura=SimpleNamespace(archivo=_Archivo(name="factura-directa.pdf", url_value="direct-url")),
            ),
            SimpleNamespace(
                id=2,
                fecha=date(2026, 7, 20),
                categoria="obra",
                concepto="Con documento",
                proveedor="Proveedor B",
                importe=Decimal("100.00"),
                imputable_inversores=False,
                estado="confirmado",
                observaciones="",
                pagado=True,
                factura=None,
            ),
        ]
    )

    _patch_project_access(monkeypatch, project)
    monkeypatch.setattr(core_views.DocumentoProyecto, "objects", SimpleNamespace(filter=lambda *args, **kwargs: docs))
    monkeypatch.setattr(core_views.GastoProyecto, "objects", SimpleNamespace(filter=lambda *args, **kwargs: gastos))

    def _fake_signed_url(key: str):
        if key == "factura-directa.pdf":
            return "signed://factura-directa.pdf"
        return ""

    monkeypatch.setattr(core_views, "_s3_presigned_url", _fake_signed_url)

    response = core_views.proyecto_gastos(_make_request(), project.id)
    payload = json.loads(response.content)

    assert response.status_code == 200
    assert payload["ok"] is True
    assert payload["gastos"] == [
        {
            "id": 1,
            "fecha": "2026-07-20",
            "categoria": "obra",
            "concepto": "Directo",
            "proveedor": "Proveedor A",
            "importe": 100.0,
            "imputable_inversores": True,
            "estado": "estimado",
            "observaciones": None,
            "pagado": False,
            "factura_url": "signed://factura-directa.pdf",
            "has_factura": True,
        },
        {
            "id": 2,
            "fecha": "2026-07-20",
            "categoria": "obra",
            "concepto": "Con documento",
            "proveedor": "Proveedor B",
            "importe": 100.0,
            "imputable_inversores": False,
            "estado": "confirmado",
            "observaciones": "",
            "pagado": True,
            "factura_url": "doc-url",
            "has_factura": True,
        },
    ]


def test_proyecto_gasto_detalle_uses_storage_url_for_factura(monkeypatch):
    project = SimpleNamespace(id=1)
    gasto = SimpleNamespace(
        id=10,
        proyecto=project,
        fecha=date(2026, 7, 21),
        categoria="obra",
        concepto="Detalle",
        proveedor="Proveedor",
        importe=Decimal("42.50"),
        imputable_inversores=True,
        estado="estimado",
        observaciones=None,
        pagado=False,
        factura=SimpleNamespace(archivo=_Archivo(name="detalle.pdf", url_value="detalle-url")),
    )

    class _GastoManager:
        def select_related(self, *args, **kwargs):
            return self

        def get(self, *args, **kwargs):
            return gasto

    _patch_project_access(monkeypatch, project)
    monkeypatch.setattr(core_views.GastoProyecto, "objects", _GastoManager())
    monkeypatch.setattr(
        core_views, "_s3_presigned_url", lambda key: "signed://detalle.pdf" if key == "detalle.pdf" else ""
    )

    response = core_views.proyecto_gasto_detalle(_make_request(), project.id, gasto.id)
    payload = json.loads(response.content)

    assert response.status_code == 200
    assert payload == {
        "ok": True,
        "gasto": {
            "id": 10,
            "fecha": "2026-07-21",
            "categoria": "obra",
            "concepto": "Detalle",
            "proveedor": "Proveedor",
            "importe": 42.5,
            "imputable_inversores": True,
            "estado": "estimado",
            "observaciones": None,
            "pagado": False,
            "factura_url": "signed://detalle.pdf",
            "has_factura": True,
        },
    }


def test_proyecto_ingresos_uses_storage_urls_for_justificantes(monkeypatch):
    project = SimpleNamespace(id=1)
    ingresos = _QuerySetStub(
        [
            SimpleNamespace(
                id=1,
                fecha=date(2026, 7, 22),
                tipo="ingreso",
                concepto="Con justificante",
                importe=Decimal("21.00"),
                estado=None,
                imputable_inversores=True,
                observaciones=None,
                pagado=False,
                justificante=SimpleNamespace(archivo=_Archivo(name="justificante.pdf", url_value="justificante-url")),
            ),
        ]
    )

    _patch_project_access(monkeypatch, project)
    monkeypatch.setattr(core_views.IngresoProyecto, "objects", SimpleNamespace(filter=lambda *args, **kwargs: ingresos))
    monkeypatch.setattr(
        core_views, "_s3_presigned_url", lambda key: "signed://justificante.pdf" if key == "justificante.pdf" else ""
    )

    response = core_views.proyecto_ingresos(_make_request(), project.id)
    payload = json.loads(response.content)

    assert response.status_code == 200
    assert payload["ok"] is True
    assert payload["ingresos"] == [
        {
            "id": 1,
            "fecha": "2026-07-22",
            "tipo": "ingreso",
            "concepto": "Con justificante",
            "importe": 21.0,
            "estado": "estimado",
            "imputable_inversores": True,
            "observaciones": None,
            "pagado": False,
            "justificante_url": "signed://justificante.pdf",
            "has_justificante": True,
        }
    ]


def test_proyecto_ingreso_detalle_uses_storage_url_for_justificante(monkeypatch):
    project = SimpleNamespace(id=1)
    ingreso = SimpleNamespace(
        id=11,
        proyecto=project,
        fecha=date(2026, 7, 23),
        tipo="ingreso",
        concepto="Detalle ingreso",
        importe=Decimal("33.00"),
        estado="confirmado",
        imputable_inversores=False,
        observaciones="nota",
        pagado=True,
        justificante=SimpleNamespace(archivo=_Archivo(name="ingreso.pdf", url_value="ingreso-url")),
    )

    class _IngresoManager:
        def select_related(self, *args, **kwargs):
            return self

        def get(self, *args, **kwargs):
            return ingreso

    _patch_project_access(monkeypatch, project)
    monkeypatch.setattr(core_views.IngresoProyecto, "objects", _IngresoManager())
    monkeypatch.setattr(
        core_views, "_s3_presigned_url", lambda key: "signed://ingreso.pdf" if key == "ingreso.pdf" else ""
    )

    response = core_views.proyecto_ingreso_detalle(_make_request(), project.id, ingreso.id)
    payload = json.loads(response.content)

    assert response.status_code == 200
    assert payload == {
        "ok": True,
        "ingreso": {
            "id": 11,
            "fecha": "2026-07-23",
            "tipo": "ingreso",
            "concepto": "Detalle ingreso",
            "importe": 33.0,
            "estado": "confirmado",
            "imputable_inversores": False,
            "observaciones": "nota",
            "pagado": True,
            "justificante_url": "signed://ingreso.pdf",
            "has_justificante": True,
        },
    }


def test_proyecto_ingreso_justificante_uses_storage_url_helper(monkeypatch):
    project = SimpleNamespace(id=1)
    ingreso = SimpleNamespace(id=12, proyecto=project)
    just_obj = SimpleNamespace(archivo=None, nombre_original="", save=lambda: None)

    class _IngresoManager:
        def select_related(self, *args, **kwargs):
            return self

        def get(self, *args, **kwargs):
            return ingreso

    _patch_project_access(monkeypatch, project)
    monkeypatch.setattr(core_views.IngresoProyecto, "objects", _IngresoManager())
    monkeypatch.setattr(
        core_views.JustificanteIngreso,
        "objects",
        SimpleNamespace(get_or_create=lambda *args, **kwargs: (just_obj, True)),
    )
    monkeypatch.setattr(
        core_views, "_s3_presigned_url", lambda key: "signed://ingreso.pdf" if key == "ingreso.pdf" else ""
    )

    request = _make_request("POST", "/proyectos/1/ingresos/12/justificante/")
    request._files = {"justificante": _Archivo(name="ingreso.pdf", url_value="ingreso-url")}

    response = core_views.proyecto_ingreso_justificante(request, project.id, ingreso.id)
    payload = json.loads(response.content)

    assert response.status_code == 200
    assert payload == {"ok": True, "justificante_url": "signed://ingreso.pdf"}
