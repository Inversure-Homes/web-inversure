from __future__ import annotations

from copy import deepcopy
from dataclasses import dataclass
from datetime import date
from decimal import Decimal
from types import SimpleNamespace

import pytest
from django.http import HttpResponse
from django.test import RequestFactory

from core import views as core_views
from core.views import (
    _build_project_documents_collection_context,
    _build_project_documents_context,
    _select_project_document_principal,
)


@dataclass
class _Archivo:
    url: str


@dataclass
class _Documento:
    id: int
    categoria: str | None = None
    titulo: str | None = ""
    es_principal: bool = False
    archivo: _Archivo | None = None
    signed_url: str | None = None
    fecha_factura: date | None = None
    importe_factura: Decimal | None = None


class _GetRaisesDict(dict):
    def get(self, key, default=None):
        raise RuntimeError("get failed")


class _QuerySetStub(list):
    def filter(self, *args, **kwargs):
        return self

    def order_by(self, *args, **kwargs):
        return self

    def select_related(self, *args, **kwargs):
        return self

    def aggregate(self, *args, **kwargs):
        return {"total": None}

    def count(self):
        return len(self)

    def first(self):
        return self[0] if self else None

    def values_list(self, *args, **kwargs):
        return []


class _FailingPrincipalDocument:
    def __init__(self, *, id: int, categoria: str, titulo: str, archivo: _Archivo):
        self.id = id
        self.categoria = categoria
        self.titulo = titulo
        self.archivo = archivo
        self.signed_url = None

    @property
    def es_principal(self):
        raise RuntimeError("principal lookup failed")


def _make_project_request() -> RequestFactory:
    request = RequestFactory().get("/proyectos/1/")
    request.user = SimpleNamespace(username="tester")
    return request


