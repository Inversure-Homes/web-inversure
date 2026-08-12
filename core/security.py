import base64
import hashlib
import hmac
import logging
from typing import Optional

from django.conf import settings

try:
    from cryptography.fernet import Fernet, InvalidToken
except Exception:  # pragma: no cover - dependency is required at runtime
    Fernet = None
    InvalidToken = Exception


log = logging.getLogger(__name__)

_FERNET = None
_ENC_PREFIX = "enc::"


def _derive_fernet_key(secret: str) -> bytes:
    return base64.urlsafe_b64encode(hashlib.sha256(secret.encode("utf-8")).digest())


def _get_fernet() -> "Fernet":
    global _FERNET
    if _FERNET is not None:
        return _FERNET
    if Fernet is None:
        raise RuntimeError("cryptography is required for field encryption")
    raw = getattr(settings, "SENSITIVE_DATA_KEY", "") or settings.SECRET_KEY
    key = _derive_fernet_key(raw)
    _FERNET = Fernet(key)
    return _FERNET


def _get_hmac_key() -> bytes:
    raw = getattr(settings, "SENSITIVE_DATA_HMAC_KEY", "") or settings.SECRET_KEY
    return raw.encode("utf-8")


def encrypt_value(value: Optional[str]) -> Optional[str]:
    if value is None or value == "":
        return value
    if isinstance(value, str) and value.startswith(_ENC_PREFIX):
        return value
    token = _get_fernet().encrypt(value.encode("utf-8")).decode("utf-8")
    return f"{_ENC_PREFIX}{token}"


def decrypt_value(value: Optional[str]) -> Optional[str]:
    if value is None or value == "":
        return value
    if not isinstance(value, str):
        value = str(value)
    if not value.startswith(_ENC_PREFIX):
        return value
    token = value[len(_ENC_PREFIX):]
    try:
        return _get_fernet().decrypt(token.encode("utf-8")).decode("utf-8")
    except InvalidToken:
        # Se devuelve el cifrado en vez de reventar, para que un dato ilegible
        # no tumbe la ficha entera. Pero queda registrado: si la clave cambia
        # —una rotación, una copia restaurada en otro entorno— todos los DNI y
        # los IBAN se vuelven ilegibles a la vez, y sin esta línea la única
        # señal sería que alguien viera `enc::gAAAAA…` en pantalla y lo contara.
        log.error(
            "No se pudo descifrar un campo sensible. Suele significar que "
            "SENSITIVE_DATA_KEY no es la que cifró el dato.",
        )
        return value


def normalize_dni_cif(value: Optional[str]) -> str:
    return (value or "").strip().upper().replace(" ", "")


def normalize_email(value: Optional[str]) -> str:
    return (value or "").strip().lower()


def normalize_iban(value: Optional[str]) -> str:
    return (value or "").strip().upper().replace(" ", "")


def normalize_phone(value: Optional[str]) -> str:
    raw = (value or "").strip()
    if not raw:
        return ""
    digits = "".join(ch for ch in raw if ch.isdigit())
    if raw.startswith("+") and digits:
        return f"+{digits}"
    return digits


def hash_value(value: Optional[str], purpose: str) -> str:
    norm = value or ""
    if not norm:
        return ""
    payload = f"{purpose}:{norm}".encode("utf-8")
    return hmac.new(_get_hmac_key(), payload, hashlib.sha256).hexdigest()


# =========================
# FICHEROS SUBIDOS
# =========================

# Lo que de verdad se sube al ERP: escrituras, facturas, justificantes, notas
# simples y fotos del inmueble. Una lista corta y explícita, no una de cosas
# prohibidas: las listas de prohibidos siempre se quedan cortas.
EXTENSIONES_PERMITIDAS = {
    ".pdf",
    ".jpg", ".jpeg", ".png", ".webp", ".heic",
    ".doc", ".docx", ".odt",
    ".xls", ".xlsx", ".ods", ".csv",
}

# Lo que el navegador dice que es. Se comprueba además de la extensión porque
# renombrar un fichero es trivial; no es una garantía, es una barrera más.
TIPOS_PERMITIDOS_PREFIJO = ("image/", "application/pdf", "text/csv", "text/plain", "application/vnd.", "application/msword")

MB = 1024 * 1024


class FicheroNoPermitido(Exception):
    """Motivo legible para enseñárselo a quien sube el fichero."""


def comprobar_fichero(archivo, max_mb: int = 25) -> None:
    """
    Valida un fichero subido. Lanza `FicheroNoPermitido` con el motivo.

    No sustituye a un antivirus ni pretende: lo que evita es que alguien deje
    un `.html` o un `.svg` con JavaScript en un bucket que después se sirve por
    una URL de nuestro dominio, y que un fichero enorme llene el
    almacenamiento.
    """
    import os

    nombre = getattr(archivo, "name", "") or ""
    extension = os.path.splitext(nombre)[1].lower()

    if not extension:
        raise FicheroNoPermitido("El fichero no tiene extensión, así que no se puede comprobar qué es.")
    if extension not in EXTENSIONES_PERMITIDAS:
        raise FicheroNoPermitido(
            "No se admiten ficheros «{}». Se aceptan PDF, imágenes y documentos de ofimática.".format(extension)
        )

    # Un objeto sin `size` no es lo mismo que uno de cero bytes: los ficheros
    # subidos de verdad siempre lo traen, pero otros envoltorios no, y tomar la
    # ausencia por vacío rechazaría subidas buenas.
    tamano = getattr(archivo, "size", None)
    if tamano is not None:
        if tamano > max_mb * MB:
            raise FicheroNoPermitido("El fichero ocupa {:.1f} MB y el máximo son {} MB.".format(tamano / MB, max_mb))
        if tamano == 0:
            raise FicheroNoPermitido("El fichero está vacío.")

    tipo = (getattr(archivo, "content_type", "") or "").lower()
    if tipo and not tipo.startswith(TIPOS_PERMITIDOS_PREFIJO):
        raise FicheroNoPermitido("El tipo de fichero ({}) no coincide con lo que se admite.".format(tipo))


# Cuántos PIN fallidos se admiten desde una misma IP contra un mismo inversor,
# y en cuántos minutos.
#
# Se cuenta por (inversor, IP) y no solo por inversor a propósito: bloquear por
# inversor dejaría que cualquiera echase al legítimo de su propio portal sin
# más que fallar cinco veces. Así, quien se bloquea es quien lo intenta. No
# para un ataque repartido entre muchas IP, pero sí el caso realista, que es
# alguien probando desde un sitio.
PIN_INTENTOS_MAXIMOS = 5
PIN_VENTANA_MINUTOS = 15
