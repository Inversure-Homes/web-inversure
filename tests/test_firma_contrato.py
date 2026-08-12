"""
Firma electrónica simple del contrato por el propio inversor.

Lo que da valor a una firma simple no es el clic: es poder demostrar después
qué documento se firmó y quién lo hizo. Estas pruebas cubren justo eso.
"""

from datetime import date, timedelta
from decimal import Decimal

import pytest
from django.core import mail
from django.test import Client
from django.utils import timezone

from core.firmas import CODIGO_INTENTOS_MAXIMOS, huella
from core.models import Cliente, FirmaContrato, InversorPerfil, Participacion, Proyecto

pytestmark = pytest.mark.django_db


def _escenario():
    proyecto = Proyecto.objects.create(
        nombre="MADRID",
        direccion="C/ Ariza 142",
        precio_compra_inmueble=Decimal("135000"),
        precio_venta_estimado=Decimal("178700"),
    )
    cliente = Cliente.objects.create(
        nombre="Alejandro Vergara",
        dni_cif="26261870X",
        email="alejandro@ejemplo.com",
        direccion_postal="Málaga",
    )
    perfil = InversorPerfil.objects.create(cliente=cliente)
    participacion = Participacion.objects.create(
        proyecto=proyecto,
        cliente=cliente,
        importe_invertido=Decimal("7500"),
        porcentaje_participacion=Decimal("5.30"),
        estado="confirmada",
        contrato_fecha=date(2026, 2, 12),
        contrato_meses=6,
    )
    return perfil, participacion


def _url(perfil, participacion):
    return "/app/inversor/{}/contrato/{}/".format(perfil.token, participacion.id)


def _codigo_del_correo():
    cuerpo = mail.outbox[-1].body
    return next(t for t in cuerpo.split() if t.isdigit() and len(t) == 6)


def _firmar(c, perfil, participacion, codigo=None, **extra):
    datos = {"firmar": "1", "acepto": "si", "nombre": "Alejandro Vergara", "codigo": codigo or ""}
    datos.update(extra)
    return c.post(_url(perfil, participacion), datos)


def test_el_recorrido_completo_deja_el_contrato_firmado():
    perfil, participacion = _escenario()
    c = Client()

    c.post(_url(perfil, participacion), {"pedir_codigo": "1"})
    assert len(mail.outbox) == 1
    assert mail.outbox[0].to == ["alejandro@ejemplo.com"]

    _firmar(c, perfil, participacion, _codigo_del_correo())

    firma = FirmaContrato.objects.get(participacion=participacion)
    assert firma.firmado
    assert firma.hash_documento and len(firma.hash_documento) == 64
    assert firma.documento, "el PDF firmado queda archivado"
    assert firma.ip and firma.firmado_en
    # Y se le manda su copia.
    assert len(mail.outbox) == 2
    assert mail.outbox[1].attachments


def test_sin_codigo_no_se_firma():
    perfil, participacion = _escenario()
    c = Client()
    c.post(_url(perfil, participacion), {"pedir_codigo": "1"})

    _firmar(c, perfil, participacion, "000000")

    assert not FirmaContrato.objects.get(participacion=participacion).firmado


def test_sin_aceptar_el_contrato_tampoco():
    perfil, participacion = _escenario()
    c = Client()
    c.post(_url(perfil, participacion), {"pedir_codigo": "1"})
    codigo = _codigo_del_correo()

    c.post(_url(perfil, participacion), {"firmar": "1", "codigo": codigo, "nombre": "X"})

    assert not FirmaContrato.objects.get(participacion=participacion).firmado


def test_el_codigo_caduca():
    perfil, participacion = _escenario()
    c = Client()
    c.post(_url(perfil, participacion), {"pedir_codigo": "1"})
    codigo = _codigo_del_correo()

    firma = FirmaContrato.objects.get(participacion=participacion)
    firma.codigo_enviado_en = timezone.now() - timedelta(minutes=16)
    firma.save(update_fields=["codigo_enviado_en"])

    r = _firmar(c, perfil, participacion, codigo)
    assert "caducado" in r.content.decode()
    assert not FirmaContrato.objects.get(participacion=participacion).firmado


