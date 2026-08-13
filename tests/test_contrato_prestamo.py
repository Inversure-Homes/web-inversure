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
    """Seis períodos de dos meses en un año. Las fechas exactas, más abajo."""
    periodos = calendario_liquidaciones(date(2026, 6, 23), 12)
    assert len(periodos) == 6
    assert [(p["desde_mes"], p["hasta_mes"]) for p in periodos] == [(1, 2), (3, 4), (5, 6), (7, 8), (9, 10), (11, 12)]


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
        "01/09/2026",
        "01/07/2027",
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


# --- Calendario en día 1 ---------------------------------------------------


def test_las_liquidaciones_caen_en_dia_1():
    """
    Es como Inversure lo venía haciendo a mano. El contrato de Jorge de Diego,
    firmado el 23/06/2026, liquidaba el 01/09 y no el 23/08. Pagar siempre en
    día 1 cuadra con la tesorería; el aniversario de la firma no le importa a
    nadie.
    """
    assert [p["vencimiento"] for p in calendario_liquidaciones(date(2026, 6, 23), 12)] == [
        date(2026, 9, 1),
        date(2026, 11, 1),
        date(2027, 1, 1),
        date(2027, 3, 1),
        date(2027, 5, 1),
        date(2027, 7, 1),
    ]


def test_firmando_en_dia_1_no_se_pierde_un_mes():
    """Si el período ya termina en día 1, ese mismo es el vencimiento."""
    assert [p["vencimiento"] for p in calendario_liquidaciones(date(2026, 9, 1), 12)] == [
        date(2026, 11, 1),
        date(2027, 1, 1),
        date(2027, 3, 1),
        date(2027, 5, 1),
        date(2027, 7, 1),
        date(2027, 9, 1),
    ]


def test_el_cambio_de_año_no_se_tuerce():
    from core.contratos import primero_de_mes_siguiente

    assert primero_de_mes_siguiente(date(2026, 12, 15)) == date(2027, 1, 1)
    assert primero_de_mes_siguiente(date(2026, 12, 1)) == date(2026, 12, 1)


# --- Baja del inversor -----------------------------------------------------


def test_lo_devengado_va_por_meses_al_2_5_por_ciento():
    """
    Al salir antes de tiempo se devenga por meses a la mitad del tipo
    bimensual: 2,5 % mensual. No es lo mismo que contar períodos completos —
    quien lleva siete meses cobra siete, no seis— y la diferencia es dinero.
    """
    from core.contratos import intereses_devengados

    _proyecto, participacion = _escenario()  # 50.000 € al 5 % bimensual desde el 23/06/2026

    # Dos meses justos: 2 × 2,5 % × 50.000.
    assert intereses_devengados(participacion, date(2026, 8, 23)) == Decimal("2500")
    # Siete meses: antes salían tres períodos (7.500 €), ahora siete meses.
    assert intereses_devengados(participacion, date(2027, 1, 23)) == Decimal("8750")
    # Nunca pasa del plazo pactado.
    assert intereses_devengados(participacion, date(2030, 1, 1)) == Decimal("15000")


def test_los_dias_sueltos_no_cuentan():
    """
    Criterio de Inversure: se pagan meses completos. Los días del último mes no
    se prorratean, salvo que se pida expresamente.
    """
    from core.contratos import intereses_devengados

    _proyecto, participacion = _escenario()  # 50.000 € desde el 23/06/2026
    hasta = date(2026, 9, 1)  # dos meses y nueve días

    assert intereses_devengados(participacion, hasta) == Decimal("2500")
    assert intereses_devengados(participacion, hasta, prorratear_dias=True) > Decimal("2500")


def test_el_acuerdo_de_resolucion_lleva_el_finiquito():
    """
    Sin la cláusula de finiquito, alguien puede cobrar y reclamar después. Es
    la razón de ser del documento.
    """
    proyecto, participacion = _escenario()
    jefe = _usuario(role=UserAccess.ROLE_DIRECCION, use_custom_perms=False)

    html = core_views.contrato_rescision(
        _peticion(jefe, "/x/?html=1&fecha=2026-09-01"),
        proyecto_id=proyecto.id,
        participacion_id=participacion.id,
    ).content.decode()

    assert "finiquitado" in html
    assert "tiene que reclamar" in html
    assert "resolver de mutuo acuerdo" in html
    # Y dice por qué hace falta un acuerdo y no basta con avisar.
    assert "no contempla su terminación anticipada" in html


