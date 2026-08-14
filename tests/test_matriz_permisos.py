"""
Matriz de permisos: cada ruta de `/app/` contra cada rol.

Los permisos se comprueban en tres sitios —el middleware por prefijo de ruta,
las vistas por su cuenta y las plantillas al pintar las tarjetas— y basta con
que uno de los tres se olvide para abrir un hueco. Probar ruta por ruta y rol
por rol es la única forma de verlo entero; a mano se revisa lo que uno recuerda.

Así apareció que `/app/dashboard/` se abría con sólo el permiso del simulador
mientras `/app/dashboard/data/` devolvía 403: alguien protegió la API y la
página que la precede se quedó fuera.
"""

import re
from datetime import date
from decimal import Decimal

import pytest
from django.test import Client
from django.urls import get_resolver
from django.urls.resolvers import URLPattern, URLResolver

from accounts.models import UserAccess
from core.models import Cliente, InversorPerfil, Participacion, Proyecto

from .factories import UserAccessFactory, UserFactory

pytestmark = pytest.mark.django_db

# La factoría deja TODOS los `can_*` a True. Con permisos a medida hay que
# apagarlos uno a uno o el usuario los tiene todos y la prueba no prueba nada.
APAGADOS = dict(
    can_simulador=False, can_estudios=False, can_proyectos=False, can_clientes=False,
    can_inversores=False, can_usuarios=False, can_cms=False, can_facturas_preview=False,
)

# Rutas que cualquier persona con sesión puede ver: la portada del ERP decide
# qué tarjetas pinta según los permisos, y la clave pública de las
# notificaciones es pública por definición.
COMUNES = {"/app/", "/app/push/public-key/", "/app/push/subscribe/", "/app/push/unsubscribe/"}


def _sesion_verificada(client, user):
    from django_otp.plugins.otp_totp.models import TOTPDevice

    dispositivo = TOTPDevice.objects.create(user=user, name="test", confirmed=True)
    client.force_login(user)
    sesion = client.session
    sesion["otp_device_id"] = dispositivo.persistent_id
    sesion.save()


def _rutas_app():
    def recorrer(resolver, prefijo=""):
        for patron in resolver.url_patterns:
            if isinstance(patron, URLResolver):
                yield from recorrer(patron, prefijo + str(patron.pattern))
            elif isinstance(patron, URLPattern):
                yield prefijo + str(patron.pattern)

    return sorted({r for r in recorrer(get_resolver()) if r.startswith("app/")})


def _concretar(patron, valores):
    """Sustituye los argumentos de la ruta por identificadores que existen."""
    ruta = "/" + patron
    for arg in re.findall(r"<([^>]+)>", ruta):
        nombre = arg.split(":")[-1]
        if nombre not in valores:
            return None
        ruta = ruta.replace("<" + arg + ">", str(valores[nombre]))
    return None if "<" in ruta else ruta


def test_quien_solo_tiene_el_simulador_no_llega_a_nada_mas():
    proyecto = Proyecto.objects.create(
        nombre="AUDITORÍA", direccion="C/ X 1", precio_compra_inmueble=Decimal("100000")
    )
    cliente = Cliente.objects.create(nombre="Cliente", dni_cif="00000000T", email="a@b.c")
    perfil = InversorPerfil.objects.create(cliente=cliente)
    participacion = Participacion.objects.create(
        proyecto=proyecto, cliente=cliente, importe_invertido=Decimal("1000"),
        estado="confirmada", contrato_fecha=date(2026, 1, 1),
    )
    valores = {
        "proyecto_id": proyecto.id, "pk": proyecto.id, "id": proyecto.id,
        "cliente_id": cliente.id, "participacion_id": participacion.id,
        "perfil_id": perfil.id, "inversor_id": perfil.id, "documento_id": 1,
        "gasto_id": 1, "ingreso_id": 1, "solicitud_id": 1, "user_id": 1,
        "estudio_id": 1, "sorteo_id": 1, "beneficio_id": 1, "token": "x" * 64,
        "slug": "x", "categoria": "otros", "tipo": "otros",
    }

    usuario = UserFactory()
    UserAccessFactory(user=usuario, role="", use_custom_perms=True, **{**APAGADOS, "can_simulador": True})
    navegador = Client()
    _sesion_verificada(navegador, usuario)

    alcanzadas = []
    for patron in _rutas_app():
        ruta = _concretar(patron, valores)
        if not ruta or ruta.startswith(("/app/login", "/app/logout", "/app/inversor/")):
            continue
        if ruta in COMUNES or ruta.startswith("/app/simulador"):
            continue
        if navegador.get(ruta).status_code == 200:
            alcanzadas.append(ruta)

    assert alcanzadas == [], "alcanza sin permiso: {}".format(alcanzadas)