def _install_project_flow_stubs(monkeypatch, documentos, *, overlay_ctx=None):
    fake_project = SimpleNamespace(
        id=1,
        nombre="Proyecto demo",
        estado="captacion",
        acceso_comercial=False,
        responsable="",
        extra={},
        snapshot_datos={},
        origen_snapshot=None,
        origen_estudio=None,
        difusion_clientes=SimpleNamespace(values_list=lambda *args, **kwargs: []),
    )

    monkeypatch.setattr(core_views, "get_object_or_404", lambda model, *args, **kwargs: fake_project)
    monkeypatch.setattr(core_views, "_user_can_view_project", lambda user, proyecto: True)
    monkeypatch.setattr(core_views, "_user_can_edit_project", lambda user, proyecto: True)
    monkeypatch.setattr(core_views, "is_admin_user", lambda user: False)
    monkeypatch.setattr(core_views, "use_custom_permissions", lambda user: False)
    monkeypatch.setattr(core_views, "_ensure_checklist_defaults", lambda proyecto: None)
    monkeypatch.setattr(
        core_views,
        "_metricas_desde_estudio",
        lambda estudio: {"metricas": {}, "inversor": {}, "resultado": {}},
    )
    monkeypatch.setattr(core_views, "_resultado_desde_metricas", lambda metricas: {})
    monkeypatch.setattr(core_views, "_resultado_desde_memoria", lambda proyecto, snapshot=None: {})
    monkeypatch.setattr(core_views, "_build_resultado_context", lambda *args, **kwargs: {})
    monkeypatch.setattr(core_views, "_build_inversor_context", lambda *args, **kwargs: {})
    monkeypatch.setattr(core_views, "_build_estado_inicial_context", lambda *args, **kwargs: {})
    monkeypatch.setattr(
        core_views,
        "_build_captacion_context",
        lambda *args, **kwargs: core_views.SafeAccessDict(
            {
                "capital_objetivo": 0.0,
                "capital_captado": 0.0,
                "pct_captado": 0.0,
                "restante": 0.0,
                "pct_restante": 100.0,
                "capital_objetivo_fmt": "0,00 €",
                "capital_captado_fmt": "0,00 €",
                "restante_fmt": "0,00 €",
                "pct_captado_fmt": "0,00 %",
                "pct_restante_fmt": "100,00 %",
            }
        ),
    )
    monkeypatch.setattr(
        core_views,
        "_build_project_overlay_context",
        lambda *args, **kwargs: (
            overlay_ctx
            if overlay_ctx is not None
            else {
                "landing_config": {},
                "publicaciones_config": {},
                "difusion_config": {},
                "pending_estado_notif": None,
                "difusion_anexos_ids": set(),
            }
        ),
    )
    monkeypatch.setattr(core_views, "_build_checklist_users_context", lambda *args, **kwargs: [])
    monkeypatch.setattr(core_views, "_build_conciertos_context", lambda *args, **kwargs: core_views.SafeAccessDict({}))
    monkeypatch.setattr(core_views, "_build_landing_beneficio_neto_pct_auto", lambda *args, **kwargs: None)

    monkeypatch.setattr(
        core_views.ProyectoSnapshot, "objects", SimpleNamespace(filter=lambda *args, **kwargs: _QuerySetStub([]))
    )
    monkeypatch.setattr(
        core_views.GastoProyecto, "objects", SimpleNamespace(filter=lambda *args, **kwargs: _QuerySetStub([]))
    )
    monkeypatch.setattr(
        core_views.Participacion, "objects", SimpleNamespace(filter=lambda *args, **kwargs: _QuerySetStub([]))
    )
    monkeypatch.setattr(
        core_views.SolicitudParticipacion, "objects", SimpleNamespace(filter=lambda *args, **kwargs: _QuerySetStub([]))
    )
    monkeypatch.setattr(
        core_views.ChecklistItem, "objects", SimpleNamespace(filter=lambda *args, **kwargs: _QuerySetStub([]))
    )
    monkeypatch.setattr(core_views.Cliente, "objects", SimpleNamespace(all=lambda *args, **kwargs: _QuerySetStub([])))
    monkeypatch.setattr(core_views.User, "objects", SimpleNamespace(filter=lambda *args, **kwargs: _QuerySetStub([])))
    monkeypatch.setattr(
        core_views.FacturaGasto, "objects", SimpleNamespace(select_related=lambda *args, **kwargs: _QuerySetStub([]))
    )

    documentos_qs = _QuerySetStub(documentos)
    monkeypatch.setattr(
        core_views.DocumentoProyecto, "objects", SimpleNamespace(filter=lambda *args, **kwargs: documentos_qs)
    )
    monkeypatch.setattr(
        core_views, "render", lambda request, template_name, context=None, *args, **kwargs: HttpResponse("captured")
    )
    monkeypatch.setattr(core_views.settings, "AWS_STORAGE_BUCKET_NAME", "", raising=False)

    return fake_project


def test_build_project_documents_context_empty_collection_returns_default_keys_and_does_not_mutate_inputs():
    documentos: list[_Documento] = []
    landing_config = {}
    original_landing = deepcopy(landing_config)

    result = _build_project_documents_context(documentos, None, landing_config)

    assert result == {
        "fotos_docs": [],
        "landing_preview_url": None,
        "facturas_docs": [],
    }
    assert landing_config == original_landing


