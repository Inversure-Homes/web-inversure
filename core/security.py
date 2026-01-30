import base64
import hashlib
import hmac
from typing import Optional

from django.conf import settings

try:
    from cryptography.fernet import Fernet, InvalidToken
except Exception:  # pragma: no cover - dependency is required at runtime
    Fernet = None
    InvalidToken = Exception


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
