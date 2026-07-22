import json
from types import SimpleNamespace

from django.http import JsonResponse
from django.test import RequestFactory

from core import views as core_views


def test_guardar_proyecto_denies_estado_only_changes_for_mperez(monkeypatch):
    request = RequestFactory().post(
        "/app/proyectos/1/guardar/",
        data='{"estado":"cerrado"}',
        content_type="application/json",
    )
    request.user = SimpleNamespace(username="mperez", is_authenticated=True)
    fake_project = SimpleNamespace(id=1, nombre="Proyecto demo", estado="captacion", extra={})

    monkeypatch.setattr(core_views, "get_object_or_404", lambda model, *args, **kwargs: fake_project)
    monkeypatch.setattr(core_views, "_user_can_edit_project", lambda user, proyecto: False)
    monkeypatch.setattr(core_views, "is_admin_user", lambda user: False)
    monkeypatch.setattr(core_views, "is_direccion_user", lambda user: False)

    notified = []
    monkeypatch.setattr(core_views, "_admin_notify", lambda *args, **kwargs: notified.append((args, kwargs)))

    response = core_views.guardar_proyecto(request, fake_project.id)

    assert isinstance(response, JsonResponse)
    assert response.status_code == 403
    assert json.loads(response.content) == {
        "ok": False,
        "error": "No tienes permisos para editar este proyecto.",
    }
    assert len(notified) == 1