def test_el_acuerdo_suma_aportacion_y_devengado():
    proyecto, participacion = _escenario()  # 50.000 € al 5 % desde el 23/06/2026
    jefe = _usuario(role=UserAccess.ROLE_DIRECCION, use_custom_perms=False)

    html = core_views.contrato_rescision(
        _peticion(jefe, "/x/?html=1&fecha=2026-10-23"),
        proyecto_id=proyecto.id,
        participacion_id=participacion.id,
    ).content.decode()

    assert "50.000,00" in html  # aportación, que se devuelve íntegra
    assert "5.000,00" in html  # dos períodos devengados, en bruto

    # Sobre los intereses —y sólo sobre ellos— se retiene a cuenta del IRPF.
    # Devolver el capital no es renta, así que retener sobre él sería retener
    # sobre dinero que ya era suyo.
    assert "950,00" in html  # 19 % de 5.000
    assert "54.050,00" in html  # líquido: 50.000 + 5.000 − 950
    assert "CINCUENTA Y CUATRO MIL CINCUENTA EUROS" in html
    assert "certificado de retenciones" in html


def test_el_acuerdo_de_una_cuenta_participe_habla_de_partícipe():
    proyecto, participacion = _escenario_inmobiliario()
    jefe = _usuario(role=UserAccess.ROLE_DIRECCION, use_custom_perms=False)

    html = core_views.contrato_rescision(
        _peticion(jefe, "/x/?html=1&fecha=2026-06-01&rendimiento=1200"),
        proyecto_id=proyecto.id,
        participacion_id=participacion.id,
    ).content.decode()

    assert "EL PARTÍCIPE" in html
    assert "PRESTAMISTA" not in html
    # En una cuenta en participación el resultado no se calcula solo.
    assert "1.200,00" in html
    assert "no altera la continuidad del Negocio" in html


def test_el_boton_de_resolucion_esta_en_los_dos_sitios():
    """
    La tabla la repinta `proyecto.js` con `innerHTML`, así que un botón que
    solo esté en la plantilla de Django se ve un instante y desaparece. Ya me
    pasó con el de «Contrato».
    """
    from pathlib import Path

    raiz = Path(core_views.__file__).resolve().parent
    js = (raiz / "static" / "core" / "proyecto.js").read_text("utf-8")
    plantilla = (raiz / "templates" / "core" / "proyecto.html").read_text("utf-8")

    assert "inv-resolucion" in js
    assert "/rescision/" in js
    assert "core:contrato_rescision" in plantilla


def test_la_fecha_de_efectos_se_pide_siempre():
    """
    De ella depende cuántos meses se devengan, así que no vale dar por buena la
    de hoy sin preguntar.
    """
    from pathlib import Path

    js = (Path(core_views.__file__).resolve().parent / "static" / "core" / "proyecto.js").read_text("utf-8")
    manejador = js.split("inv-resolucion")[2]

    assert "prompt(" in manejador
    assert "AAAA-MM-DD" in manejador


def test_el_prestamo_advierte_de_la_retencion_y_desglosa_el_liquido():
    """
    El contrato prometía «5 % del principal» y la tabla enseñaba el bruto. Si
    después se ingresa un 19 % menos, el prestamista puede sostener que se le
    prometió esa cifra limpia, y la ambigüedad se interpreta contra quien
    redactó el contrato (art. 1288 CC). Por eso el papel lo dice y lo desglosa.
    """
    proyecto, participacion = _escenario()  # 50.000 € al 5 % bimensual
    jefe = _usuario(role=UserAccess.ROLE_DIRECCION, use_custom_perms=False)

    html = core_views.contrato_prestamo(
        _peticion(jefe, "/x/?html=1"),
        proyecto_id=proyecto.id,
        participacion_id=participacion.id,
    ).content.decode()

    assert "Régimen fiscal y retención a cuenta" in html
    assert "brutos" in html
    assert "certificado de retenciones" in html

    # 5 % de 50.000 = 2.500 brutos por período; 19 % = 475; líquido 2.025.
    assert "2.500,00" in html
    assert "475,00" in html
    assert "2.025,00" in html


def test_la_cuenta_participe_tambien_menciona_la_retencion():
    proyecto, participacion = _escenario_inmobiliario()
    jefe = _usuario(role=UserAccess.ROLE_DIRECCION, use_custom_perms=False)

    html = core_views.contrato_prestamo(
        _peticion(jefe, "/x/?html=1"),
        proyecto_id=proyecto.id,
        participacion_id=participacion.id,
    ).content.decode()

    assert "Retención a cuenta" in html
    assert "certificado de retenciones" in html