def test_build_project_documents_context_preserves_order_and_document_shapes():
    documentos = [
        _Documento(id=1, categoria="", titulo="Sin categoría", archivo=_Archivo("otros.jpg")),
        _Documento(
            id=2,
            categoria="fotografias",
            titulo="Principal base",
            es_principal=True,
            archivo=_Archivo("principal.jpg"),
            signed_url="principal-signed.jpg",
        ),
        _Documento(
            id=3,
            categoria="fotografias",
            titulo="Landing",
            archivo=_Archivo("landing.jpg"),
            signed_url="landing-signed.jpg",
        ),
        _Documento(
            id=4,
            categoria="fotografias",
            titulo="Cabecera",
            archivo=_Archivo("cabecera.jpg"),
            signed_url="",
        ),
        _Documento(
            id=5,
            categoria="facturas",
            titulo=None,
            archivo=_Archivo("factura.pdf"),
            signed_url="factura-signed.pdf",
            fecha_factura=date(2026, 7, 18),
            importe_factura=Decimal("123.45"),
        ),
    ]
    landing_config = {"imagen_id": 3}
    publicaciones_config = {"cabecera_imagen_id": 3}
    original_documentos = deepcopy(documentos)
    original_landing = deepcopy(landing_config)
    principal = documentos[1]

    result = _build_project_documents_context(documentos, principal, landing_config, publicaciones_config)

    assert result["foto_principal_url"] == "landing-signed.jpg"
    assert result["foto_principal_titulo"] == "Landing"
    assert result["landing_preview_url"] == "landing-signed.jpg"
    assert result["fotos_docs"] == [
        {"id": 2, "titulo": "Principal base", "archivo_url": "principal-signed.jpg"},
        {"id": 3, "titulo": "Landing", "archivo_url": "landing-signed.jpg"},
        {"id": 4, "titulo": "Cabecera", "archivo_url": "cabecera.jpg"},
    ]
    assert result["facturas_docs"] == [
        {
            "id": 5,
            "titulo": None,
            "fecha": "2026-07-18",
            "importe": 123.45,
            "archivo_url": "factura-signed.pdf",
        }
    ]
    assert documentos == original_documentos
    assert landing_config == original_landing


def test_build_project_documents_context_falls_back_to_principal_and_handles_missing_files_and_empty_configs():
    documentos = [
        _Documento(
            id=10,
            categoria="fotografias",
            titulo="Principal",
            es_principal=True,
            archivo=_Archivo("principal.jpg"),
            signed_url="",
        ),
        _Documento(
            id=11,
            categoria="fotografias",
            titulo="Sin archivo",
            archivo=None,
            signed_url=None,
        ),
        _Documento(
            id=12,
            categoria="facturas",
            titulo="Factura vacía",
            archivo=None,
            signed_url="",
            fecha_factura=None,
            importe_factura=None,
        ),
    ]
    landing_config = {}
    principal = documentos[0]
    original_documentos = deepcopy(documentos)
    original_landing = deepcopy(landing_config)

    result = _build_project_documents_context(documentos, principal, landing_config)

    assert result["foto_principal_url"] == "principal.jpg"
    assert result["foto_principal_titulo"] == "Principal"
    assert result["landing_preview_url"] == "principal.jpg"
    assert result["fotos_docs"] == [
        {"id": 10, "titulo": "Principal", "archivo_url": "principal.jpg"},
        {"id": 11, "titulo": "Sin archivo", "archivo_url": None},
    ]
    assert result["facturas_docs"] == [
        {
            "id": 12,
            "titulo": "Factura vacía",
            "fecha": None,
            "importe": None,
            "archivo_url": None,
        }
    ]
    assert documentos == original_documentos
    assert landing_config == original_landing


def test_build_project_documents_context_keeps_partial_context_when_landing_config_get_raises():
    documentos = [
        _Documento(
            id=20,
            categoria="fotografias",
            titulo="Principal",
            es_principal=True,
            archivo=_Archivo("principal.jpg"),
            signed_url="principal-signed.jpg",
        ),
        _Documento(
            id=21,
            categoria="facturas",
            titulo="Factura",
            archivo=_Archivo("factura.pdf"),
            signed_url="factura-signed.pdf",
        ),
    ]
    landing_config = _GetRaisesDict({"imagen_id": 20})
    publicaciones_config = _GetRaisesDict({"cabecera_imagen_id": 20})
    principal = documentos[0]
    original_documentos = deepcopy(documentos)

    result = _build_project_documents_context(documentos, principal, landing_config, publicaciones_config)

    assert result["landing_preview_url"] is None
    assert result["foto_principal_url"] == "principal-signed.jpg"
    assert result["foto_principal_titulo"] == "Principal"
    assert result["fotos_docs"] == [
        {"id": 20, "titulo": "Principal", "archivo_url": "principal-signed.jpg"},
    ]
    assert result["facturas_docs"] == [
        {
            "id": 21,
            "titulo": "Factura",
            "fecha": None,
            "importe": None,
            "archivo_url": "factura-signed.pdf",
        }
    ]
    assert documentos == original_documentos


