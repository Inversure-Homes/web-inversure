"""
La edición del beneficio de una participación.

Escribe el beneficio de esa participación y, en `proyecto.extra`, el beneficio
bruto, la comisión y el impuesto de sociedades del proyecto entero: lo que ven
todos sus inversores. Antes colgaba de `/app/inversor/<token>/…`, la zona que
el middleware exime del login para el portal del inversor, así que cualquiera
con el enlace de un inversor podía mandar el POST.
"""

import pytest
from django.contrib.messages.storage.fallback import FallbackStorage
from django.contrib.sessions.middleware import SessionMiddleware
from django.test import RequestFactory
from django.urls import resolve, reverse
from django.urls.exceptions import Resolver404

from accounts.models import UserAccess
from core import views as core_views
from core.models import Cliente, InversorPerfil, Participacion, Proyecto

from .factories import UserFactory

pytestmark = pytest.mark.django_db


def _escenario():
    proyecto = Proyecto.objects.create(nombre="COIN")
    cliente = Cliente.objects.create(nombre="Ana Ruiz", dni_cif="00000001R", email="ana@ejemplo.com")
    perfil = InversorPerfil.objects.create(cliente=cliente)
    participacion = Participacion.objects.create(
        proyecto=proyecto, cliente=cliente, importe_invertido=10000, estado="confirmada"
    )
    return proyecto, perfil, participacion


def _peticion(user, datos):
    request = RequestFactory().post("/x/", datos)
    request.user = user
    SessionMiddleware(lambda r: None).process_request(request)
    request.session.save()
    request._messages = FallbackStorage(request)
    return request


def _usuario(**acceso):
    user = UserFactory()
    from .factories import UserAccessFactory

    UserAccessFactory(user=user, **acceso)
    return user


def test_la_ruta_sale_de_la_zona_publica():
    """
    El middleware exime del login todo lo que empieza por `/app/inversor/`.
    Esta vista escribe cifras del proyecto: no puede vivir ahí.
    """
    ruta = reverse("core:inversor_beneficio_update", args=[1, 2])
    assert not ruta.startswith("/app/inversor/")
    assert ruta.startswith("/app/inversores/")


def test_la_ruta_antigua_ya_no_existe():
    """La que estaba exenta de login. Que no resuelva es justamente el arreglo."""
    with pytest.raises(Resolver404):
        resolve("/app/inversor/un-token-cualquiera/beneficio/1/")


def test_sin_permiso_no_se_escribe_nada():
    proyecto, perfil, participacion = _escenario()
    mirón = _usuario(use_custom_perms=True, role="", can_proyectos=False, can_clientes=True)

    core_views.inversor_beneficio_update(
        _peticion(mirón, {"beneficio_bruto": "99999"}), perfil_id=perfil.id, participacion_id=participacion.id
    )

    proyecto.refresh_from_db()
    assert not (proyecto.extra or {}).get("beneficio_operacion_override")


def test_quien_gestiona_el_proyecto_sigue_pudiendo():
    proyecto, perfil, participacion = _escenario()
    jefe = _usuario(role=UserAccess.ROLE_DIRECCION, use_custom_perms=False)

    core_views.inversor_beneficio_update(
        _peticion(jefe, {"beneficio_bruto": "12345"}), perfil_id=perfil.id, participacion_id=participacion.id
    )

    proyecto.refresh_from_db()
    assert proyecto.extra["beneficio_operacion_override"]["beneficio_bruto"] == 12345.0


def test_un_anonimo_tampoco():
    from django.contrib.auth.models import AnonymousUser

    proyecto, perfil, participacion = _escenario()

    core_views.inversor_beneficio_update(
        _peticion(AnonymousUser(), {"beneficio_bruto": "77777"}),
        perfil_id=perfil.id,
        participacion_id=participacion.id,
    )

    proyecto.refresh_from_db()
    assert not (proyecto.extra or {}).get("beneficio_operacion_override")