def test_la_retencion_no_toca_el_capital_devuelto():
    """Sin rendimiento no hay renta, y por tanto no hay nada que retener."""
    from core.contratos import condiciones_baja

    _proyecto, participacion = _escenario_inmobiliario()
    baja = condiciones_baja(participacion, date(2026, 10, 1), rendimiento=0)

    assert baja["retencion"]["retencion"] == Decimal("0")
    assert baja["total_neto"] == baja["aportacion"]


def test_los_contratos_llevan_membrete():
    proyecto, participacion = _escenario()
    jefe = _usuario(role=UserAccess.ROLE_DIRECCION, use_custom_perms=False)

    for vista, kwargs in (
        (core_views.contrato_prestamo, {}),
        (core_views.contrato_rescision, {}),
    ):
        html = vista(
            _peticion(jefe, "/x/?html=1"),
            proyecto_id=proyecto.id,
            participacion_id=participacion.id,
            **kwargs,
        ).content.decode()
        assert 'class="membrete"' in html
        # Incrustado, no enlazado: WeasyPrint no descarga recursos externos.
        assert "data:image/" in html


# --- El alta del inversor fija las condiciones del contrato ----------------


def _json(respuesta):
    """`JsonResponse` no trae `.json()`: eso lo pone el cliente de pruebas."""
    import json

    return json.loads(respuesta.content)


def _alta(user, proyecto, cliente, **campos):
    import json

    from django.test import RequestFactory

    peticion = RequestFactory().post(
        "/x/",
        data=json.dumps({"cliente_id": cliente.id, "importe_invertido": "16000", **campos}),
        content_type="application/json",
    )
    peticion.user = user
    SessionMiddleware(lambda r: None).process_request(peticion)
    peticion.session.save()
    peticion._messages = FallbackStorage(peticion)
    return core_views.proyecto_participaciones(peticion, proyecto_id=proyecto.id)


def test_el_alta_en_conciertos_deja_el_prestamo_a_doce_meses_al_cinco():
    proyecto, _ = _escenario()
    cliente = Cliente.objects.create(nombre="Juan Jesús Fernández", dni_cif="76429174J")
    jefe = _usuario(role=UserAccess.ROLE_DIRECCION, use_custom_perms=False)

    r = _alta(jefe, proyecto, cliente, fecha_aportacion="2026-09-01")
    assert r.status_code == 200
    datos = _json(r)
    assert datos["ok"] and datos["contrato"] == "prestamo"

    nueva = Participacion.objects.get(id=datos["id"])
    assert nueva.contrato_meses == 12
    assert nueva.contrato_interes_bimensual == Decimal("5")


def test_el_alta_en_un_inmobiliario_dura_lo_que_el_negocio():
    """
    El valor por defecto del modelo son doce meses, que es lo que dura un
    préstamo de Conciertos. Una cuenta en participación dura lo que el negocio,
    y dejarla en doce le habría puesto al contrato un plazo que nadie pactó.
    """
    from core.contratos import MESES_NEGOCIO

    proyecto, _ = _escenario_inmobiliario()
    cliente = Cliente.objects.create(nombre="Una inversora", dni_cif="00000000T")
    jefe = _usuario(role=UserAccess.ROLE_DIRECCION, use_custom_perms=False)

    datos = _json(_alta(jefe, proyecto, cliente))
    assert datos["contrato"] == "cuenta_participe"
    assert Participacion.objects.get(id=datos["id"]).contrato_meses == MESES_NEGOCIO


def test_el_alta_respeta_lo_que_se_haya_pactado():
    proyecto, _ = _escenario()
    cliente = Cliente.objects.create(nombre="Otro inversor", dni_cif="11111111H")
    jefe = _usuario(role=UserAccess.ROLE_DIRECCION, use_custom_perms=False)

    datos = _json(
        _alta(
            jefe, proyecto, cliente,
            fecha_aportacion="2026-09-01",
            contrato_fecha="2026-08-28",
            contrato_meses="18",
            contrato_interes_bimensual="4.5",
        )
    )

    nueva = Participacion.objects.get(id=datos["id"])
    assert nueva.contrato_fecha == date(2026, 8, 28)
    assert nueva.contrato_meses == 18
    assert nueva.contrato_interes_bimensual == Decimal("4.5")

    # Y el contrato que sale es el que se pactó, no el de por defecto.
    html = core_views.contrato_prestamo(
        _peticion(jefe, "/x/?html=1"), proyecto_id=proyecto.id, participacion_id=nueva.id
    ).content.decode()
    assert "4,50 %" in html
    assert "28 de agosto de 2026" in html


