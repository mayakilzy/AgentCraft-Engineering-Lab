"""Modules registry tests — validates fail-closed registration semantics."""
from __future__ import annotations

import pytest

from app.services.modules_registry import ManifestRef, ModuleRegistry
from app.core.errors import InvalidStateError


def _ref(mid: str = "m1") -> ManifestRef:
    return ManifestRef(
        id=mid,
        module_id="graph",
        version="1.0.0",
        title_en="t", title_ar="t",
        description_en="d", description_ar="d",
    )


def test_register_and_list():
    reg = ModuleRegistry()
    reg.register(_ref())
    assert reg.count() == 1
    assert reg.get("m1") is not None


def test_duplicate_id_rejected():
    reg = ModuleRegistry()
    reg.register(_ref())
    with pytest.raises(InvalidStateError) as exc:
        reg.register(_ref())
    assert "duplicate manifest id" in str(exc.value)


def test_missing_id_rejected():
    reg = ModuleRegistry()
    bad = ManifestRef(
        id="", module_id="graph", version="1.0.0",
        title_en="t", title_ar="t", description_en="d", description_ar="d",
    )
    with pytest.raises(InvalidStateError):
        reg.register(bad)


def test_modules_endpoint_empty(client):
    r = client.get("/api/v1/modules")
    assert r.status_code == 200
    body = r.json()
    assert body == {"count": 0, "ids": []}


def test_experiments_endpoint_empty(client):
    r = client.get("/api/v1/experiments")
    assert r.status_code == 200
    body = r.json()
    assert body == {"count": 0, "ids": []}
