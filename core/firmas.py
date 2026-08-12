"""
Firma electrónica simple de los contratos, con rastro probatorio.

Lo que da valor a una firma simple no es el clic, sino poder demostrar después
**qué** documento se firmó y **quién** lo hizo. Aquí vive esa parte:

- la huella SHA-256 del PDF exacto que el firmante tuvo delante;
- un código de un solo uso enviado a su correo, que acredita el control de esa
  cuenta;
- la hora, la IP y el navegador.

Es firma electrónica simple (art. 3.10 del Reglamento eIDAS). Vale y es
admisible, pero no equivale a una cualificada: si el firmante la niega, hay que
acreditarla, y para eso está todo lo anterior.
"""

import hashlib
import logging
import secrets
from datetime import timedelta

from django.contrib.auth.hashers import check_password, make_password
from django.utils import timezone

log = logging.getLogger(__name__)

# El código caduca pronto a propósito: es de un solo uso y para una sesión de
# firma que está ocurriendo en ese momento.
CODIGO_VALIDO_MINUTOS = 15
CODIGO_INTENTOS_MAXIMOS = 5


class ErrorFirma(Exception):
    """Motivo legible para enseñárselo a quien está firmando."""


def huella(contenido: bytes) -> str:
    return hashlib.sha256(contenido).hexdigest()


def generar_codigo() -> str:
    """Seis dígitos, de un generador criptográfico y no de `random`."""
    return "".join(secrets.choice("0123456789") for _ in range(6))


def enviar_codigo(firma, email: str) -> str:
    """
    Emite un código nuevo y lo guarda cifrado.

    Devuelve el código en claro para que lo envíe quien llama; no se guarda en
    ningún sitio en claro, así que si alguien lee la base de datos no puede
    firmar en nombre de otro.
    """
    codigo = generar_codigo()
    firma.codigo_hash = make_password(codigo)
    firma.codigo_enviado_en = timezone.now()
    firma.codigo_intentos = 0
    firma.email = email
    firma.save(update_fields=["codigo_hash", "codigo_enviado_en", "codigo_intentos", "email"])
    return codigo


def comprobar_codigo(firma, codigo: str) -> None:
    """Valida el código. Lanza `ErrorFirma` con el motivo si no cuela."""
    if not firma.codigo_hash or not firma.codigo_enviado_en:
        raise ErrorFirma("Pide primero un código de verificación.")

    if firma.codigo_intentos >= CODIGO_INTENTOS_MAXIMOS:
        raise ErrorFirma("Demasiados intentos fallidos. Pide un código nuevo.")

    caduca = firma.codigo_enviado_en + timedelta(minutes=CODIGO_VALIDO_MINUTOS)
    if timezone.now() > caduca:
        raise ErrorFirma("El código ha caducado. Pide uno nuevo.")

    if not check_password((codigo or "").strip(), firma.codigo_hash):
        firma.codigo_intentos += 1
        firma.save(update_fields=["codigo_intentos"])
        raise ErrorFirma("El código no es correcto.")


def sellar(firma, pdf_contrato: bytes, datos: dict) -> None:
    """
    Cierra la firma: guarda la huella, las circunstancias y el documento.

    La huella es la del contrato **antes** de añadirle la hoja de evidencias.
    Es a propósito: así cualquiera puede regenerar el contrato, calcular su
    SHA-256 y comprobar que coincide con el que aparece impreso en esa misma
    hoja. Si la huella cubriera la hoja que la contiene, no habría forma de
    comprobar nada.
    """
    from django.core.files.base import ContentFile

    firma.hash_documento = huella(pdf_contrato)
    firma.nombre_declarado = (datos.get("nombre") or "").strip()[:200]
    firma.ip = datos.get("ip") or None
    firma.user_agent = (datos.get("user_agent") or "")[:400]
    firma.autorizaciones = datos.get("autorizaciones") or {}
    firma.firmado_en = timezone.now()
    firma.estado = firma.Estado.FIRMADO

    completo = datos.get("pdf_completo") or pdf_contrato
    nombre = "{}-{}.pdf".format(firma.tipo, firma.participacion_id)
    firma.documento.save(nombre, ContentFile(completo), save=False)

    firma.save()
    log.info(
        "Contrato firmado: participación %s, tipo %s, huella %s",
        firma.participacion_id, firma.tipo, firma.hash_documento[:16],
    )


def unir(pdf_contrato: bytes, pdf_evidencias: bytes) -> bytes:
    """
    Pega la hoja de evidencias al final del contrato.

    Si falla, se devuelve el contrato solo: perder la hoja es un problema, pero
    perder el contrato firmado sería mucho peor.
    """
    try:
        from io import BytesIO

        from pypdf import PdfReader, PdfWriter

        escritor = PdfWriter()
        for pdf in (pdf_contrato, pdf_evidencias):
            for pagina in PdfReader(BytesIO(pdf)).pages:
                escritor.add_page(pagina)
        salida = BytesIO()
        escritor.write(salida)
        return salida.getvalue()
    except Exception:
        log.exception("No se pudo unir la hoja de evidencias al contrato firmado")
        return pdf_contrato