def _patch(user, proyecto, participacion, **campos):
    import json

    from django.test import RequestFactory

    peticion = RequestFactory().patch("/x/", data=json.dumps(campos), content_type="application/json")
    peticion.user = user
    SessionMiddleware(lambda r: None).process_request(peticion)
    peticion.session.save()
    peticion._messages = FallbackStorage(peticion)
    return core_views.proyecto_participacion_detalle(
        peticion, proyecto_id=proyecto.id, participacion_id=participacion.id
    )


def test_corregir_la_fecha_no_reescribe_el_plazo():
    """Mandar un campo no puede arrastrar los valores por defecto del resto."""
    proyecto, participacion = _escenario_inmobiliario()
    participacion.contrato_meses = 9
    participacion.save(update_fields=["contrato_meses"])
    jefe = _usuario(role=UserAccess.ROLE_DIRECCION, use_custom_perms=False)

    assert _patch(jefe, proyecto, participacion, contrato_fecha="2026-07-01").status_code == 200
    participacion.refresh_from_db()
    assert participacion.contrato_fecha == date(2026, 7, 1)
    assert participacion.contrato_meses == 9


def test_un_contrato_firmado_ya_no_se_puede_retocar():
    """
    La huella de la firma se calcula sobre el PDF exacto que se firmó. Cambiar
    después las condiciones dejaría un contrato firmado que ya no se puede
    reproducir, y la firma pasaría a no acreditar nada.
    """
    from core.models import FirmaContrato

    proyecto, participacion = _escenario()
    FirmaContrato.objects.create(
        participacion=participacion,
        tipo=FirmaContrato.Tipo.PRESTAMO,
        estado=FirmaContrato.Estado.FIRMADO,
    )
    jefe = _usuario(role=UserAccess.ROLE_DIRECCION, use_custom_perms=False)

    r = _patch(jefe, proyecto, participacion, contrato_interes_bimensual="1")
    assert r.status_code == 409
    participacion.refresh_from_db()
    assert participacion.contrato_interes_bimensual == Decimal("5")


def test_el_formulario_de_alta_pide_las_condiciones():
    """Si no está en la plantilla, el alta se queda con los valores por defecto."""
    from pathlib import Path

    raiz = Path(__file__).resolve().parent.parent
    plantilla = (raiz / "core" / "templates" / "core" / "proyecto.html").read_text("utf-8")
    js = (raiz / "core" / "static" / "core" / "proyecto.js").read_text("utf-8")

    for campo in ("inv_contrato_fecha", "inv_contrato_meses", "inv_contrato_interes"):
        assert campo in plantilla, campo
        assert campo in js, campo
    assert "contrato_interes_bimensual" in js


def _aprobar(user, solicitud):
    import json

    from django.test import RequestFactory

    peticion = RequestFactory().patch(
        "/x/", data=json.dumps({"estado": "aprobada", "confirm": True}), content_type="application/json"
    )
    peticion.user = user
    SessionMiddleware(lambda r: None).process_request(peticion)
    peticion.session.save()
    peticion._messages = FallbackStorage(peticion)
    return core_views.proyecto_solicitud_detalle(
        peticion, proyecto_id=solicitud.proyecto_id, solicitud_id=solicitud.id
    )


def _solicitud(proyecto, importe="20000"):
    from core.models import InversorPerfil, SolicitudParticipacion

    cliente = Cliente.objects.create(nombre="Quien solicita entrar", dni_cif="22222222J")
    perfil = InversorPerfil.objects.create(cliente=cliente)
    return SolicitudParticipacion.objects.create(
        proyecto=proyecto, inversor=perfil, importe_solicitado=Decimal(importe)
    )


def test_aprobar_una_solicitud_deja_lista_la_participacion_con_sus_condiciones():
    """La otra puerta por la que entra un inversor tiene que dejarlo igual."""
    from core.contratos import MESES_NEGOCIO

    proyecto, _ = _escenario_inmobiliario()
    solicitud = _solicitud(proyecto)
    jefe = _usuario(role=UserAccess.ROLE_DIRECCION, use_custom_perms=False)

    assert _aprobar(jefe, solicitud).status_code == 200
    nueva = Participacion.objects.get(cliente=solicitud.inversor.cliente, proyecto=proyecto)
    assert nueva.estado == "confirmada"
    assert nueva.contrato_meses == MESES_NEGOCIO


def test_aprobar_dos_veces_no_duplica_el_capital_captado():
    """
    Se podía aprobar la misma solicitud otra vez y salían dos participaciones,
    con lo que el capital captado se contaba doble.
    """
    proyecto, _ = _escenario_inmobiliario()
    solicitud = _solicitud(proyecto)
    jefe = _usuario(role=UserAccess.ROLE_DIRECCION, use_custom_perms=False)

    _aprobar(jefe, solicitud)
    _aprobar(jefe, solicitud)

    assert Participacion.objects.filter(cliente=solicitud.inversor.cliente, proyecto=proyecto).count() == 1


