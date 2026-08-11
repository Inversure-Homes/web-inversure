"""
Quién entra al simulador, al listado de estudios y a sus informes.

Hasta ahora estas tres pantallas no comprobaban nada: bastaba con tener
cualquier permiso del ERP y escribir la URL. `home.html` sí escondía las
tarjetas según `can_simulador` y `can_estudios`, así que el menú decía una cosa
y el servidor otra.
"""

import pytest
from django.contrib.messages.storage.fallback import FallbackStorage
from django.contrib.sessions.middleware import SessionMiddleware
from django.test import RequestFactory

from accounts.models import UserAccess
from core import views as core_views

from .factories import EstudioFactory, UserAccessFactory, UserFactory

pytestmark = pytest.mark.django_db


def _peticion(user, ruta="/"):
    request = RequestFactory().get(ruta)
    request.user = user
    SessionMiddleware(lambda r: None).process_request(request)
    request.session.save()
    request._messages = FallbackStorage(request)
    return request


def _usuario(**acceso):
    user = UserFactory()
    UserAccessFactory(user=user, **acceso)
    return user


SOLO_CLIENTES = {
    "use_custom_perms": True,
    "role": "",
    "can_simulador": False,
    "can_estudios": False,
    "can_proyectos": False,
    "can_clientes": True,
}


@pytest.mark.parametrize("vista", ["simulador", "lista_estudio"])
def test_sin_permiso_no_se_entra(vista):
    """El agujero que se cierra: un usuario de clientes escribiendo la URL."""
    request = _peticion(_usuario(**SOLO_CLIENTES))
    respuesta = getattr(core_views, vista)(request)
    assert respuesta.status_code == 302


def test_sin_permiso_tampoco_se_baja_el_informe():
    estudio = EstudioFactory(datos={"valor_adquisicion": 100000})
    request = _peticion(_usuario(**SOLO_CLIENTES))
    assert core_views.pdf_estudio_preview(request, estudio.id).status_code == 302


def test_marketing_ve_los_estudios_pero_no_el_simulador():
    """
    No es un matiz nuestro: `resolve_permissions` le da `can_estudios` y le
    niega `can_simulador`. Las dos pantallas van por permisos distintos y el
    control tiene que respetarlo.
    """
    user = _usuario(role=UserAccess.ROLE_MARKETING, use_custom_perms=False)

    assert core_views.lista_estudio(_peticion(user)).status_code == 200
    assert core_views.simulador(_peticion(user)).status_code == 302


def test_moderadores_no_entran_a_estudios():
    """Tienen `can_proyectos`, que no es lo mismo. Copiar el helper de
    proyectos para estudios les daba acceso por error."""
    user = _usuario(role=UserAccess.ROLE_MODERATORS, use_custom_perms=False)
    assert core_views.lista_estudio(_peticion(user)).status_code == 302


@pytest.mark.parametrize("rol", [UserAccess.ROLE_DIRECCION, UserAccess.ROLE_COMERCIAL])
def test_quien_ya_entraba_sigue_entrando(rol):
    user = _usuario(role=rol, use_custom_perms=False)
    assert core_views.simulador(_peticion(user)).status_code == 200
    assert core_views.lista_estudio(_peticion(user)).status_code == 200


def test_el_menu_y_el_servidor_dicen_lo_mismo():
    """
    Las tarjetas de `home.html` se pintan con `can_simulador` y `can_estudios`.
    Si el control del servidor mirase otra cosa, volveríamos a tener un enlace
    que no lleva a ningún sitio o una puerta sin enlace.
    """
    from accounts.utils import resolve_permissions

    for acceso in (SOLO_CLIENTES, {"role": UserAccess.ROLE_MARKETING, "use_custom_perms": False}):
        user = _usuario(**acceso)
        perms = resolve_permissions(user)
        assert core_views._user_can_use_simulador(user) == bool(perms["can_simulador"])
        assert core_views._user_can_view_estudio(user) == bool(perms["can_estudios"])


def test_el_listado_no_ofrece_botones_que_rebotan():
    """
    Marketing entra al listado pero no al simulador. Si «Abrir» siguiera ahí,
    cada tarjeta llevaría a un rebote a la portada; se le ofrece el informe.
    """
    EstudioFactory(guardado=True, datos={"valor_adquisicion": 100000})
    user = _usuario(role=UserAccess.ROLE_MARKETING, use_custom_perms=False)

    html = core_views.lista_estudio(_peticion(user)).content.decode()

    assert "Informe PDF" in html
    assert "estudio_id=" not in html
    # El nombre de la clase también aparece en el JS del manejador: lo que
    # se comprueba es que no haya botón, no que no se mencione.
    assert "btn-outline-danger btn-sm js-borrar-estudio" not in html


def test_quien_puede_simular_conserva_abrir_y_borrar():
    EstudioFactory(guardado=True, datos={"valor_adquisicion": 100000})
    user = _usuario(role=UserAccess.ROLE_DIRECCION, use_custom_perms=False)

    html = core_views.lista_estudio(_peticion(user)).content.decode()

    assert "estudio_id=" in html
    assert "btn-outline-danger btn-sm js-borrar-estudio" in html
    assert "Informe PDF" in html
