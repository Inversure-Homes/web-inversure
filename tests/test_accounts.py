import pytest
from django.urls import reverse

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
