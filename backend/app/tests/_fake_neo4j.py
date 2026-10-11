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

G03-C1 note #5: the fake now records EVERY (query, params) tuple on the
session's `queries_run` list so tests can assert on query structure and
parameter correctness, not just function calls. The fake also tracks GDS
projections so `gds.louvain.stream` can return nodeIds that match the
ref-lookup query's `id(n)` values — making the nodeId→node_ref conversion
in `gds_service.detect_communities` exercisable end-to-end.

IMPORTANT: tests using this fake verify the SERVICE CODE PATH (the Cypher
we issue and how we process the result), NOT real Neo4j runtime behavior.
The real Neo4j/GDS smoke is mandatory for G07 lockdown.
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
        self._closed = False

    def __enter__(self) -> "FakeSession":
        return self

    def __exit__(self, exc_type, exc, tb) -> None:
        self.close()

    def run(self, query: str, parameters: dict | None = None, **kwargs) -> FakeResult:
        if self._closed:
            raise RuntimeError("session closed")
        # Merge positional `parameters` and `**kwargs` like the real driver.
        params = {**(parameters or {}), **kwargs}
        self.queries_run.append((query, params))
        q = query.strip()

        # ---- Capability probe queries ----
        if q.startswith("CALL dbms.components"):
            return FakeResult(rows=[{
                "name": "Neo4j Kernel",
                "versions": ["5.26.0"],
                "edition": "community",
            }])
        if q.startswith("SHOW PROCEDURES"):
            if self.store.get("gds_available"):
                return FakeResult(rows=[{"name": "gds.louvain.stream"}])
            return FakeResult(rows=[])

        # ---- Idempotency count ----
        # Specific match: count query (returns {"cnt": N})
        if q.startswith("MATCH (n:`") and "RETURN count(n) AS cnt" in q \
                and "n.kind" not in q:
            label = _extract_label(q, "MATCH (n:`")
            count = len(self.store.get("labels", {}).get(label, {}))
            return FakeResult(rows=[{"cnt": count}])

        # ---- kind_counts ----
        if q.startswith("MATCH (n:`") and "RETURN n.kind AS kind, count(n) AS cnt" in q:
            label = _extract_label(q, "MATCH (n:`")
            nodes = self.store.get("labels", {}).get(label, {})
            counts: dict[str, int] = {}
            for data in nodes.values():
                k = data.get("kind", "default")
                counts[k] = counts.get(k, 0) + 1
            rows = [{"kind": k, "cnt": v} for k, v in sorted(counts.items())]
            return FakeResult(rows=rows)

        # ---- MERGE node ----
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

        # ---- MERGE edge ----
        if q.startswith("MATCH (s:`") and "MERGE (s)-[r:`" in q:
            label = _extract_label(q, "MATCH (s:`")
            src = params.get("src")
            tgt = params.get("tgt")
            self.store.setdefault("edges", {}).setdefault(label, []).append((src, tgt))
            return FakeResult(rows=[])

        # ---- Cleanup by namespace prefix ----
        if q.startswith("MATCH (n) WHERE ANY(l IN labels(n)"):
            ns = params.get("ns_prefix", "")
            deleted = 0
            for label in list(self.store.get("labels", {}).keys()):
                if label.startswith(ns):
                    deleted += len(self.store["labels"].pop(label, {}))
            for label in list(self.store.get("edges", {}).keys()):
                if label.startswith(ns):
                    edges = self.store["edges"].pop(label, [])
                    deleted += len(edges)
            # Return a result whose consume() carries the delete counter.
            result = FakeResult(rows=[])
            result.consume = lambda: FakeSummary(counters={"nodes_deleted": deleted})  # type: ignore[assignment]
            return result

        # ---- GDS projection lifecycle ----
        # gds.graph.project($name, $nodeLabel, '*')
        if q.startswith("CALL gds.graph.project"):
            name = params.get("name")
            node_label = params.get("nodeLabel")
            if name and node_label:
                self.store.setdefault("projections", {})[name] = node_label
            return FakeResult(rows=[])

        # gds.graph.drop($name, false)
        if q.startswith("CALL gds.graph.drop"):
            name = params.get("name")
            if name and name in self.store.get("projections", {}):
                del self.store["projections"][name]
            return FakeResult(rows=[])

        # gds.louvain.stream($name) YIELD nodeId, communityId
        if q.startswith("CALL gds.louvain.stream"):
            name = params.get("name")
            projections = self.store.get("projections", {})
            label = projections.get(name, "")
            nodes = self.store.get("labels", {}).get(label, {})
            # Sort node_refs for determinism, assign each an integer id that
            # MATCHES the id(n) returned by the ref-lookup query below.
            sorted_refs = sorted(nodes.keys())
            # Partition by kind so the test can assert 3 communities for
            # the COMMUNITIES_V1 fixture (which has 3 kinds).
            rows = []
            for i, ref in enumerate(sorted_refs):
                kind = nodes[ref].get("kind", "default")
                # communityId = hash of kind so same-kind nodes cluster.
                cid = abs(hash(kind)) % 10000
                rows.append({"nodeId": i, "communityId": cid})
            return FakeResult(rows=rows)

        # ---- Ref lookup for nodeId→node_ref resolution ----
        # MATCH (n:`<label>`) RETURN id(n) AS id, n.ref AS ref
        if q.startswith("MATCH (n:`") and "RETURN id(n) AS id, n.ref AS ref" in q:
            label = _extract_label(q, "MATCH (n:`")
            nodes = self.store.get("labels", {}).get(label, {})
            # Sort for determinism; assign integer ids that match the
            # Louvain stream's nodeId values (same sort order).
            sorted_refs = sorted(nodes.keys())
            return FakeResult(rows=[
                {"id": i, "ref": ref}
                for i, ref in enumerate(sorted_refs)
            ])

        # ---- Parity queries ----
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
        # Delegate to the result's own consume() if it has been overridden
        # (e.g. for cleanup queries that carry a nodes_deleted counter).
        if hasattr(result, "consume"):
            try:
                return result.consume()  # type: ignore[operator]
            except TypeError:
                pass
        return FakeSummary(counters={"nodes_deleted": 0})

    def close(self) -> None:
        self._closed = True


class FakeDriver:
    def __init__(self, *, connected: bool = True, gds_available: bool = False):
        self.connected = connected
        self.store: dict[str, Any] = {
            "labels": {},
            "edges": {},
            "projections": {},
            "gds_available": gds_available,
        }

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
