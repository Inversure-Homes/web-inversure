from __future__ import annotations

import json

import pytest
from django.contrib.auth.models import User
from django.core.serializers.json import DjangoJSONEncoder
from django.urls import reverse
from django.utils import timezone
from django_otp import DEVICE_ID_SESSION_KEY
from django_otp.plugins.otp_totp.models import TOTPDevice

from core.services.financial_dashboard import FinancialDashboardFilters, FinancialDashboardService

from .factories import UserFactory
from .test_financial_dashboard import _build_service_dataset, _fake_core_views_factory, _fake_settlement

pytestmark = pytest.mark.django_db


def _normalized_payload(payload):
    return json.loads(json.dumps(payload, cls=DjangoJSONEncoder))


def _login_verified_user(client, user: User) -> None:
    device = TOTPDevice.objects.create(user=user, name="pytest-otp-device")
    client.force_login(user)
    session = client.session
    session[DEVICE_ID_SESSION_KEY] = device.persistent_id
    session.save()


def test_dashboard_data_redirects_anonymous_users(client):
    response = client.get(reverse("core:dashboard_data"))

    assert response.status_code == 302
    assert response.url.startswith(reverse("accounts:login"))
    assert "next=%2Fapp%2Fdashboard%2Fdata%2F" in response.url


def test_dashboard_data_redirects_users_without_permissions(client):
    user = UserFactory()
    _login_verified_user(client, user)

    response = client.get(reverse("core:dashboard_data"))

    assert response.status_code == 302
    assert response.url == "/app/login/"


def test_dashboard_data_returns_expected_json_for_verified_user(verified_client):
    dataset = _build_service_dataset()
    fake_core_views = _fake_core_views_factory(dataset)
    fixed_now = timezone.datetime(2026, 7, 16, 12, 0, 0, tzinfo=timezone.get_current_timezone())

    with pytest.MonkeyPatch.context() as monkeypatch:
        monkeypatch.setattr("core.services.financial_dashboard._core_views", lambda: fake_core_views)
        monkeypatch.setattr("core.services.financial_dashboard.calc_inversor_settlement", _fake_settlement)
        monkeypatch.setattr("core.services.financial_dashboard.timezone.now", lambda: fixed_now)
        expected = FinancialDashboardService(dataset["user"]).build()
        response = verified_client.get(reverse("core:dashboard_data"))

    assert response.status_code == 200
    assert response["Content-Type"].startswith("application/json")
    assert response.json() == _normalized_payload(expected)


def test_dashboard_data_applies_querystring_filters(verified_client):
    dataset = _build_service_dataset()
    fake_core_views = _fake_core_views_factory(dataset)
    today = timezone.datetime(2026, 7, 16, tzinfo=timezone.get_current_timezone()).date()
    start = today.replace(day=1)
    fixed_now = timezone.datetime(2026, 7, 16, 12, 0, 0, tzinfo=timezone.get_current_timezone())
    filters = FinancialDashboardFilters.from_mapping(
        {
            "fecha_desde": start.isoformat(),
            "fecha_hasta": today.isoformat(),
            "proyecto_id": dataset["proyectos"]["activo"].id,
            "estado": "captacion",
        }
    )

    with pytest.MonkeyPatch.context() as monkeypatch:
        monkeypatch.setattr("core.services.financial_dashboard._core_views", lambda: fake_core_views)
        monkeypatch.setattr("core.services.financial_dashboard.calc_inversor_settlement", _fake_settlement)
        monkeypatch.setattr("core.services.financial_dashboard.timezone.now", lambda: fixed_now)
        expected = FinancialDashboardService(dataset["user"], filters=filters).build()
        response = verified_client.get(
            reverse("core:dashboard_data"),
            {
                "fecha_desde": start.isoformat(),
                "fecha_hasta": today.isoformat(),
                "proyecto_id": dataset["proyectos"]["activo"].id,
                "estado": "captacion",
            },
        )

    assert response.status_code == 200
    assert response.json() == _normalized_payload(expected)
    assert response.json()["filters"] == {
        "fecha_desde": start.isoformat(),
        "fecha_hasta": today.isoformat(),
        "proyecto_id": dataset["proyectos"]["activo"].id,
        "estado": "captacion",
    }