def test_no_se_puede_probar_el_codigo_a_lo_bruto():
    perfil, participacion = _escenario()
    c = Client()
    c.post(_url(perfil, participacion), {"pedir_codigo": "1"})

    for _ in range(CODIGO_INTENTOS_MAXIMOS):
        _firmar(c, perfil, participacion, "000000")

    # Ni siquiera con el bueno.
    r = _firmar(c, perfil, participacion, _codigo_del_correo())
    assert "Demasiados intentos" in r.content.decode()
    assert not FirmaContrato.objects.get(participacion=participacion).firmado


def test_el_codigo_no_se_guarda_en_claro():
    """Si alguien lee la base de datos no puede firmar en nombre de otro."""
    perfil, participacion = _escenario()
    Client().post(_url(perfil, participacion), {"pedir_codigo": "1"})

    firma = FirmaContrato.objects.get(participacion=participacion)
    assert _codigo_del_correo() not in firma.codigo_hash


def test_la_huella_es_la_del_documento_firmado():
    """
    Se guarda la huella del contrato sin la hoja de evidencias, para que se
    pueda regenerar el contrato y comprobar que coincide. Si la huella cubriera
    la hoja que la imprime, no habría forma de verificarla.
    """
    perfil, participacion = _escenario()
    c = Client()
    c.post(_url(perfil, participacion), {"pedir_codigo": "1"})
    _firmar(c, perfil, participacion, _codigo_del_correo())

    firma = FirmaContrato.objects.get(participacion=participacion)
    with firma.documento.open("rb") as f:
        archivado = f.read()

    assert archivado[:5] == b"%PDF-"
    # El archivado lleva la hoja de más, así que su huella NO es la guardada.
    assert huella(archivado) != firma.hash_documento


def test_una_vez_firmado_se_entrega_el_archivado():
    """Lo que vale es lo que se firmó, no lo que el sistema generaría hoy."""
    perfil, participacion = _escenario()
    c = Client()
    c.post(_url(perfil, participacion), {"pedir_codigo": "1"})
    _firmar(c, perfil, participacion, _codigo_del_correo())

    firma = FirmaContrato.objects.get(participacion=participacion)
    with firma.documento.open("rb") as f:
        archivado = f.read()

    r = c.get(_url(perfil, participacion) + "pdf/")
    assert r["Content-Type"] == "application/pdf"
    assert r.content == archivado


def test_no_se_firma_el_contrato_de_otro():
    """El token es la credencial: solo alcanza a las participaciones propias."""
    perfil, _participacion = _escenario()
    otro_cliente = Cliente.objects.create(nombre="Otra", dni_cif="00000002W", email="o@e.com")
    ajena = Participacion.objects.create(
        proyecto=Proyecto.objects.first(),
        cliente=otro_cliente,
        importe_invertido=Decimal("5000"),
        estado="confirmada",
    )

    r = Client().get(_url(perfil, ajena))
    assert r.status_code == 404


def test_las_autorizaciones_quedan_registradas():
    perfil, participacion = _escenario()
    c = Client()
    c.post(_url(perfil, participacion), {"pedir_codigo": "1"})
    _firmar(c, perfil, participacion, _codigo_del_correo(), aut_novedades="on")

    firma = FirmaContrato.objects.get(participacion=participacion)
    marcadas = {k: v for k, v in firma.autorizaciones.items() if v}
    assert len(marcadas) == 1
    assert "oportunidades de inversión" in list(marcadas)[0]


def test_no_se_firma_dos_veces():
    perfil, participacion = _escenario()
    c = Client()
    c.post(_url(perfil, participacion), {"pedir_codigo": "1"})
    _firmar(c, perfil, participacion, _codigo_del_correo())
    firmado_en = FirmaContrato.objects.get(participacion=participacion).firmado_en

    _firmar(c, perfil, participacion, "123456")

    assert FirmaContrato.objects.filter(participacion=participacion).count() == 1
    assert FirmaContrato.objects.get(participacion=participacion).firmado_en == firmado_en
