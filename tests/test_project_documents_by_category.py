from __future__ import annotations

from copy import deepcopy
from types import SimpleNamespace

from core.views import _build_project_documents_by_category


def test_build_project_documents_by_category_groups_by_category_and_preserves_order():
    documentos = [
        SimpleNamespace(id=1, categoria="fotografias"),
        SimpleNamespace(id=2, categoria=None),
        SimpleNamespace(id=3),
        SimpleNamespace(id=4, categoria=""),
        SimpleNamespace(id=5, categoria="facturas"),
        SimpleNamespace(id=6, categoria="fotografias"),
    ]
    original = deepcopy(documentos)

    result = _build_project_documents_by_category(documentos)

    assert list(result.keys()) == ["fotografias", "otros", "facturas"]
    assert result["fotografias"] == [documentos[0], documentos[5]]
    assert result["otros"] == [documentos[1], documentos[2], documentos[3]]
    assert result["facturas"] == [documentos[4]]
    assert documentos == original


def test_build_project_documents_by_category_empty_iterable_returns_empty_dict():
    assert _build_project_documents_by_category([]) == {}
