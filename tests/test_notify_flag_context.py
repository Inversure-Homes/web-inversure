from __future__ import annotations

from copy import deepcopy

import pytest

from core.views import _build_project_notify_flag


class ContainsRaisesDict(dict):
    def __contains__(self, item):
        raise RuntimeError("contains failed")


class GetRaisesDict(dict):
    def get(self, key, default=None):
        raise RuntimeError("get failed")


class BoolRaises:
    def __bool__(self):
        raise RuntimeError("bool failed")


@pytest.mark.parametrize(
    "value",
    [True, False, 0, 1, "", "activo", None, [], [1], {}, {"k": "v"}],
)
def test_build_project_notify_flag_prefers_extra_and_coerces_bool(value):
    extra = {"notificar_inversores": value}
    snapshot = {"proyecto": {"notificar_inversores": not bool(value)}}
    extra_original = deepcopy(extra)
    snapshot_original = deepcopy(snapshot)

    result = _build_project_notify_flag(extra, snapshot)

    assert result is bool(value)
    assert extra == extra_original
    assert snapshot == snapshot_original


@pytest.mark.parametrize(
    "snapshot_value, expected",
    [
        (True, True),
        (False, False),
        (0, False),
        (1, True),
        ("", False),
        ("activo", True),
        (None, False),
        ([], False),
        ([1], True),
        ({}, False),
        ({"k": "v"}, True),
    ],
)
def test_build_project_notify_flag_falls_back_to_snapshot_project_block(snapshot_value, expected):
    extra = {}
    snapshot = {"proyecto": {"notificar_inversores": snapshot_value}}
    extra_original = deepcopy(extra)
    snapshot_original = deepcopy(snapshot)

    result = _build_project_notify_flag(extra, snapshot)

    assert result is expected
    assert extra == extra_original
    assert snapshot == snapshot_original


@pytest.mark.parametrize(
    "extra, snapshot",
    [
        ([], None),
        ("ignored", {}),
        (None, {"proyecto": {}}),
        (None, {"proyecto": []}),
        (None, {"proyecto": "texto"}),
        (None, {"proyecto": None}),
        (None, []),
        (None, "texto"),
    ],
)
def test_build_project_notify_flag_defaults_to_true_for_invalid_or_missing_snapshot(extra, snapshot):
    assert _build_project_notify_flag(extra, snapshot) is True


def test_build_project_notify_flag_aborts_when_extra_contains_raises_before_snapshot():
    extra = ContainsRaisesDict({"notificar_inversores": True})
    snapshot = {"proyecto": {"notificar_inversores": False}}

    assert _build_project_notify_flag(extra, snapshot) is True


def test_build_project_notify_flag_aborts_when_extra_get_raises_before_snapshot():
    extra = GetRaisesDict({"notificar_inversores": True})
    snapshot = {"proyecto": {"notificar_inversores": False}}

    assert _build_project_notify_flag(extra, snapshot) is True


def test_build_project_notify_flag_aborts_when_value_bool_raises():
    extra = {"notificar_inversores": BoolRaises()}
    snapshot = {"proyecto": {"notificar_inversores": False}}

    assert _build_project_notify_flag(extra, snapshot) is True


def test_build_project_notify_flag_aborts_when_snapshot_lookup_raises():
    extra = {}
    snapshot = GetRaisesDict({"proyecto": {"notificar_inversores": False}})

    assert _build_project_notify_flag(extra, snapshot) is True


def test_build_project_notify_flag_aborts_when_project_block_get_raises():
    extra = {}
    snapshot = {"proyecto": GetRaisesDict({"notificar_inversores": False})}

    assert _build_project_notify_flag(extra, snapshot) is True


def test_build_project_notify_flag_aborts_when_snapshot_value_bool_raises():
    extra = {}
    snapshot = {"proyecto": {"notificar_inversores": BoolRaises()}}

    assert _build_project_notify_flag(extra, snapshot) is True
