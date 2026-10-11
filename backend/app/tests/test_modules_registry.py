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
    """G05 contract change: the /modules endpoint now returns the 10
    manifests loaded from lab-modules/*.yaml at boot. The G01-era test
    expected `count=0`, but that was the honest empty state before
    manifests were wired (per the G01 report)."""
    r = client.get("/api/v1/modules")
    assert r.status_code == 200
    body = r.json()
    assert body["count"] == 10
    assert "graph-first-network" in body["ids"]
    assert "integrated-challenge" in body["ids"]


def test_experiments_endpoint_empty(client):
    """G05 contract change: the /experiments endpoint now returns the 10
    persisted experiment IDs. The G01-era test expected `count=0`, but
    that was the honest empty state before the manifest loader was wired."""
    r = client.get("/api/v1/experiments")
    assert r.status_code == 200
    body = r.json()
    assert body["count"] == 10
    # The IDs are alphabetically sorted (the test checks the set membership).
    expected_ids = {
        "graph-first-network", "shortest-path", "interactive-explorer",
        "sql-vs-cypher", "critical-dependencies", "discover-communities",
        "trace-one-request", "build-monitoring-dashboard",
        "diagnose-hidden-failure", "integrated-challenge",
    }
    assert set(body["ids"]) == expected_ids
