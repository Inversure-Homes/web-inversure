import pytest
from django.urls import reverse

from .factories import NoticiaFactory

pytestmark = pytest.mark.django_db


def test_landing_home_is_public(client):
    response = client.get(reverse("landing:home"))
    assert response.status_code == 200
    body = response.content.decode("utf-8")
    assert "Control total de cada operación" in body


def test_landing_news_list_is_public(client):
    response = client.get(reverse("landing:noticias_list"))
    assert response.status_code == 200
    assert "Noticias" in response.content.decode("utf-8")


def test_noticia_generates_slug_when_missing():
    noticia = NoticiaFactory(slug="", titulo="Nueva noticia del proyecto")
    assert noticia.slug.startswith("nueva-noticia-del-proyecto")