def test_build_project_documents_collection_context_applies_signed_urls_and_groups_documents(monkeypatch):
    documentos = [
        _Documento(
            id=70,
            categoria="fotografias",
            titulo="Principal",
            archivo=SimpleNamespace(name="principal.jpg", url="principal.jpg"),
        ),
        _Documento(
            id=71,
            categoria="facturas",
            titulo="Factura",
            archivo=SimpleNamespace(name="factura.pdf", url="factura.pdf"),
        ),
    ]
    signed_keys: list[str] = []

    def _fake_signed_url(key):
        signed_keys.append(key)
        if key == "principal.jpg":
            return "principal-signed.jpg"
        raise RuntimeError("boom")

    monkeypatch.setattr(core_views, "_s3_presigned_url", _fake_signed_url)

    result = _build_project_documents_collection_context(documentos, True)

    assert signed_keys == ["principal.jpg", "factura.pdf"]
    assert result["documentos"] is documentos
    assert documentos[0].signed_url == "principal-signed.jpg"
    assert documentos[1].signed_url is None
    assert result["documentos_por_categoria"] == {
        "fotografias": [documentos[0]],
        "facturas": [documentos[1]],
    }


def test_build_project_documents_collection_context_without_signing_keeps_documents_and_groups(monkeypatch):
    documentos = [
        _Documento(
            id=72,
            categoria="fotografias",
            titulo="Principal",
            archivo=SimpleNamespace(name="principal.jpg", url="principal.jpg"),
        ),
    ]
    original_documentos = deepcopy(documentos)

    monkeypatch.setattr(core_views, "_s3_presigned_url", lambda key: (_ for _ in ()).throw(RuntimeError("boom")))

    result = _build_project_documents_collection_context(documentos, False)

    assert result["documentos"] == documentos
    assert result["documentos_por_categoria"] == {"fotografias": [documentos[0]]}
    assert documentos == original_documentos


@pytest.mark.parametrize(
    "documentos, expected_id",
    [
        (
            [
                _Documento(id=50, categoria="fotografias", titulo="Primera", archivo=_Archivo("primera.jpg")),
                _Documento(
                    id=51,
                    categoria="fotografias",
                    titulo="Principal",
                    es_principal=True,
                    archivo=_Archivo("principal.jpg"),
                ),
            ],
            51,
        ),
        (
            [
                _Documento(id=60, categoria="fotografias", titulo="Primera", archivo=_Archivo("primera.jpg")),
                _Documento(id=61, categoria="facturas", titulo="Factura", archivo=_Archivo("factura.pdf")),
            ],
            60,
        ),
        ([], None),
    ],
)
def test_select_project_document_principal_prefers_principal_photo_and_falls_back_to_first_photo(
    documentos, expected_id
):
    result = _select_project_document_principal(documentos)

    if expected_id is None:
        assert result is None
    else:
        assert result.id == expected_id


def test_project_documents_context_preserves_empty_documents_when_principal_selection_raises(monkeypatch):
    documentos = [
        _FailingPrincipalDocument(
            id=30, categoria="fotografias", titulo="Rompedora", archivo=_Archivo("rompedora.jpg")
        ),
        _Documento(
            id=31,
            categoria="facturas",
            titulo="Factura posterior",
            archivo=_Archivo("factura-posterior.pdf"),
            signed_url="factura-posterior-signed.pdf",
        ),
    ]
    fake_project = _install_project_flow_stubs(monkeypatch, documentos)
    request = _make_project_request()

    captured = {}

    def _fake_render(request, template_name, context=None, *args, **kwargs):
        captured["template_name"] = template_name
        captured["context"] = context or {}
        return HttpResponse("captured")

    monkeypatch.setattr(core_views, "render", _fake_render)

    response = core_views.proyecto(request, fake_project.id)

    assert response.status_code == 200
    assert captured["template_name"] == "core/proyecto.html"
    ctx = captured["context"]
    assert ctx["documentos_por_categoria"] == {
        "fotografias": [documentos[0]],
        "facturas": [documentos[1]],
    }
    assert ctx["documentos"] == []
    assert "foto_principal_url" not in ctx
    assert "foto_principal_titulo" not in ctx
    assert "fotos_docs" not in ctx
    assert "landing_preview_url" not in ctx
    assert "facturas_docs" not in ctx


