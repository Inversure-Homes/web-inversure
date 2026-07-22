import json
from types import SimpleNamespace

import pytest
from django.http import JsonResponse
from django.test import RequestFactory

from core import views as core_views


class _FakeDocument:
    def __init__(self, proyecto):
        self.proyecto = proyecto
        self.categoria = "fotografias"
        self.usar_pdf = False
        self.usar_story = False
        self.usar_instagram = False
        self.usar_dossier = False
        self.delete_called = False
        self.save_called = False

    def delete(self):
        self.delete_called = True

    def save(self, *args, **kwargs):
        self.save_called = True


class _FailOnUpdateManager:
    def update(self, *args, **kwargs):
        raise AssertionError("DocumentoProyecto.objects.filter(...).update() no debería ejecutarse")


@pytest.mark.parametrize(
    ("view_name", "request_data", "expected_response"),
    [
        ("proyecto_documento_borrar", {}, {"ok": False, "error": "No tienes permisos para editar este proyecto."}),
        ("proyecto_documento_principal", {}, {"ok": False, "error": "No tienes permisos para editar este proyecto."}),
        (
            "proyecto_documento_flag",
            {"field": "usar_pdf", "value": "1"},
            {"ok": False, "error": "No tienes permisos para editar este proyecto."},
        ),
    ],
)
def test_project_document_actions_require_edit_permission(monkeypatch, view_name, request_data, expected_response):
    request = RequestFactory().post(
        "/app/proyectos/1/documentos/2/",
        data=request_data,
    )
    request.user = SimpleNamespace(username="viewer", is_authenticated=True)
    fake_project = SimpleNamespace(id=1, nombre="Proyecto demo")
    fake_document = _FakeDocument(fake_project)

    monkeypatch.setattr(core_views, "get_object_or_404", lambda *args, **kwargs: fake_document)
    monkeypatch.setattr(core_views, "_user_can_edit_project", lambda user, proyecto: False)
    monkeypatch.setattr(core_views.DocumentoProyecto.objects, "filter", lambda *args, **kwargs: _FailOnUpdateManager())

    response = getattr(core_views, view_name)(request, 1, 2)

    assert isinstance(response, JsonResponse)
    assert response.status_code == 403
    assert json.loads(response.content) == expected_response
    assert fake_document.delete_called is False
    assert fake_document.save_called is False


def test_project_document_flag_keeps_successful_edit_flow(monkeypatch):
    request = RequestFactory().post(
        "/app/proyectos/1/documentos/2/flag/",
        data={"field": "usar_pdf", "value": "1"},
    )
    request.user = SimpleNamespace(username="editor", is_authenticated=True)
    fake_project = SimpleNamespace(id=1, nombre="Proyecto demo")
    fake_document = _FakeDocument(fake_project)

    monkeypatch.setattr(core_views, "get_object_or_404", lambda *args, **kwargs: fake_document)
    monkeypatch.setattr(core_views, "_user_can_edit_project", lambda user, proyecto: True)

    response = core_views.proyecto_documento_flag(request, 1, 2)

    assert isinstance(response, JsonResponse)
    assert response.status_code == 200
    assert json.loads(response.content) == {"ok": True, "field": "usar_pdf", "value": True}
    assert fake_document.usar_pdf is True
