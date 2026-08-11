from types import SimpleNamespace

from django.http import HttpResponse
from django.test import RequestFactory
from django.urls import reverse

from accounts.middleware import RoleAccessMiddleware


def _make_request(username: str) -> SimpleNamespace:
    request = RequestFactory().get("/app/usuarios/")
    request.user = SimpleNamespace(
        username=username,
        is_authenticated=True,
        is_verified=lambda: False,
    )
    return request


def _allow_all_permissions(user):
    return {
        "can_simulador": True,
        "can_estudios": True,
        "can_proyectos": True,
        "can_clientes": True,
        "can_inversores": True,
        "can_usuarios": True,
        "can_cms": True,
        "can_facturas_preview": True,
    }


def test_codex_test_is_redirected_to_two_factor_setup(monkeypatch):
    request = _make_request("codex-test")
    middleware = RoleAccessMiddleware(lambda req: HttpResponse("ok"))

    monkeypatch.setattr("accounts.middleware.resolve_permissions", _allow_all_permissions)
    monkeypatch.setattr("accounts.middleware.use_custom_permissions", lambda user: False)
    monkeypatch.setattr("accounts.middleware.is_admin_user", lambda user: False)

    response = middleware(request)

    assert response.status_code == 302
    assert response.url == reverse("two_factor:setup")


def test_non_bypass_user_is_redirected_to_two_factor_setup(monkeypatch):
    request = _make_request("regular-user")
    middleware = RoleAccessMiddleware(lambda req: HttpResponse("ok"))

    monkeypatch.setattr("accounts.middleware.resolve_permissions", _allow_all_permissions)
    monkeypatch.setattr("accounts.middleware.use_custom_permissions", lambda user: False)
    monkeypatch.setattr("accounts.middleware.is_admin_user", lambda user: False)

    response = middleware(request)

    assert response.status_code == 302
    assert response.url == reverse("two_factor:setup")
