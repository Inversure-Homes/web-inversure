"""
Los tres endurecimientos que quedaban de la auditoría: A3, M3 y M2.
"""

import pytest
from django.contrib.auth.hashers import make_password
from django.test import Client

from core.models import Cliente, IntentoPinPortal, InversorPerfil
from core.security import (
    PIN_INTENTOS_MAXIMOS,
    FicheroNoPermitido,
    comprobar_fichero,
    decrypt_value,
    encrypt_value,
)

pytestmark = pytest.mark.django_db


# --- A3 · un fallo al descifrar deja rastro -------------------------------


def test_descifrar_con_otra_clave_queda_en_el_log(caplog, settings):
    """
    Si la clave cambia, todos los DNI e IBAN se vuelven ilegibles a la vez. Sin
    esta línea en el log, la única señal sería que alguien viese `enc::…` en
    pantalla y se molestase en contarlo.
    """
    import core.security as seguridad

    settings.SENSITIVE_DATA_KEY = "la-clave-con-la-que-se-cifro"
    seguridad._FERNET = None
    cifrado = encrypt_value("12345678Z")

    settings.SENSITIVE_DATA_KEY = "otra-clave-distinta-por-una-rotacion"
    seguridad._FERNET = None
    with caplog.at_level("ERROR"):
        devuelto = decrypt_value(cifrado)

    assert devuelto == cifrado, "sigue devolviendo el cifrado para no tumbar la ficha"
    assert "SENSITIVE_DATA_KEY" in caplog.text
    seguridad._FERNET = None


# --- M3 · validación de ficheros subidos ----------------------------------


class _Fichero:
    def __init__(self, name, size=1024, content_type="application/pdf"):
        self.name = name
        self.size = size
        self.content_type = content_type


@pytest.mark.parametrize(
    "nombre",
    ["escritura.pdf", "foto.JPG", "cuentas.xlsx", "nota.docx", "datos.csv"],
)
def test_lo_que_se_sube_de_verdad_pasa(nombre):
    comprobar_fichero(_Fichero(nombre, content_type=""))


@pytest.mark.parametrize(
    "nombre",
    ["malicioso.html", "icono.svg", "script.js", "programa.exe", "paquete.zip", "sin_extension"],
)
def test_lo_que_no_deberia_subirse_se_rechaza(nombre):
    """Un `.html` o un `.svg` con JavaScript acaba servido desde nuestro dominio."""
    with pytest.raises(FicheroNoPermitido):
        comprobar_fichero(_Fichero(nombre, content_type=""))


def test_se_rechaza_por_tamano_y_por_vacio():
    with pytest.raises(FicheroNoPermitido):
        comprobar_fichero(_Fichero("enorme.pdf", size=26 * 1024 * 1024))
    with pytest.raises(FicheroNoPermitido):
        comprobar_fichero(_Fichero("vacio.pdf", size=0))


def test_la_extension_correcta_no_salva_un_tipo_raro():
    """Renombrar es trivial; el tipo declarado es una barrera más."""
    with pytest.raises(FicheroNoPermitido):
        comprobar_fichero(_Fichero("disfrazado.pdf", content_type="text/html"))


# --- M2 · límite de intentos del PIN --------------------------------------


def _portal_con_pin(pin="1234"):
    cliente = Cliente.objects.create(nombre="Ana", dni_cif="00000001R", email="a@e.com")
    perfil = InversorPerfil.objects.create(cliente=cliente, portal_pin_hash=make_password(pin))
    return perfil


def _intentar(cliente_http, perfil, pin, ip="10.0.0.1"):
    return cliente_http.post(
        "/app/inversor/{}/".format(perfil.token),
        {"portal_pin_submit": "1", "portal_pin": pin},
        HTTP_X_FORWARDED_FOR=ip,
    )


def test_a_la_sexta_se_bloquea():
    perfil = _portal_con_pin()
    c = Client()
    for _ in range(PIN_INTENTOS_MAXIMOS):
        r = _intentar(c, perfil, "0000")
        assert "PIN incorrecto" in r.content.decode()

    r = _intentar(c, perfil, "0000")
    assert "Demasiados intentos" in r.content.decode()


def test_el_bloqueo_tambien_frena_el_pin_correcto():
    """Si no, bastaría con acertar al sexto intento."""
    perfil = _portal_con_pin()
    c = Client()
    for _ in range(PIN_INTENTOS_MAXIMOS):
        _intentar(c, perfil, "0000")

    r = _intentar(c, perfil, "1234")
    assert "Demasiados intentos" in r.content.decode()


def test_otra_ip_no_queda_bloqueada():
    """
    Se cuenta por (inversor, IP). Si se contara solo por inversor, cualquiera
    podría echar al legítimo de su propio portal fallando cinco veces.
    """
    perfil = _portal_con_pin()
    c = Client()
    for _ in range(PIN_INTENTOS_MAXIMOS):
        _intentar(c, perfil, "0000", ip="10.0.0.1")

    r = _intentar(c, perfil, "1234", ip="10.0.0.2")
    assert "Demasiados intentos" not in r.content.decode()


def test_queda_registro_de_los_intentos():
    perfil = _portal_con_pin()
    c = Client()
    _intentar(c, perfil, "0000")
    _intentar(c, perfil, "1234")

    assert IntentoPinPortal.objects.filter(perfil=perfil, acertado=False).count() == 1
    assert IntentoPinPortal.objects.filter(perfil=perfil, acertado=True).count() == 1
