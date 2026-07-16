from unittest.mock import patch

from django.http import HttpResponse
from django.test import RequestFactory

from cms.views import root_or_app


def test_root_or_app_redirects_to_app_when_wagtail_returns_404():
    request = RequestFactory().get("/")

    with patch("cms.views.wagtail_serve", return_value=HttpResponse(status=404)):
        response = root_or_app(request)

    assert response.status_code == 302
    assert response.url == "/app/"
