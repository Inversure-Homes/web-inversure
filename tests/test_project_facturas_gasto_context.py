from __future__ import annotations

from copy import deepcopy
from dataclasses import dataclass
from datetime import date
from decimal import Decimal

from core import views as core_views
from core.views import _build_project_facturas_gasto_context


@dataclass
class _Archivo:
    name: str = ""
    url_value: str = ""
    url_raises: bool = False

    @property
    def url(self):
        if self.url_raises:
            raise RuntimeError("url failed")
        return self.url_value


@dataclass
class _Gasto:
    concepto: str | None = None
    fecha: date | None = None
    importe: Decimal | None = None


@dataclass
class _Factura:
    id: int
    gasto_id: int
    gasto: _Gasto | None = None
    archivo: _Archivo | None = None
    nombre_original: str | None = None


def test_build_project_facturas_gasto_context_empty_iterable_returns_empty_list():
    assert _build_project_facturas_gasto_context([]) == []


def test_build_project_facturas_gasto_context_preserves_order_and_serialization(monkeypatch):
    facturas = [
        _Factura(
            id=1,
            gasto_id=10,
            gasto=_Gasto(concepto="Compra", fecha=date(2026, 7, 18), importe=Decimal("12.50")),
            archivo=_Archivo(name="signed.pdf", url_value="should-not-use", url_raises=True),
            nombre_original="Factura 1",
        ),
        _Factura(
            id=2,
            gasto_id=11,
            gasto=None,
            archivo=_Archivo(name="plain.pdf", url_value="plain-url"),
            nombre_original="",
        ),
        _Factura(
            id=3,
            gasto_id=12,
            gasto=None,
            archivo=_Archivo(name="error.pdf", url_value="unused", url_raises=True),
            nombre_original=None,
        ),
        _Factura(
            id=4,
            gasto_id=13,
            gasto=None,
            archivo=None,
            nombre_original=None,
        ),
    ]
    original_facturas = deepcopy(facturas)

    def fake_presigned(key):
        if key == "signed.pdf":
            return "signed://signed.pdf"
        if key == "plain.pdf":
            return ""
        if key == "error.pdf":
            raise RuntimeError("signed failed")
        return None

    monkeypatch.setattr(core_views, "_s3_presigned_url", fake_presigned)

    result = _build_project_facturas_gasto_context(facturas)

    assert result == [
        {
            "id": 1,
            "gasto_id": 10,
            "concepto": "Compra",
            "fecha": date(2026, 7, 18),
            "importe": Decimal("12.50"),
            "archivo_url": "signed://signed.pdf",
            "nombre": "Factura 1",
        },
        {
            "id": 2,
            "gasto_id": 11,
            "concepto": "—",
            "fecha": None,
            "importe": None,
            "archivo_url": "plain-url",
            "nombre": "plain.pdf",
        },
        {
            "id": 3,
            "gasto_id": 12,
            "concepto": "—",
            "fecha": None,
            "importe": None,
            "archivo_url": None,
            "nombre": "error.pdf",
        },
        {
            "id": 4,
            "gasto_id": 13,
            "concepto": "—",
            "fecha": None,
            "importe": None,
            "archivo_url": None,
            "nombre": "Factura",
        },
    ]
    assert facturas == original_facturas
