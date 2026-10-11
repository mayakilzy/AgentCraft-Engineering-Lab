"""Allowlisted Cypher queries for T10 (relational vs graph parity).

Per the architecture contract §6: 'Neo4j import uses session-scoped
dataset and cleanup, with reserved namespace; no arbitrary Cypher input.'

Only the queries defined here are runnable; the parity service refuses
any unknown query_key. Each query is parameterised (no string-interpolated
user input).
"""
from __future__ import annotations

# A query is a (key, cypher_template) pair. Parameters are bound at call site.
ALLOWLISTED_CYPHER: dict[str, str] = {
    # E04 parity query: find all (app, tool) pairs where app uses tool directly.
    "app_uses_tool_direct": (
        "MATCH (a:`{label}` {kind: 'app'})-[:APP_USES_TOOL]->(t:`{label}` {kind: 'tool'}) "
        "RETURN a.ref AS app, t.ref AS tool ORDER BY app, tool"
    ),
    # Transitive dependency: tools reachable from a given app via any path.
    "app_transitive_tools": (
        "MATCH (a:`{label}` {kind: 'app', ref: $app_ref})-[:APP_USES_TOOL|TOOL_DEPENDS_ON_TOOL*]->(t:`{label}` {kind: 'tool'}) "
        "RETURN DISTINCT a.ref AS app, t.ref AS tool ORDER BY tool"
    ),
    # Direct tool-to-tool dependencies.
    "tool_depends_on_tool": (
        "MATCH (s:`{label}` {kind: 'tool'})-[:TOOL_DEPENDS_ON_TOOL]->(t:`{label}` {kind: 'tool'}) "
        "RETURN s.ref AS source, t.ref AS target ORDER BY source, target"
    ),
    # Count nodes + edges per kind for sanity.
    "kind_counts": (
        "MATCH (n:`{label}`) "
        "RETURN n.kind AS kind, count(n) AS cnt ORDER BY kind"
    ),
}


def get_query(query_key: str, label: str) -> str:
    """Return the parameterised Cypher for `query_key`, with `{label}`
    substituted by the session-scoped label. Unknown keys raise.
    """
    if query_key not in ALLOWLISTED_CYPHER:
        from app.core.errors import InvalidStateError
        raise InvalidStateError(
            f"unknown cypher query_key: {query_key}",
            details={"requested": query_key},
        )
    # Use .replace() instead of .format() because the queries contain
    # literal `{kind: 'app'}` blocks that .format() would try to interpolate.
    return ALLOWLISTED_CYPHER[query_key].replace("{label}", label)


def allowlisted_keys() -> list[str]:
    return sorted(ALLOWLISTED_CYPHER.keys())
