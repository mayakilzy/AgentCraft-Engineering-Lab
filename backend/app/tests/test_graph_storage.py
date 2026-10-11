"""T05 — Graph storage: referential integrity, cardinality caps,
session + dataset isolation, deterministic fixture load.

Tests against the production app via TestClient; uses real migrations against
a per-test SQLite file DB.
"""
from __future__ import annotations

import pytest


# ---- Helpers ----

def _new_guest(client):
    r = client.post("/api/v1/sessions/guest", json={"locale": "en"})
    assert r.status_code == 201, r.text
    return r  # caller can read Set-Cookie from headers


def _seed(client, dataset_id, fixture_key="starter-five-v1"):
    r = client.post(
        f"/api/v1/graph/{dataset_id}/seed",
        json={"dataset_key": fixture_key},
    )
    assert r.status_code == 200, r.text
    return r.json()


# ---- Sessions ----

def test_create_guest_session_sets_cookie(client):
    r = _new_guest(client)
    set_cookie = r.headers.get("set-cookie", "")
    assert "ac_guest=" in set_cookie
    assert "HttpOnly" in set_cookie
    assert "samesite=lax" in set_cookie.lower()

    me = client.get("/api/v1/sessions/me")
    assert me.status_code == 200
    body = me.json()
    assert "session_id" in body
    assert "expires_at" in body
    assert body["locale"] == "en"


def test_missing_cookie_returns_401(client):
    r = client.get("/api/v1/sessions/me")
    assert r.status_code == 401
    body = r.json()
    assert body["code"] == "unauthorized"


# ---- Seed + read ----

def test_seed_starter_five_loads_deterministic_data(client):
    _new_guest(client)
    summary = _seed(client, "ds-1")
    assert summary["dataset_id"] == "ds-1"
    assert summary["node_count"] == 5
    assert summary["edge_count"] == 4

    r = client.get("/api/v1/graph/ds-1")
    assert r.status_code == 200
    body = r.json()
    assert body["node_count"] == 5
    assert body["edge_count"] == 4
    # Cytoscape elements: 5 nodes + 4 edges = 9
    assert len(body["elements"]) == 9
    # The first element is a node (group=nodes)
    assert body["elements"][0]["group"] == "nodes"
    assert body["elements"][0]["data"]["kind"] in ("tool", "app", "skill")


def test_seed_is_idempotent(client):
    """Re-seeding the same dataset on the same session returns the existing
    counts without duplicating rows."""
    _new_guest(client)
    s1 = _seed(client, "ds-idem")
    s2 = _seed(client, "ds-idem")
    assert s1 == s2


def test_read_empty_dataset(client):
    _new_guest(client)
    r = client.get("/api/v1/graph/never-seeded")
    assert r.status_code == 200
    body = r.json()
    assert body["node_count"] == 0
    assert body["edge_count"] == 0
    assert body["elements"] == []


# ---- Node CRUD ----

def test_add_node_then_read(client):
    _new_guest(client)
    r = client.post(
        "/api/v1/graph/ds-nodes/nodes",
        json={"node_ref": "A1", "kind": "app", "label": "App Alpha"},
    )
    assert r.status_code == 201, r.text
    body = r.json()
    assert body["node"]["node_ref"] == "A1"
    assert body["node"]["kind"] == "app"

    r = client.get("/api/v1/graph/ds-nodes")
    assert r.status_code == 200
    assert r.json()["node_count"] == 1


def test_add_node_duplicate_ref_rejected(client):
    _new_guest(client)
    payload = {"node_ref": "DUP", "kind": "tool", "label": "Dup"}
    r1 = client.post("/api/v1/graph/ds-dup/nodes", json=payload)
    assert r1.status_code == 201
    r2 = client.post("/api/v1/graph/ds-dup/nodes", json=payload)
    assert r2.status_code == 409
    assert r2.json()["code"] == "invalid_state"


def test_add_node_missing_fields_422(client):
    _new_guest(client)
    r = client.post("/api/v1/graph/ds/nodes", json={"node_ref": "X"})
    assert r.status_code == 422


# ---- Edge CRUD + referential integrity ----

def test_add_edge_requires_existing_endpoints(client):
    _new_guest(client)
    r = client.post(
        "/api/v1/graph/ds-edges/edges",
        json={"source_ref": "GHOST", "target_ref": "ALSO", "relation": "R"},
    )
    assert r.status_code == 404
    assert r.json()["code"] == "not_found"


def test_add_edge_creates_directed_edge(client):
    _new_guest(client)
    client.post("/api/v1/graph/ds-edge/nodes", json={"node_ref": "S", "kind": "app", "label": "src"})
    client.post("/api/v1/graph/ds-edge/nodes", json={"node_ref": "T", "kind": "tool", "label": "tgt"})
    r = client.post(
        "/api/v1/graph/ds-edge/edges",
        json={"source_ref": "S", "target_ref": "T", "relation": "APP_USES_TOOL"},
    )
    assert r.status_code == 201, r.text
    body = r.json()["edge"]
    assert body["source_ref"] == "S"
    assert body["target_ref"] == "T"
    assert body["relation"] == "APP_USES_TOOL"


def test_add_edge_self_loop_rejected(client):
    _new_guest(client)
    client.post("/api/v1/graph/ds-loop/nodes", json={"node_ref": "L", "kind": "app", "label": "self"})
    r = client.post(
        "/api/v1/graph/ds-loop/edges",
        json={"source_ref": "L", "target_ref": "L", "relation": "SELF"},
    )
    assert r.status_code == 409
    assert r.json()["code"] == "invalid_state"


