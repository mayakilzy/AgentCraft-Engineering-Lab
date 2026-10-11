"""In-process fake Neo4j driver that mirrors the real GraphDatabase API
shape used by `app/services/neo4j_service.py`.

This is for tests only — production never uses it. It implements:
- `verify_connectivity()` -> raises if `connected` flag is False
- `session()` -> returns a session object
- session.run(query, **params) -> returns a Result-like object with .next()
  and __iter__
- session.consume(result) -> returns a Summary-like object with .counters

The fake stores data in an in-memory dict so parity tests can verify that
SQL and Cypher return the same canonical sets.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Iterable


@dataclass
class FakeRecord:
    """Mirror of neo4j.Record: dict-like with a `.data()` accessor that
    returns the underlying dict (matching the real neo4j.Record API)."""
    _data: dict

    def __getitem__(self, key):
        return self._data[key]

    def get(self, key, default=None):
        return self._data.get(key, default)

    def values(self):
        return list(self._data.values())

    def data(self) -> dict:
        return dict(self._data)


@dataclass
class FakeResult:
    rows: list[dict] = field(default_factory=list)

    def __iter__(self):
        # Iteration yields Record-like objects so caller code that does
        # `[r.data() for r in result]` works.
        return iter(FakeRecord(r) for r in self.rows)

    def next(self):  # mirror neo4j.Result.next()
        if not self.rows:
            raise StopIteration
        return FakeRecord(self.rows[0])

    def single(self):
        return FakeRecord(self.rows[0]) if self.rows else None

    def data(self) -> list[dict]:
        return list(self.rows)

    def consume(self) -> "FakeSummary":
        return FakeSummary(counters={"nodes_deleted": 0})


@dataclass
class FakeSummary:
    counters: dict[str, int] = field(default_factory=dict)


class FakeSession:
    def __init__(self, store: dict[str, Any], database: str | None = None):
        self.store = store
        self.database = database
        self.queries_run: list[tuple[str, dict]] = []

    def __enter__(self) -> "FakeSession":
        return self

    def __exit__(self, exc_type, exc, tb) -> None:
        self.close()

    def run(self, query: str, parameters: dict | None = None, **kwargs) -> FakeResult:
        # Merge positional `parameters` and `**kwargs` like the real driver.
        params = {**(parameters or {}), **kwargs}
        self.queries_run.append((query, params))
        # Implement just enough Cypher for the parity + community tests:
        # - MATCH (n:`<label>`) RETURN count(n) AS cnt
        # - MERGE (n:`<label>` {ref: $ref}) SET n.kind=$kind, n.label=$label
        # - MATCH (s), (t) MERGE (s)-[r:`<rel>`]->(t)
        # - SHOW PROCEDURES YIELD name WHERE name STARTS WITH 'gds.' RETURN name LIMIT 1
        # - CALL dbms.components() YIELD name, versions, edition RETURN name, versions, edition
        # - MATCH (n) WHERE ANY(l IN labels(n) WHERE l STARTS WITH $ns_prefix) DETACH DELETE n
        # Real Cypher parsing is out of scope — we pattern-match the leading token.
        q = query.strip()
        if q.startswith("CALL dbms.components"):
            return FakeResult(rows=[{
                "name": "Neo4j Kernel",
                "versions": ["5.26.0"],
                "edition": "community",
            }])
        if q.startswith("SHOW PROCEDURES"):
            # Test driver: configure whether GDS procedures are listed.
            if self.store.get("gds_available"):
                return FakeResult(rows=[{"name": "gds.louvain.stream"}])
            return FakeResult(rows=[])
        # Specific match: count query (returns {"cnt": N})
        if q.startswith("MATCH (n:`") and "RETURN count(n) AS cnt" in q \
                and "n.kind" not in q:
            label = _extract_label(q, "MATCH (n:`")
            count = len(self.store.get("labels", {}).get(label, []))
            return FakeResult(rows=[{"cnt": count}])
        # Specific match: kind_counts query
        if q.startswith("MATCH (n:`") and "RETURN n.kind AS kind, count(n) AS cnt" in q:
            label = _extract_label(q, "MATCH (n:`")
            nodes = self.store.get("labels", {}).get(label, {})
            counts: dict[str, int] = {}
            for data in nodes.values():
                k = data.get("kind", "default")
                counts[k] = counts.get(k, 0) + 1
            rows = [{"kind": k, "cnt": v} for k, v in sorted(counts.items())]
            return FakeResult(rows=rows)
        if q.startswith("MERGE (n:`"):
            label = _extract_label(q, "MERGE (n:`")
            ref = params.get("ref")
            if ref is None:
                return FakeResult(rows=[])
            self.store.setdefault("labels", {}).setdefault(label, {})[ref] = {
                "ref": ref,
                "kind": params.get("kind"),
                "label": params.get("label"),
            }
            return FakeResult(rows=[])
        if q.startswith("MATCH (s:`") and "MERGE (s)-[r:`" in q:
            label = _extract_label(q, "MATCH (s:`")
            src = params.get("src")
            tgt = params.get("tgt")
            self.store.setdefault("edges", {}).setdefault(label, []).append((src, tgt))
            return FakeResult(rows=[])
        if q.startswith("MATCH (n) WHERE ANY(l IN labels(n)"):
            ns = params.get("ns_prefix", "")
            deleted = 0
            for label in list(self.store.get("labels", {}).keys()):
                if label.startswith(ns):
                    del self.store["labels"][label]
                    deleted += len(self.store["labels"].get(label, {}))
            for label in list(self.store.get("edges", {}).keys()):
                if label.startswith(ns):
                    edges = self.store["edges"].pop(label, [])
                    deleted += len(edges)
            return FakeResult(rows=[])  # consume will return counters
        if q.startswith("CALL gds.louvain.stream"):
            # Fake community detection: partition by node's kind.
            label = "g_" + _extract_gds_graph_name(q)
            nodes = self.store.get("labels", {}).get(label, {})
            communities: dict[str, list[str]] = {}
            for ref, data in nodes.items():
                cid = data.get("kind", "default")
                communities.setdefault(cid, []).append(ref)
            return FakeResult(rows=[
                {"nodeId": i, "communityId": hash(cid) % 100}
                for cid, members in communities.items()
                for i, _ in enumerate(members)
            ])
        if q.startswith("CALL gds.graph.project"):
            return FakeResult(rows=[])
        if q.startswith("CALL gds.graph.drop"):
            return FakeResult(rows=[])
        if q.startswith("MATCH (n:`") and "RETURN id(n) AS id, n.ref AS ref" in q:
            label = _extract_label(q, "MATCH (n:`")
            nodes = self.store.get("labels", {}).get(label, {})
            return FakeResult(rows=[{"id": i, "ref": ref} for i, ref in enumerate(sorted(nodes.keys()))])
        if q.startswith("MATCH (a:`") and "RETURN a.ref AS app, t.ref AS tool" in q:
            label = _extract_label(q, "MATCH (a:`")
            edges = self.store.get("edges", {}).get(label, [])
            nodes = self.store.get("labels", {}).get(label, {})
            rows = []
            for (s, t) in edges:
                if nodes.get(s, {}).get("kind") == "app" and nodes.get(t, {}).get("kind") == "tool":
                    rows.append({"app": s, "tool": t})
            rows.sort(key=lambda r: (r["app"], r["tool"]))
            return FakeResult(rows=rows)
        if q.startswith("MATCH (s:`") and "RETURN s.ref AS source, t.ref AS target" in q:
            label = _extract_label(q, "MATCH (s:`")
            edges = self.store.get("edges", {}).get(label, [])
            nodes = self.store.get("labels", {}).get(label, {})
            rows = []
            for (s, t) in edges:
                if nodes.get(s, {}).get("kind") == "tool" and nodes.get(t, {}).get("kind") == "tool":
                    rows.append({"source": s, "target": t})
            rows.sort(key=lambda r: (r["source"], r["target"]))
            return FakeResult(rows=rows)
        # Default: empty result.
        return FakeResult(rows=[])

    def consume(self, result: FakeResult) -> FakeSummary:
        # Fake a delete counter for cleanup queries.
        return FakeSummary(counters={"nodes_deleted": len(result.rows)})

    def close(self) -> None:
        pass


class FakeDriver:
    def __init__(self, *, connected: bool = True, gds_available: bool = False):
        self.connected = connected
        self.store: dict[str, Any] = {"labels": {}, "edges": {}, "gds_available": gds_available}

    def verify_connectivity(self) -> None:
        if not self.connected:
            raise ConnectionError("fake driver: connectivity disabled")

    def session(self, database: str | None = None) -> FakeSession:
        return FakeSession(self.store, database=database)

    def close(self) -> None:
        pass


def _extract_label(query: str, prefix: str) -> str:
    """Pull the label string out of a query like 'MATCH (n:`LABEL`) ...'."""
    start = query.find(prefix) + len(prefix)
    end = query.find("`", start)
    return query[start:end]


def _extract_gds_graph_name(query: str) -> str:
    """Pull the graph name out of `CALL gds.<x>($name) ...`."""
    # The fake doesn't actually need the name; return a placeholder.
    return "fake"
