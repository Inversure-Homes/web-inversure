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


def test_el_boton_esta_tambien_en_el_javascript():
    """
    La tabla de participaciones la repinta `proyecto.js` con `innerHTML` nada
    más cargar, así que la fila del servidor se ve un instante y desaparece. Un
    botón que solo esté en la plantilla de Django no llega a existir: hay que
    ponerlo en los dos sitios.

    Lo descubrí en producción, no aquí: los tests prueban la vista, no lo que
    el navegador acaba pintando.
    """
    from pathlib import Path

    raiz = Path(__file__).resolve().parent.parent
    js = (raiz / "core" / "static" / "core" / "proyecto.js").read_text("utf-8")
    plantilla = (raiz / "core" / "templates" / "core" / "proyecto.html").read_text("utf-8")

    assert "/contrato/" in js, "el JS repinta la tabla y se comería el botón"
    # El botón ya no depende del tipo de proyecto: todos los inversores tienen
    # contrato. Cuál se emite lo decide la vista, que es donde está el criterio.
    assert "esConciertos ?" not in js.split("/contrato/")[0].rsplit("<td", 1)[-1]
    assert "core:contrato_prestamo" in plantilla, "y también en el primer pintado del servidor"


# --- Cuenta en participación (proyectos inmobiliarios) ---------------------


def _escenario_inmobiliario():
    proyecto = Proyecto.objects.create(
        nombre="MADRID",
        direccion="C/ Ariza 142",
        precio_compra_inmueble=Decimal("135000"),
        precio_venta_estimado=Decimal("178700"),
    )
    cliente = Cliente.objects.create(
        nombre="Alejandro Vergara",
        dni_cif="26261870X",
        email="a@ejemplo.com",
        direccion_postal="Málaga",
    )
    participacion = Participacion.objects.create(
        proyecto=proyecto,
        cliente=cliente,
        importe_invertido=Decimal("7500"),
        porcentaje_participacion=Decimal("5.30"),
        estado="confirmada",
        contrato_fecha=date(2026, 2, 12),
        contrato_meses=6,
    )
    return proyecto, participacion


def test_un_proyecto_inmobiliario_no_genera_un_prestamo():
    """
    La diferencia no es de formato. La cláusula 1.2 del contrato de cuenta
    partícipe niega expresamente que la relación sea un préstamo o un crédito,
    y de eso dependen el tratamiento fiscal y que la pérdida del partícipe se
    limite a su aportación. Emitir el documento equivocado cambiaría la
    naturaleza jurídica de la operación.
    """
    proyecto, participacion = _escenario_inmobiliario()
    jefe = _usuario(role=UserAccess.ROLE_DIRECCION, use_custom_perms=False)

    html = core_views.contrato_prestamo(
        _peticion(jefe, "/x/?html=1"), proyecto_id=proyecto.id, participacion_id=participacion.id
    ).content.decode()

    assert "CUENTA PARTÍCIPE" in html
    assert "239 y siguientes del Código de Comercio" in html
    assert "CONTRATO DE PRÉSTAMO" not in html
    assert "calendario de liquidaciones" not in html


def test_conciertos_sigue_generando_el_prestamo():
    proyecto, participacion = _escenario()  # crea el proyecto con extra tipo conciertos
    jefe = _usuario(role=UserAccess.ROLE_DIRECCION, use_custom_perms=False)

    html = core_views.contrato_prestamo(
        _peticion(jefe, "/x/?html=1"), proyecto_id=proyecto.id, participacion_id=participacion.id
    ).content.decode()

    assert "CONTRATO DE PRÉSTAMO" in html
    assert "CUENTA PARTÍCIPE" not in html


def test_el_contrato_inmobiliario_lleva_las_cifras_del_proyecto():
    proyecto, participacion = _escenario_inmobiliario()
    jefe = _usuario(role=UserAccess.ROLE_DIRECCION, use_custom_perms=False)

    html = core_views.contrato_prestamo(
        _peticion(jefe, "/x/?html=1"), proyecto_id=proyecto.id, participacion_id=participacion.id
    ).content.decode()

    for esperado in [
        "CIENTO TREINTA Y CINCO MIL EUROS",  # valor de adquisición en letra
        "178.700,00",  # precio de venta estimado
        "SIETE MIL QUINIENTOS EUROS",  # aportación en letra
        "5,30",  # porcentaje de participación
        "DIEZ MIL EUROS",  # participación mínima
        "ES41 0081 1508 1600 0146 1056",  # cuenta del gestor
        "Aportación cuenta partícipe",  # concepto para conciliar el ingreso
    ]:
        assert esperado in html, esperado


def test_lleva_los_dos_anexos():
    proyecto, participacion = _escenario_inmobiliario()
    jefe = _usuario(role=UserAccess.ROLE_DIRECCION, use_custom_perms=False)

    html = core_views.contrato_prestamo(
        _peticion(jefe, "/x/?html=1"), proyecto_id=proyecto.id, participacion_id=participacion.id
    ).content.decode()

    assert "ANEXO I" in html
    assert "PROTECCIÓN DE DATOS" in html
    assert "Agencia Española de Protección de Datos" in html


def test_la_perdida_del_participe_queda_limitada():
    """Es la protección esencial del partícipe y tiene que estar escrita."""
    proyecto, participacion = _escenario_inmobiliario()
    jefe = _usuario(role=UserAccess.ROLE_DIRECCION, use_custom_perms=False)

    html = core_views.contrato_prestamo(
        _peticion(jefe, "/x/?html=1"), proyecto_id=proyecto.id, participacion_id=participacion.id
    ).content.decode()

    assert "limitada a las Aportaciones efectuadas" in html
