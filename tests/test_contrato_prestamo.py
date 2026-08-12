"""
El contrato de préstamo de los inversores de Conciertos.

Se genera a partir de los datos del sistema en vez de rellenar una plantilla a
mano. La razón no es la comodidad: el contrato original traía el calendario de
liquidaciones tecleado y con la fecha de vencimiento equivocada en un año.
"""

from datetime import date
from decimal import Decimal

import pytest
from django.contrib.messages.storage.fallback import FallbackStorage
from django.contrib.sessions.middleware import SessionMiddleware
from django.test import RequestFactory

from accounts.models import UserAccess
from core import views as core_views
from core.contratos import calendario_liquidaciones, condiciones, importe_en_letra, sumar_meses
from core.models import Cliente, Participacion, Proyecto

from .factories import UserAccessFactory, UserFactory

pytestmark = pytest.mark.django_db


# --- Importe en letra ------------------------------------------------------


@pytest.mark.parametrize(
    "cifra,letra",
    [
        (50000, "CINCUENTA MIL EUROS"),
        (1, "UN EURO"),
        (21, "VEINTIÚN EUROS"),
        (31, "TREINTA Y UN EUROS"),
        (100, "CIEN EUROS"),
        (101, "CIENTO UN EUROS"),
        (1000, "MIL EUROS"),
        (21000, "VEINTIÚN MIL EUROS"),
        (1000000, "UN MILLÓN DE EUROS"),
        (2000000, "DOS MILLONES DE EUROS"),
    ],
)
def test_la_cantidad_en_letra_concuerda(cifra, letra):
    """
    En un contrato manda la letra si discrepa de la cifra, así que «UNO EURO» o
    «VEINTIUNO EUROS» no valen: delante del sustantivo se apocopa.
    """
    assert importe_en_letra(cifra) == letra


def test_los_centimos_tambien():
    assert importe_en_letra(Decimal("15500.50")) == "QUINCE MIL QUINIENTOS EUROS CON CINCUENTA CÉNTIMOS"
    assert importe_en_letra(Decimal("71.01")) == "SETENTA Y UN EUROS CON UN CÉNTIMO"


# --- Fechas ----------------------------------------------------------------


def test_el_vencimiento_cae_un_año_despues():
    """
    El contrato original decía «firmado el 23 de junio de 2026, vencerá el 24 de
    junio de 2026»: doce meses después es 2027. Calculado no puede pasar.
    """
    assert sumar_meses(date(2026, 6, 23), 12) == date(2027, 6, 23)


def test_los_meses_cortos_no_desbordan():
    assert sumar_meses(date(2026, 1, 31), 1) == date(2026, 2, 28)


def test_el_calendario_sale_bimensual():
    periodos = calendario_liquidaciones(date(2026, 6, 23), 12)
    assert len(periodos) == 6
    assert [p["vencimiento"] for p in periodos] == [
        date(2026, 8, 23),
        date(2026, 10, 23),
        date(2026, 12, 23),
        date(2027, 2, 23),
        date(2027, 4, 23),
        date(2027, 6, 23),
    ]


# --- El documento ----------------------------------------------------------


def _escenario(importe="50000"):
    proyecto = Proyecto.objects.create(nombre="Conciertos", extra={"tipo": "conciertos"})
    cliente = Cliente.objects.create(
        nombre="Jorge de Diego",
        dni_cif="74866847-F",
        email="j@ejemplo.com",
        iban="ES68 2103 0280 4700 1000 9172",
        direccion_postal="Madrid",
        estado_civil="soltero",
        profesion="funcionario",
    )
    participacion = Participacion.objects.create(
        proyecto=proyecto,
        cliente=cliente,
        importe_invertido=Decimal(importe),
        estado="confirmada",
        contrato_fecha=date(2026, 6, 23),
    )
    return proyecto, participacion


def _peticion(user, ruta="/x/"):
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


def test_los_intereses_cuadran():
    _, participacion = _escenario()
    c = condiciones(participacion)
    assert c["importe_por_periodo"] == Decimal("2500.00")
    assert c["intereses_totales"] == Decimal("15000.00")
    assert c["interes_total_pct"] == Decimal("30")
    assert c["vencimiento"] == date(2027, 6, 23)


def test_el_contrato_lleva_los_datos_de_las_dos_partes():
    proyecto, participacion = _escenario()
    jefe = _usuario(role=UserAccess.ROLE_DIRECCION, use_custom_perms=False)

    html = core_views.contrato_prestamo(
        _peticion(jefe, "/x/?html=1"), proyecto_id=proyecto.id, participacion_id=participacion.id
    ).content.decode()

    for esperado in [
        "Jorge de Diego",
        "74866847-F",
        "ES68 2103 0280 4700 1000 9172",
        "INVERSURE HOMES S.L.",
        "B-75265843",
        "CINCUENTA MIL EUROS",
        "23 de junio de 2027",
        "23/08/2026",
        "23/06/2027",
    ]:
        assert esperado in html, esperado


def test_lleva_el_anexo_de_proteccion_de_datos():
    proyecto, participacion = _escenario()
    jefe = _usuario(role=UserAccess.ROLE_DIRECCION, use_custom_perms=False)

    html = core_views.contrato_prestamo(
        _peticion(jefe, "/x/?html=1"), proyecto_id=proyecto.id, participacion_id=participacion.id
    ).content.decode()

    assert "PROTECCIÓN DE DATOS" in html
    assert "2016/679" in html
    assert "Agencia Española de Protección de Datos" in html
    # Las casillas de marketing son voluntarias y deben decirlo.
    assert "voluntarias" in html


def test_sale_en_pdf():
    proyecto, participacion = _escenario()
    jefe = _usuario(role=UserAccess.ROLE_DIRECCION, use_custom_perms=False)

    r = core_views.contrato_prestamo(_peticion(jefe), proyecto_id=proyecto.id, participacion_id=participacion.id)
    assert r["Content-Type"] == "application/pdf"
    assert r.content[:5] == b"%PDF-"


def test_sin_acceso_al_proyecto_no_hay_contrato():
    """Lleva DNI, domicilio y cuenta bancaria del inversor."""
    proyecto, participacion = _escenario()
    mirón = _usuario(use_custom_perms=True, role="", can_proyectos=False, can_clientes=True)

    r = core_views.contrato_prestamo(_peticion(mirón), proyecto_id=proyecto.id, participacion_id=participacion.id)
    assert r.status_code == 302
