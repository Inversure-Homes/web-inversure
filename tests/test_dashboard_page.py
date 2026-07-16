from __future__ import annotations

import pytest
from django.contrib.auth.models import User
from django.urls import reverse
from django.utils import timezone
from django_otp import DEVICE_ID_SESSION_KEY
from django_otp.plugins.otp_totp.models import TOTPDevice

from .factories import UserFactory
from .test_financial_dashboard import _build_service_dataset, _fake_core_views_factory, _fake_settlement

pytestmark = pytest.mark.django_db


def _login_verified_user(client, user: User) -> None:
    device = TOTPDevice.objects.create(user=user, name="pytest-otp-device")
    client.force_login(user)
    session = client.session
    session[DEVICE_ID_SESSION_KEY] = device.persistent_id
    session.save()


def test_dashboard_html_redirects_users_without_permissions(client):
    user = UserFactory()
    _login_verified_user(client, user)

    response = client.get(reverse("core:dashboard"))

    assert response.status_code == 302
    assert response.url == "/app/login/"


def test_dashboard_html_reflects_querystring_filters_and_embeds_initial_payload(verified_client):
    dataset = _build_service_dataset()
    fake_core_views = _fake_core_views_factory(dataset)
    fixed_now = timezone.datetime(2026, 7, 16, 12, 0, 0, tzinfo=timezone.get_current_timezone())
    fixed_today = timezone.datetime(2026, 7, 16, tzinfo=timezone.get_current_timezone()).date()
    start = fixed_today.replace(day=1)
    querystring = {
        "fecha_desde": start.isoformat(),
        "fecha_hasta": fixed_today.isoformat(),
        "proyecto_id": dataset["proyectos"]["activo"].id,
        "estado": "captacion",
    }

    with pytest.MonkeyPatch.context() as monkeypatch:
        monkeypatch.setattr("core.services.financial_dashboard._core_views", lambda: fake_core_views)
        monkeypatch.setattr("core.services.financial_dashboard.calc_inversor_settlement", _fake_settlement)
        monkeypatch.setattr("core.services.financial_dashboard.timezone.now", lambda: fixed_now)
        response = verified_client.get(reverse("core:dashboard"), querystring)

    html = response.content.decode("utf-8")

    assert response.status_code == 200
    assert 'data-dashboard-filters-form' in html
    assert 'data-dashboard-root' in html
    assert 'data-dashboard-reset' in html
    assert "/static/core/dashboard." in html
    assert f'value="{start.isoformat()}"' in html
    assert f'value="{fixed_today.isoformat()}"' in html
    assert f'value="{dataset["proyectos"]["activo"].id}" selected' in html or f'selected>{dataset["proyectos"]["activo"].nombre}' in html
    assert '"estado": "captacion"' in html
    assert f'"proyecto_id": {dataset["proyectos"]["activo"].id}' in html
    assert "financialDashboardData" in html
