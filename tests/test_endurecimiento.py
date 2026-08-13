"""
Los tres endurecimientos que quedaban de la auditoría: A3, M3 y M2.
"""

import os

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


# --- D3 · un dato ilegible deja de convertirse en «0 €» en silencio --------


def test_un_importe_ilegible_avisa_en_el_log(caplog):
    """
    En un informe de rentabilidad, un cero silencioso miente más que un error.
    Se sigue devolviendo el valor por defecto para no tumbar la página, pero
    queda constancia de que había un dato y no se pudo leer.
    """
    from core.views import _safe_float

    with caplog.at_level("WARNING"):
        assert _safe_float("no es un número") == 0.0
    assert "no interpretable" in caplog.text


def test_un_valor_ausente_no_ensucia_el_log(caplog):
    """Que no haya dato es normal y no dice nada; solo interesa el ilegible."""
    from core.views import _safe_float

    with caplog.at_level("WARNING"):
        assert _safe_float(None) == 0.0
        assert _safe_float("") == 0.0
    assert "no interpretable" not in caplog.text


def test_los_formatos_españoles_se_siguen_leyendo(caplog):
    from core.views import _safe_float

    with caplog.at_level("WARNING"):
        assert _safe_float("1.234,56 €") == 1234.56
        assert _safe_float("12,5 %") == 12.5
    assert "no interpretable" not in caplog.text


# --- A2 · sin claves no se arranca en producción ---------------------------


def test_produccion_exige_las_claves():
    """
    La barrera vive en `settings`, que se evalúa al importar, así que se
    comprueba ejecutando un proceso aparte: es la única forma de ver lo que
    pasaría en un arranque de verdad.
    """
    import subprocess
    import sys
    from pathlib import Path

    raiz = Path(__file__).resolve().parent.parent
    entorno = {
        "PATH": os.environ.get("PATH", ""),
        "DJANGO_SETTINGS_MODULE": "config.settings",
        "DJANGO_DEBUG": "0",
        "PYTHONPATH": str(raiz),
    }
    r = subprocess.run(
        [sys.executable, "-c", "import django; django.setup()"],
        capture_output=True,
        text=True,
        env=entorno,
        cwd=raiz,
    )
    assert r.returncode != 0
    assert "SENSITIVE_DATA_KEY" in r.stderr

    entorno.update({"DJANGO_SECRET_KEY": "una-clave-larga-de-verdad", "SENSITIVE_DATA_KEY": "otra-distinta"})

    # Con las claves puestas pero sin backend de correo tampoco arranca: el
    # valor por defecto escribe los correos en el log y devuelve éxito, así que
    # en producción no llegarían ni las invitaciones a firmar ni los códigos de
    # verificación, y nadie se enteraría.
    r = subprocess.run(
        [sys.executable, "-c", "import django; django.setup()"],
        capture_output=True,
        text=True,
        env=entorno,
        cwd=raiz,
    )
    assert r.returncode != 0
    assert "EMAIL_BACKEND" in r.stderr

    entorno["EMAIL_BACKEND"] = "django.core.mail.backends.smtp.EmailBackend"
    r = subprocess.run(
        [sys.executable, "-c", "import django; django.setup()"],
        capture_output=True,
        text=True,
        env=entorno,
        cwd=raiz,
    )
    assert r.returncode == 0, r.stderr


def test_las_cabeceras_de_seguridad_que_django_no_trae():
    """
    La CSP va a propósito sin `script-src`: hay scripts y estilos en línea en
    28 plantillas del ERP, y una política con `'unsafe-inline'` no protegería
    de nada mientras da la impresión contraria. Lo que sí se puede cerrar hoy
    —marcos, plugins, base de URLs y destino de los formularios— se cierra.
    """
    from django.test import Client

    respuesta = Client().get("/")
    csp = respuesta.headers.get("Content-Security-Policy", "")

    for directiva in ["frame-ancestors 'none'", "object-src 'none'", "base-uri 'self'", "form-action 'self'"]:
        assert directiva in csp, directiva

    assert "unsafe-inline" not in csp, "una CSP con unsafe-inline aparenta proteger sin hacerlo"
    assert "camera=()" in respuesta.headers.get("Permissions-Policy", "")


def test_la_landing_no_pide_nada_a_terceros():
    """
    Las tipografías se pedían a fonts.googleapis.com y los iconos a jsDelivr,
    lo que enviaba la IP de cada visitante a Google antes de que aceptara nada.
    Ahora se sirven desde el propio dominio. Los iconos, directamente, no se
    usaban en ninguna plantilla.
    """
    from pathlib import Path

    base = (Path(__file__).resolve().parent.parent / "landing" / "templates" / "landing" / "base.html").read_text("utf-8")
    for tercero in ["fonts.googleapis.com", "fonts.gstatic.com", "cdn.jsdelivr.net"]:
        assert tercero not in base, tercero
    assert "landing/fuentes.css" in base


def test_la_landing_se_puede_compartir():
    """Sin estas etiquetas, el enlace compartido sale pelado."""
    from django.test import Client

    html = Client().get("/").content.decode()
    for etiqueta in ['property="og:title"', 'property="og:image"', 'property="og:description"',
                     'name="twitter:card"', 'name="description"']:
        assert etiqueta in html, etiqueta


def test_los_formularios_informan_de_proteccion_de_datos():
    """
    El artículo 13 del RGPD obliga a informar al recoger los datos, y estos son
    los formularios por los que entra un inversor nuevo.
    """
    from django.test import Client

    html = Client().get("/").content.decode()
    assert html.count("lead-form__privacidad") == 2, "los dos formularios, no uno"
    assert "B-75265843" in html
    assert "/privacidad/" in html
