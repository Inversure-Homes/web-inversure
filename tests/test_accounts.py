from types import SimpleNamespace

import pytest
from django.test import override_settings
from django.urls import reverse

from accounts import views
from accounts.models import UserAccess
from accounts.utils import is_direccion_user, resolve_permissions

from .factories import UserFactory

pytestmark = pytest.mark.django_db


def test_login_view_redirects_to_two_factor_login(client):
    response = client.get(reverse("accounts:login"))
    assert response.status_code == 302
    assert response.url == reverse("two_factor:login")


def test_direccion_role_gets_core_permissions(direccion_user):
    perms = resolve_permissions(direccion_user)
    assert is_direccion_user(direccion_user) is True
    assert perms["can_simulador"] is True
    assert perms["can_estudios"] is True
    assert perms["can_proyectos"] is True
    assert perms["can_cms"] is True
    assert perms["can_facturas_preview"] is True


def test_custom_permissions_override_role(custom_perms_user):
    perms = resolve_permissions(custom_perms_user)
    assert perms["can_estudios"] is True
    assert perms["can_proyectos"] is False
    assert perms["can_cms"] is False


def test_non_admin_useraccess_defaults_to_blank_role():
    user = UserFactory()
    access = UserAccess.objects.create(user=user, role="")
    assert access.role == ""


@override_settings(VAPID_PUBLIC_KEY="")
def test_push_public_key_without_vapid_key_does_not_500(verified_client):
    response = verified_client.get(reverse("accounts:push_public_key"))

    assert response.status_code == 200
    assert response.json() == {
        "ok": False,
        "error": "VAPID public key missing",
        "publicKey": "",
    }


def test_webpush_send_patches_pywebpush_curve_compatibility(monkeypatch):
    subscription = SimpleNamespace(
        endpoint="https://example.com/push",
        p256dh="p256dh-value",
        auth="auth-value",
    )
    seen = {}

    monkeypatch.setattr(views.settings, "VAPID_PRIVATE_KEY", "private-key")
    monkeypatch.setattr(views.settings, "VAPID_PUBLIC_KEY", "public-key")
    monkeypatch.setattr(views.settings, "VAPID_SUBJECT", "mailto:test@example.com")

    class FakeVapid:
        @classmethod
        def from_string(cls, private_key):
            seen["private_key"] = private_key
            return cls()

        def sign(self, claims):
            seen["claims"] = claims
            return {"Authorization": "Bearer test"}

    class FakeWebPusher:
        def __init__(self, subscription_info):
            seen["subscription_info"] = subscription_info

        def send(self, data, headers, content_encoding="aes128gcm"):
            seen["curve_is_instance"] = not isinstance(views.pywebpush.ec.SECP256R1, type)
            seen["curve_call_works"] = views.pywebpush.ec.SECP256R1().name == "secp256r1"
            seen["data"] = data
            seen["headers"] = headers
            seen["content_encoding"] = content_encoding

    monkeypatch.setattr(views, "Vapid", FakeVapid)
    monkeypatch.setattr(views, "WebPusher", FakeWebPusher)

    assert views._webpush_send(subscription, {"title": "Inversure", "body": "Prueba"}) is True
    assert seen["curve_is_instance"] is True
    assert seen["subscription_info"] == {
        "endpoint": "https://example.com/push",
        "keys": {"p256dh": "p256dh-value", "auth": "auth-value"},
    }
    assert seen["private_key"] == "private-key"  # pragma: allowlist secret
    assert seen["claims"] == {
        "sub": "mailto:test@example.com",
        "aud": "https://example.com",
    }
    assert seen["data"] == '{"title": "Inversure", "body": "Prueba"}'
    assert seen["headers"] == {"Authorization": "Bearer test"}
    assert seen["content_encoding"] == "aes128gcm"
    assert seen["curve_call_works"] is True
    assert isinstance(views.pywebpush.ec.SECP256R1, type)