def test_project_documents_context_does_not_bypass_editability_for_mperez(monkeypatch):
    documentos = []
    fake_project = _install_project_flow_stubs(monkeypatch, documentos)
    request = _make_project_request()
    request.user = SimpleNamespace(username="mperez", is_authenticated=True)
    monkeypatch.setattr(core_views, "_user_can_edit_project", lambda user, proyecto: False)

    captured = {}

    def _fake_render(request, template_name, context=None, *args, **kwargs):
        captured["template_name"] = template_name
        captured["context"] = context or {}
        return HttpResponse("captured")

    monkeypatch.setattr(core_views, "render", _fake_render)

    response = core_views.proyecto(request, fake_project.id)

    assert response.status_code == 200
    ctx = captured["context"]
    assert ctx["editable"] is False
    assert ctx["editable_estado"] is False


def test_project_documents_context_keeps_materialized_documents_on_normal_flow(monkeypatch):
    documentos = [
        _Documento(
            id=40,
            categoria="fotografias",
            titulo="Principal",
            es_principal=True,
            archivo=_Archivo("normal.jpg"),
            signed_url="normal-signed.jpg",
        ),
        _Documento(
            id=41,
            categoria="fotografias",
            titulo="Cabecera",
            archivo=_Archivo("cabecera.jpg"),
            signed_url="cabecera-signed.jpg",
        ),
        _Documento(
            id=42,
            categoria="facturas",
            titulo="Factura",
            archivo=_Archivo("factura.pdf"),
            signed_url="factura-signed.pdf",
        ),
    ]
    fake_project = _install_project_flow_stubs(
        monkeypatch,
        documentos,
        overlay_ctx={
            "landing_config": {"imagen_id": 41},
            "publicaciones_config": {"cabecera_imagen_id": 41},
            "difusion_config": {},
            "pending_estado_notif": None,
            "difusion_anexos_ids": set(),
        },
    )
    request = _make_project_request()

    captured = {}

    def _fake_render(request, template_name, context=None, *args, **kwargs):
        captured["template_name"] = template_name
        captured["context"] = context or {}
        return HttpResponse("captured")

    monkeypatch.setattr(core_views, "render", _fake_render)

    response = core_views.proyecto(request, fake_project.id)

    assert response.status_code == 200
    assert captured["template_name"] == "core/proyecto.html"
    ctx = captured["context"]
    assert ctx["documentos_por_categoria"] == {
        "fotografias": [documentos[0], documentos[1]],
        "facturas": [documentos[2]],
    }
    assert ctx["documentos"] == documentos
    assert ctx["foto_principal_url"] == "cabecera-signed.jpg"
    assert ctx["foto_principal_titulo"] == "Cabecera"
    assert ctx["landing_preview_url"] == "cabecera-signed.jpg"
    assert ctx["fotos_docs"] == [
        {"id": 40, "titulo": "Principal", "archivo_url": "normal-signed.jpg"},
        {"id": 41, "titulo": "Cabecera", "archivo_url": "cabecera-signed.jpg"},
    ]
    assert ctx["facturas_docs"] == [
        {
            "id": 42,
            "titulo": "Factura",
            "fecha": None,
            "importe": None,
            "archivo_url": "factura-signed.pdf",
        }
    ]