# --- La baja del inversor --------------------------------------------------


def _baja(user, proyecto, participacion, **campos):
    import json

    from django.test import RequestFactory

    peticion = RequestFactory().post("/x/", data=json.dumps(campos), content_type="application/json")
    peticion.user = user
    SessionMiddleware(lambda r: None).process_request(peticion)
    peticion.session.save()
    peticion._messages = FallbackStorage(peticion)
    return core_views.participacion_baja(
        peticion, proyecto_id=proyecto.id, participacion_id=participacion.id
    )


def test_generar_el_acuerdo_no_da_de_baja_a_nadie():
    """
    El acuerdo se saca para revisarlo y para que lo firmen. Si el mismo botón
    diera de baja, previsualizar un documento sacaría a alguien de la inversión
    sin haberlo pactado.
    """
    proyecto, participacion = _escenario()
    jefe = _usuario(role=UserAccess.ROLE_DIRECCION, use_custom_perms=False)

    core_views.contrato_rescision(
        _peticion(jefe, "/x/?html=1&fecha=2026-10-01"),
        proyecto_id=proyecto.id,
        participacion_id=participacion.id,
    )

    participacion.refresh_from_db()
    assert participacion.fecha_baja is None
    assert participacion.estado == "confirmada"


def test_la_baja_registra_lo_que_dice_el_acuerdo():
    proyecto, participacion = _escenario()  # 50.000 € al 5 % desde el 23/06/2026
    jefe = _usuario(role=UserAccess.ROLE_DIRECCION, use_custom_perms=False)

    r = _baja(jefe, proyecto, participacion, fecha="2026-10-23", motivo="cesión de su posición")
    assert r.status_code == 200

    participacion.refresh_from_db()
    assert participacion.fecha_baja == date(2026, 10, 23)
    assert participacion.motivo_baja == "cesión de su posición"
    assert participacion.estado == "cancelada"
    # 50.000 + 5.000 devengados − 950 de retención.
    assert participacion.importe_devuelto == Decimal("54050.00")


def test_al_darse_de_baja_deja_de_contar_en_el_capital_captado():
    """Es la razón de ser de la baja: que el inversor deje de estar presente."""
    from django.db.models import Sum

    proyecto, participacion = _escenario()
    jefe = _usuario(role=UserAccess.ROLE_DIRECCION, use_custom_perms=False)

    def captado():
        return Participacion.objects.filter(proyecto=proyecto, estado="confirmada").aggregate(
            t=Sum("importe_invertido")
        )["t"] or Decimal("0")

    assert captado() == Decimal("50000")
    _baja(jefe, proyecto, participacion, fecha="2026-10-23")
    assert captado() == Decimal("0")


def test_no_se_puede_dar_de_baja_dos_veces():
    proyecto, participacion = _escenario()
    jefe = _usuario(role=UserAccess.ROLE_DIRECCION, use_custom_perms=False)

    assert _baja(jefe, proyecto, participacion, fecha="2026-10-23").status_code == 200
    r = _baja(jefe, proyecto, participacion, fecha="2026-12-01")
    assert r.status_code == 409

    participacion.refresh_from_db()
    assert participacion.fecha_baja == date(2026, 10, 23)


def test_la_baja_exige_fecha_de_efectos():
    """De ella depende el devengo, así que no vale suponer la de hoy."""
    proyecto, participacion = _escenario()
    jefe = _usuario(role=UserAccess.ROLE_DIRECCION, use_custom_perms=False)

    assert _baja(jefe, proyecto, participacion).status_code == 400
    participacion.refresh_from_db()
    assert participacion.fecha_baja is None


def test_sin_permisos_no_se_da_de_baja_a_nadie():
    proyecto, participacion = _escenario()
    mirón = _usuario(use_custom_perms=True, role="", can_proyectos=False, can_clientes=True)

    assert _baja(mirón, proyecto, participacion, fecha="2026-10-23").status_code == 403
    participacion.refresh_from_db()
    assert participacion.estado == "confirmada"


def test_el_boton_de_baja_esta_en_el_javascript():
    """La tabla la repinta el JS: lo que no esté ahí no llega a existir."""
    from pathlib import Path

    js = (Path(__file__).resolve().parent.parent / "core" / "static" / "core" / "proyecto.js").read_text("utf-8")
    assert "/baja/" in js
    # Y una vez dada de baja, ya no se ofrece resolverla otra vez.
    assert "fecha_baja" in js
