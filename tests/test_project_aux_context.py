from types import SimpleNamespace

from core.models import DocumentoProyecto
from core.views import _build_project_aux_context


def test_build_project_aux_context_preserves_values_and_copies_diffusion_ids():
    checklist_items = [SimpleNamespace(id=1), SimpleNamespace(id=2)]
    clientes = [SimpleNamespace(nombre="Cliente 1")]
    difusion_clientes_ids = [10, 20]

    result = _build_project_aux_context(
        checklist_items,
        clientes,
        difusion_clientes_ids,
        3,
    )

    assert result["checklist_items"] is checklist_items
    assert result["clientes"] is clientes
    assert result["difusion_clientes_ids"] == [10, 20]
    assert result["difusion_clientes_ids"] is not difusion_clientes_ids
    assert result["solicitudes_pendientes_count"] == 3
    assert result["documento_categorias"] == DocumentoProyecto.CATEGORIAS
    assert difusion_clientes_ids == [10, 20]


def test_build_project_aux_context_keeps_empty_iterables_and_zero_counts():
    result = _build_project_aux_context([], [], [], 0)

    assert result == {
        "checklist_items": [],
        "clientes": [],
        "difusion_clientes_ids": [],
        "solicitudes_pendientes_count": 0,
        "documento_categorias": DocumentoProyecto.CATEGORIAS,
    }
