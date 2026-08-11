from __future__ import annotations

from types import SimpleNamespace

from core.views import _ensure_project_template_fields


def test_ensure_project_template_fields_adds_missing_fields_without_overwriting_existing_values():
    proyecto = SimpleNamespace(venta_estimada="ya existe", responsable=None)

    _ensure_project_template_fields(proyecto)

    assert proyecto.venta_estimada == "ya existe"
    assert proyecto.responsable is None
    assert proyecto.precio_propiedad == ""
    assert proyecto.precio_compra_inmueble == ""
    assert proyecto.precio_venta_estimado == ""
    assert proyecto.notaria == ""
    assert proyecto.registro == ""
    assert proyecto.itp == ""
    assert proyecto.direccion == ""
    assert proyecto.ref_catastral == ""
    assert proyecto.valor_referencia == ""
    assert proyecto.meses == ""
    assert proyecto.financiacion_pct == ""


def test_ensure_project_template_fields_keeps_all_expected_fields_when_already_present():
    proyecto = SimpleNamespace(
        venta_estimada="1",
        precio_propiedad="2",
        precio_compra_inmueble="3",
        precio_venta_estimado="4",
        notaria="5",
        registro="6",
        itp="7",
        direccion="8",
        ref_catastral="9",
        valor_referencia="10",
        meses="11",
        financiacion_pct="12",
        responsable="13",
    )

    _ensure_project_template_fields(proyecto)

    assert proyecto.__dict__ == {
        "venta_estimada": "1",
        "precio_propiedad": "2",
        "precio_compra_inmueble": "3",
        "precio_venta_estimado": "4",
        "notaria": "5",
        "registro": "6",
        "itp": "7",
        "direccion": "8",
        "ref_catastral": "9",
        "valor_referencia": "10",
        "meses": "11",
        "financiacion_pct": "12",
        "responsable": "13",
    }