def test_clientes_e_inversores_solo_para_direccion():
    """Son las dos secciones con datos personales: DNI, domicilio e IBAN."""
    navegadores = {}
    for nombre, kwargs in [
        ("direccion", dict(role=UserAccess.ROLE_DIRECCION, use_custom_perms=False)),
        ("marketing", dict(role=UserAccess.ROLE_MARKETING, use_custom_perms=False)),
        ("comercial", dict(role=UserAccess.ROLE_COMERCIAL, use_custom_perms=False)),
    ]:
        usuario = UserFactory()
        UserAccessFactory(user=usuario, **kwargs)
        navegador = Client()
        _sesion_verificada(navegador, usuario)
        navegadores[nombre] = navegador

    for ruta in ("/app/clientes/", "/app/inversores/"):
        assert navegadores["direccion"].get(ruta).status_code == 200, ruta
        for rol in ("marketing", "comercial"):
            assert navegadores[rol].get(ruta).status_code == 302, "{} llega a {}".format(rol, ruta)


def test_la_lista_de_inversores_no_consulta_mas_por_tener_mas_inversores():
    """
    Hacía un `get_or_create` por cliente: una consulta por cada uno en cada
    visita, y además una escritura en una petición GET. Con 30 inversores eran
    168 consultas; con 60 habrían sido el doble.

    Se mide la segunda visita a propósito: en la primera puede haber perfiles
    que crear, que es un coste de una vez. Lo que no puede crecer es lo que se
    paga en cada visita.
    """
    from django.db import connection, reset_queries
    from django.test.utils import override_settings

    usuario = UserFactory()
    UserAccessFactory(user=usuario, role=UserAccess.ROLE_DIRECCION, use_custom_perms=False)
    navegador = Client()
    _sesion_verificada(navegador, usuario)

    consultas = {}
    for cuantos in (5, 40):
        Cliente.objects.all().delete()
        for i in range(cuantos):
            Cliente.objects.create(nombre="Inversor {:03d}".format(i), dni_cif="{:08d}Z".format(i))
        with override_settings(DEBUG=True):
            navegador.get("/app/inversores/")   # crea los perfiles que falten
            reset_queries()
            respuesta = navegador.get("/app/inversores/")
            consultas[cuantos] = len(connection.queries)
        assert respuesta.status_code == 200

    assert consultas[5] == consultas[40], (
        "la lista consulta más por tener más inversores: {} con 5, {} con 40".format(
            consultas[5], consultas[40]
        )
    )


def test_el_perfil_del_inversor_se_crea_con_su_token():
    """
    Al optimizar la lista probé con `bulk_create`, que se salta `save()` — y el
    token del portal se genera justo ahí. Los perfiles salían sin token y el
    enlace al portal reventaba al construirlo.
    """
    from core.models import InversorPerfil

    usuario = UserFactory()
    UserAccessFactory(user=usuario, role=UserAccess.ROLE_DIRECCION, use_custom_perms=False)
    navegador = Client()
    _sesion_verificada(navegador, usuario)

    Cliente.objects.create(nombre="Sin perfil todavía", dni_cif="12345678Z")
    assert navegador.get("/app/inversores/").status_code == 200

    perfiles = list(InversorPerfil.objects.all())
    assert perfiles, "la lista debe crear el perfil que falte"
    for perfil in perfiles:
        assert perfil.token, "un perfil sin token rompe el enlace a su portal"
        assert len(perfil.token) >= 32


@pytest.mark.parametrize("ruta", ["/app/proyectos/", "/app/dashboard/"])
def test_las_pantallas_no_consultan_mas_por_tener_mas_proyectos(ruta):
    """
    Las dos crecían dos consultas por proyecto.

    En el listado, `_resultado_desde_memoria` recorre los gastos y los ingresos
    de cada proyecto; su propio comentario dice «aprovecha prefetch si existe»,
    pero nadie se lo daba.

    En el panel financiero el servicio sí los precargaba, y aun así se pedían
    uno por uno: `_beneficio_estimado_real_memoria` consultaba con
    `objects.filter(proyecto=...)` en vez de por el gestor de la relación, y
    así se saltaba el prefetch que ya estaba hecho.
    """
    from datetime import date

    from django.db import connection, reset_queries
    from django.test.utils import override_settings

    from core.models import GastoProyecto, IngresoProyecto

    usuario = UserFactory()
    UserAccessFactory(user=usuario, role=UserAccess.ROLE_DIRECCION, use_custom_perms=False)
    navegador = Client()
    _sesion_verificada(navegador, usuario)

    consultas = {}
    creados = 0
    for total in (5, 40):
        for i in range(creados, total):
            proyecto = Proyecto.objects.create(
                nombre="Proyecto {:03d}".format(i), precio_compra_inmueble=Decimal("100000")
            )
            GastoProyecto.objects.create(
                proyecto=proyecto, importe=Decimal("10"), estado="confirmado",
                categoria="otros", fecha=date(2026, 1, 1), concepto="x",
            )
            IngresoProyecto.objects.create(
                proyecto=proyecto, importe=Decimal("20"), estado="confirmado",
                fecha=date(2026, 1, 1), concepto="y",
            )
        creados = total
        with override_settings(DEBUG=True):
            navegador.get(ruta)
            reset_queries()
            respuesta = navegador.get(ruta)
            consultas[total] = len(connection.queries)
        assert respuesta.status_code == 200

    assert consultas[5] == consultas[40], (
        "{} consulta más por tener más proyectos: {} con 5, {} con 40".format(
            ruta, consultas[5], consultas[40]
        )
    )
