"""
Quién entra a clientes, a inversores y a los datos del panel.

Estas vistas dependían solo del middleware, que exige estar autenticado con
**cualquier** permiso del ERP. `home.html` sí escondía las tarjetas según
`can_clientes`, `can_inversores` y `can_proyectos`, así que el menú decía una
cosa y el servidor otra: bastaba escribir la URL.
"""

import pytest
from django.contrib.messages.storage.fallback import FallbackStorage
from django.contrib.sessions.middleware import SessionMiddleware
from django.test import RequestFactory

from accounts.models import UserAccess
from accounts.utils import resolve_permissions
from core import views as core_views

from .factories import UserAccessFactory, UserFactory

pytestmark = pytest.mark.django_db


def _peticion(user, metodo="get"):
    request = getattr(RequestFactory(), metodo)("/x/")
    request.user = user
    SessionMiddleware(lambda r: None).process_request(request)
    request.session.save()
    request._messages = FallbackStorage(request)
    return request


def _usuario(**acceso):
    user = UserFactory()
    UserAccessFactory(user=user, **acceso)
    return user


SOLO_ESTUDIOS = {
    "use_custom_perms": True,
    "role": "",
    "can_simulador": True,
    "can_estudios": True,
    "can_proyectos": False,
    "can_clientes": False,
    "can_inversores": False,
    "can_usuarios": False,
    "can_cms": False,
}


@pytest.mark.parametrize(
    "vista",
    ["clientes", "clientes_form", "clientes_import", "inversores_list", "inversor_buscar"],
)
def test_sin_permiso_de_area_no_se_entra(vista):
    """El agujero que se cierra: alguien de estudios escribiendo la URL."""
    respuesta = getattr(core_views, vista)(_peticion(_usuario(**SOLO_ESTUDIOS)))
    assert respuesta.status_code == 302


@pytest.mark.parametrize("vista", ["dashboard_data"])
def test_los_endpoints_json_responden_403_y_no_redirigen(vista):
    """
    Un 302 a una llamada de JavaScript llega como HTML donde se espera JSON y
    el error sale por otro lado. Aquí toca 403.
    """
    respuesta = getattr(core_views, vista)(_peticion(_usuario(**SOLO_ESTUDIOS)))
    assert respuesta.status_code == 403
    assert respuesta["Content-Type"].startswith("application/json")


def test_las_comunicaciones_a_inversores_tambien():
    user = _usuario(**SOLO_ESTUDIOS)
    respuesta = core_views.inversor_comunicacion_send(_peticion(user, "post"), perfil_id=1)
    assert respuesta.status_code == 403


def test_direccion_sigue_entrando():
    """Lo que de verdad hay que no romper."""
    user = _usuario(role=UserAccess.ROLE_DIRECCION, use_custom_perms=False)
    assert core_views.clientes(_peticion(user)).status_code == 200
    assert core_views.inversores_list(_peticion(user)).status_code == 200


def test_comercial_no_entra_a_clientes_ni_a_inversores():
    """
    Cambia quién entra, y conviene que quede escrito.

    `resolve_permissions` da al rol comercial `can_simulador`, `can_estudios` y
    `can_proyectos`, y **no** `can_clientes` ni `can_inversores`. El menú ya le
    escondía esas dos tarjetas; lo único que pasaba es que el servidor le dejaba
    entrar escribiendo la URL.

    Si un comercial debe gestionar clientes —que es discutible y es una decisión
    de negocio, no técnica— lo que hay que cambiar es la tabla de permisos en
    `accounts/utils.py`, no volver a abrir la puerta aquí.
    """
    user = _usuario(role=UserAccess.ROLE_COMERCIAL, use_custom_perms=False)
    assert core_views.clientes(_peticion(user)).status_code == 302
    assert core_views.inversores_list(_peticion(user)).status_code == 302
    # Lo suyo sí lo conserva.
    assert resolve_permissions(user)["can_proyectos"] is True


def test_el_menu_y_el_servidor_deciden_lo_mismo():
    """
    Las tarjetas de `home.html` se pintan con `can_clientes`, `can_inversores` y
    `can_proyectos`. Si el control mirase otra cosa, volveríamos a tener un
    enlace que no lleva a ningún sitio, o una puerta sin enlace.
    """
    casos = [
        SOLO_ESTUDIOS,
        {"role": UserAccess.ROLE_MARKETING, "use_custom_perms": False},
        {"role": UserAccess.ROLE_COMERCIAL, "use_custom_perms": False},
        {"role": UserAccess.ROLE_MODERATORS, "use_custom_perms": False},
    ]
    for acceso in casos:
        user = _usuario(**acceso)
        perms = resolve_permissions(user)
        assert core_views._user_can_view_clientes(user) == bool(perms["can_clientes"])
        assert core_views._user_can_view_inversores(user) == bool(perms["can_inversores"])
        assert core_views._user_can_view_proyectos(user) == bool(perms["can_proyectos"])


def test_no_queda_ninguna_ruta_de_core_sin_control():
    """
    Cruza `core/urls.py` con el cuerpo de cada vista. Las únicas que pueden
    quedarse sin comprobar permisos son las del portal del inversor, que van por
    token —esa es su credencial—, y el service worker, que es un fichero .js sin
    datos. Cualquier otra que aparezca aquí es un descuido.
    """
    import ast
    import re
    from pathlib import Path

    raiz = Path(core_views.__file__).resolve().parent
    rutas = dict(
        (m.group(2), m.group(1))
        for m in re.finditer(r'path\(\s*"([^"]*)"\s*,\s*views\.(\w+)', (raiz / "urls.py").read_text("utf-8"))
    )
    fuente = (raiz / "views.py").read_text("utf-8")
    cuerpos = {
        n.name: "\n".join(fuente.splitlines()[n.lineno - 1 : n.end_lineno])
        for n in ast.parse(fuente).body
        if isinstance(n, ast.FunctionDef)
    }
    señales = ("_user_can", "resolve_permissions", "is_admin_user", "InversorPerfil, token")

    sin_control = sorted(
        nombre for nombre in rutas if nombre in cuerpos and not any(s in cuerpos[nombre] for s in señales)
    )
    assert sin_control == ["inversor_service_worker"], "rutas sin control: {}".format(sin_control)