def test_add_edge_duplicate_triplet_rejected(client):
    _new_guest(client)
    client.post("/api/v1/graph/ds-dup-edge/nodes", json={"node_ref": "A", "kind": "app", "label": "a"})
    client.post("/api/v1/graph/ds-dup-edge/nodes", json={"node_ref": "B", "kind": "tool", "label": "b"})
    payload = {"source_ref": "A", "target_ref": "B", "relation": "R"}
    r1 = client.post("/api/v1/graph/ds-dup-edge/edges", json=payload)
    assert r1.status_code == 201
    r2 = client.post("/api/v1/graph/ds-dup-edge/edges", json=payload)
    assert r2.status_code == 409


# ---- SESSION ISOLATION (reviewer instruction #3) ----

def test_session_cannot_read_other_session_dataset(client):
    """Two sessions seed the same dataset key; each can only see its own."""
    # Session A
    a = _new_guest(client)
    a_cookie = a.headers["set-cookie"].split(";")[0].split("=", 1)[1]
    # Session B (new client request without cookie)
    b = _new_guest(client)
    b_cookie = b.headers["set-cookie"].split(";")[0].split("=", 1)[1]

    # A seeds
    client.cookies.clear()
    client.cookies.set("ac_guest", a_cookie)
    _seed(client, "iso-ds")

    # B reads the same dataset_id — must see empty (different session)
    client.cookies.clear()
    client.cookies.set("ac_guest", b_cookie)
    r = client.get("/api/v1/graph/iso-ds")
    assert r.status_code == 200
    body = r.json()
    assert body["node_count"] == 0
    assert body["edge_count"] == 0


def test_edge_cannot_connect_nodes_from_different_sessions(client):
    """Reviewer instruction #3: an edge must never connect nodes owned by
    two different sessions. This is structurally enforced because node
    lookups are scoped by session.id — but we test it explicitly here."""
    a = _new_guest(client)
    a_cookie = a.headers["set-cookie"].split(";")[0].split("=", 1)[1]
    b = _new_guest(client)
    b_cookie = b.headers["set-cookie"].split(";")[0].split("=", 1)[1]

    # Session A creates node A1
    client.cookies.clear()
    client.cookies.set("ac_guest", a_cookie)
    r = client.post(
        "/api/v1/graph/iso-edge/nodes",
        json={"node_ref": "A1", "kind": "app", "label": "A1"},
    )
    assert r.status_code == 201

    # Session B creates node B1
    client.cookies.clear()
    client.cookies.set("ac_guest", b_cookie)
    r = client.post(
        "/api/v1/graph/iso-edge/nodes",
        json={"node_ref": "B1", "kind": "tool", "label": "B1"},
    )
    assert r.status_code == 201

    # Session B tries to create an edge B1 -> A1: must fail with 404
    # because A1 doesn't exist in session B's scope.
    r = client.post(
        "/api/v1/graph/iso-edge/edges",
        json={"source_ref": "B1", "target_ref": "A1", "relation": "R"},
    )
    assert r.status_code == 404
    body = r.json()
    assert body["code"] == "not_found"
    assert "not found in this dataset" in body["message"]


def test_edge_cannot_cross_datasets_in_same_session(client):
    """Cross-dataset edges are rejected — the lookup is scoped to
    (session, dataset), so a node_ref in another dataset is invisible."""
    _new_guest(client)
    client.post("/api/v1/graph/ds-A/nodes", json={"node_ref": "X", "kind": "app", "label": "x"})
    client.post("/api/v1/graph/ds-B/nodes", json={"node_ref": "Y", "kind": "tool", "label": "y"})
    r = client.post(
        "/api/v1/graph/ds-B/edges",
        json={"source_ref": "X", "target_ref": "Y", "relation": "R"},
    )
    assert r.status_code == 404


# ---- Cardinality caps ----

def test_max_graph_nodes_enforced(client, monkeypatch):
    """When the cap is reached, additional node inserts are rejected."""
    from app.config import get_settings
    s = get_settings()
    monkeypatch.setattr(s, "max_graph_nodes", 2)
    monkeypatch.setattr(s, "max_graph_edges", 10)

    _new_guest(client)
    client.post("/api/v1/graph/cap/nodes", json={"node_ref": "N1", "kind": "app", "label": "1"})
    client.post("/api/v1/graph/cap/nodes", json={"node_ref": "N2", "kind": "app", "label": "2"})
    r = client.post("/api/v1/graph/cap/nodes", json={"node_ref": "N3", "kind": "app", "label": "3"})
    assert r.status_code == 409
    assert r.json()["code"] == "invalid_state"
    body = r.json()
    assert body["details"]["limit"] == 2


def test_max_graph_edges_enforced(client, monkeypatch):
    from app.config import get_settings
    s = get_settings()
    monkeypatch.setattr(s, "max_graph_nodes", 10)
    monkeypatch.setattr(s, "max_graph_edges", 1)

    _new_guest(client)
    client.post("/api/v1/graph/cap-e/nodes", json={"node_ref": "A", "kind": "app", "label": "a"})
    client.post("/api/v1/graph/cap-e/nodes", json={"node_ref": "B", "kind": "tool", "label": "b"})
    r1 = client.post(
        "/api/v1/graph/cap-e/edges",
        json={"source_ref": "A", "target_ref": "B", "relation": "R"},
    )
    assert r1.status_code == 201
    r2 = client.post(
        "/api/v1/graph/cap-e/edges",
        json={"source_ref": "B", "target_ref": "A", "relation": "R2"},
    )
    assert r2.status_code == 409


# ---- Invalid dataset_id ----

def test_invalid_dataset_id_rejected(client):
    _new_guest(client)
    r = client.get("/api/v1/graph/" + "x" * 200)
    assert r.status_code in (400, 404)
    # path too long is a 404 in FastAPI; keep the assertion permissive
