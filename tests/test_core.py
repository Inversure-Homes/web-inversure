import pytest
from django.urls import reverse

from .factories import InversorPerfilFactory

pytestmark = pytest.mark.django_db


def test_private_core_home_redirects_anonymous(client):
    response = client.get(reverse("core:home"))
    assert response.status_code == 302
    assert response.url.startswith(reverse("accounts:login"))
    assert "next=%2Fapp%2F" in response.url


def test_verified_direccion_user_can_open_core_home(verified_client):
    response = verified_client.get(reverse("core:home"))
    assert response.status_code == 200
    assert "Plataforma interna" in response.content.decode("utf-8")


def test_verified_direccion_user_can_open_simulador_without_active_estudio(verified_client):
    response = verified_client.get(reverse("core:simulador"))

    html = response.content.decode("utf-8")

    assert response.status_code == 200
    assert 'data-convertir-url=""' in html


def test_inversor_portal_without_confirmed_participations_does_not_500(client):
    perfil = InversorPerfilFactory()
    response = client.get(reverse("core:inversor_portal", args=[perfil.token]))

    assert response.status_code == 200
