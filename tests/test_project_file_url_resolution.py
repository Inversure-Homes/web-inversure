from __future__ import annotations

from dataclasses import dataclass
from types import SimpleNamespace

import pytest

from core import views as core_views
from core.views import _apply_project_signed_url, _build_project_file_url


@dataclass
class _Archivo:
    name: str = ""
    url_value: str = ""
    url_raises: bool = False

    @property
    def url(self):
        if self.url_raises:
            raise RuntimeError("archivo.url failed")
        return self.url_value


@dataclass
class _Media:
    archivo: _Archivo
    signed_url: str | None = None


class _Request:
    def __init__(self, prefix: str = "abs://", raises: bool = False):
        self.prefix = prefix
        self.raises = raises

    def build_absolute_uri(self, value):
        if self.raises:
            raise RuntimeError("absolute uri failed")
        return f"{self.prefix}{value}"


def test_build_project_file_url_prefers_existing_signed_url_attr(monkeypatch):
    media = _Media(archivo=_Archivo(name="ignored.pdf", url_value="raw-url"), signed_url="signed-url")
    original = dict(getattr(media, "__dict__", {}))

    monkeypatch.setattr(core_views, "_s3_presigned_url", lambda key: (_ for _ in ()).throw(RuntimeError("boom")))

    assert _build_project_file_url(media, signed_url_attr="signed_url") == "signed-url"
    assert dict(getattr(media, "__dict__", {})) == original


@pytest.mark.parametrize(
    ("request_obj", "archivo", "expected"),
    [
        (_Request(), _Archivo(name="doc.pdf", url_value="raw-url"), "abs://raw-url"),
        (_Request(raises=True), _Archivo(name="doc.pdf", url_value="raw-url"), "raw-url"),
        (None, _Archivo(name="doc.pdf", url_value="raw-url"), "raw-url"),
    ],
)
def test_documento_url_uses_absolute_uri_when_available_and_raw_url_when_not(
    monkeypatch, request_obj, archivo, expected
):
    documento = SimpleNamespace(archivo=archivo)

    monkeypatch.setattr(core_views, "_s3_presigned_url", lambda key: "")

    assert core_views._documento_url(request_obj, documento) == expected


def test_build_project_file_url_returns_empty_string_when_raw_url_raises(monkeypatch):
    media = _Media(archivo=_Archivo(name="broken.pdf", url_raises=True))

    monkeypatch.setattr(core_views, "_s3_presigned_url", lambda key: "")

    assert _build_project_file_url(media, empty_on_error=True) == ""


def test_apply_project_signed_url_sets_signed_url_without_mutating_other_fields(monkeypatch):
    media = _Media(archivo=_Archivo(name="signed.pdf", url_value="raw-url"), signed_url=None)

    monkeypatch.setattr(
        core_views, "_s3_presigned_url", lambda key: "signed://signed.pdf" if key == "signed.pdf" else ""
    )

    original = dict(getattr(media, "__dict__", {}))

    assert _apply_project_signed_url(media) == "signed://signed.pdf"
    assert media.signed_url == "signed://signed.pdf"
    assert media.archivo == original["archivo"]
