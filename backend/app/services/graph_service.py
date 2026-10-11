"""Graph storage service — scoped CRUD with referential integrity,
cardinality limits, and session isolation.

Per the architecture contract §2 + §6 + §9:
- All reads/writes scoped server-side by the cookie session; no
  client-provided session_id is ever trusted.
- Directed edges require source/target to exist in the same session AND
  the same dataset. Cross-session or cross-dataset endpoints are rejected.
- Cardinality caps enforced via `Settings.max_graph_nodes` /
  `Settings.max_graph_edges`.
- Graph nodes/edges are immutable once stored in a terminal run; for G02
  we expose scoped insert + list (delete comes with reset in later groups).
"""
from __future__ import annotations

import uuid
from typing import Iterable, List

from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.config import Settings
from app.core.errors import (
    AppError,
    InvalidStateError,
    NotFoundError,
)
from app.core.logging import get_logger
from app.models.graph import GraphEdge, GraphNode
from app.models.guest_session import GuestSession

log = get_logger(__name__)


# ---- Node ops ----

def add_node(
    db: Session,
    settings: Settings,
    session: GuestSession,
    dataset_id: str,
    *,
    node_ref: str,
    kind: str,
    label: str,
    attributes: dict | None = None,
) -> GraphNode:
    """Insert a node scoped to (session, dataset). Rejects duplicate refs."""
    _check_dataset_id(dataset_id)
    _enforce_cardinality_node(db, settings, session.id, dataset_id)

    existing = _get_node_by_ref(db, session.id, dataset_id, node_ref)
    if existing is not None:
        raise InvalidStateError(
            f"node_ref {node_ref!r} already exists in this dataset",
            details={"dataset_id": dataset_id, "node_ref": node_ref},
        )

    node = GraphNode(
        id=uuid.uuid4(),
        session_id=session.id,
        dataset_id=dataset_id,
        node_ref=node_ref,
        kind=kind,
        label=label,
        attributes_json=attributes,
    )
    db.add(node)
    try:
        db.commit()
    except IntegrityError as exc:
        db.rollback()
        raise InvalidStateError(
            "node insert rejected by integrity constraint",
            details={"reason": str(exc.orig) if exc.orig else "integrity"},
        ) from exc
    db.refresh(node)
    return node


def add_edge(
    db: Session,
    settings: Settings,
    session: GuestSession,
    dataset_id: str,
    *,
    source_ref: str,
    target_ref: str,
    relation: str,
    attributes: dict | None = None,
) -> GraphEdge:
    """Insert a directed edge scoped to (session, dataset).

    Rejects:
    - source/target node missing in the same (session, dataset)
    - self-loop unless explicitly allowed (V1: disallow)
    - duplicate (source, target, relation) — DB unique constraint
    - cardinality cap exceeded
    """
    _check_dataset_id(dataset_id)
    _enforce_cardinality_edge(db, settings, session.id, dataset_id)

    if source_ref == target_ref:
        raise InvalidStateError(
            "self-loop edges are not allowed in V1",
            details={"node_ref": source_ref},
        )

    src = _get_node_by_ref(db, session.id, dataset_id, source_ref)
    if src is None:
        raise NotFoundError(
            f"source node_ref {source_ref!r} not found in this dataset",
            details={"dataset_id": dataset_id, "node_ref": source_ref},
        )
    tgt = _get_node_by_ref(db, session.id, dataset_id, target_ref)
    if tgt is None:
        raise NotFoundError(
            f"target node_ref {target_ref!r} not found in this dataset",
            details={"dataset_id": dataset_id, "node_ref": target_ref},
        )

    # Cross-session is structurally impossible (the lookup is scoped to
    # session.id), but we assert explicitly so the test can document the
    # invariant.
    assert src.session_id == session.id and tgt.session_id == session.id
    assert src.session_id == tgt.session_id

    edge = GraphEdge(
        id=uuid.uuid4(),
        session_id=session.id,
        dataset_id=dataset_id,
        source_id=src.id,
        target_id=tgt.id,
        relation=relation,
        attributes_json=attributes,
    )
    db.add(edge)
    try:
        db.commit()
    except IntegrityError as exc:
        db.rollback()
        raise InvalidStateError(
            "edge insert rejected by integrity constraint (duplicate?)",
            details={"reason": str(exc.orig) if exc.orig else "integrity"},
        ) from exc
    db.refresh(edge)
    return edge, src.node_ref, tgt.node_ref


# ---- List/read ----

def list_nodes(
    db: Session, session: GuestSession, dataset_id: str
) -> List[GraphNode]:
    _check_dataset_id(dataset_id)
    stmt = (
        select(GraphNode)
        .where(GraphNode.session_id == session.id)
        .where(GraphNode.dataset_id == dataset_id)
        .order_by(GraphNode.node_ref)
    )
    return list(db.execute(stmt).scalars())


def list_edges(
    db: Session, session: GuestSession, dataset_id: str
) -> List[tuple[GraphEdge, str, str]]:
    """Return edges with their source/target node_refs resolved.

    We alias `GraphNode` twice (once for source, once for target) so the
    `node_ref` column doesn't become ambiguous in the join.
    """
    _check_dataset_id(dataset_id)
    from sqlalchemy.orm import aliased

    SrcNode = aliased(GraphNode)
    TgtNode = aliased(GraphNode)
    stmt = (
        select(GraphEdge, SrcNode.node_ref, TgtNode.node_ref)
        .where(GraphEdge.session_id == session.id)
        .where(GraphEdge.dataset_id == dataset_id)
        .join(SrcNode, GraphEdge.source_id == SrcNode.id)
        .join(TgtNode, GraphEdge.target_id == TgtNode.id)
        .order_by(GraphEdge.relation, GraphEdge.id)
    )
    return [(e, s_ref, t_ref) for (e, s_ref, t_ref) in db.execute(stmt).all()]


def get_dataset_summary(
    db: Session, session: GuestSession, dataset_id: str
) -> dict:
    """Counts of nodes/edges in this (session, dataset)."""
    _check_dataset_id(dataset_id)
    n_count = db.execute(
        select(func.count(GraphNode.id))
        .where(GraphNode.session_id == session.id)
        .where(GraphNode.dataset_id == dataset_id)
    ).scalar_one()
    e_count = db.execute(
        select(func.count(GraphEdge.id))
        .where(GraphEdge.session_id == session.id)
        .where(GraphEdge.dataset_id == dataset_id)
    ).scalar_one()
    return {"dataset_id": dataset_id, "node_count": int(n_count), "edge_count": int(e_count)}


# ---- Seed fixture loader ----

def load_fixture(
    db: Session,
    settings: Settings,
    session: GuestSession,
    target_dataset_id: str,
    fixture_key: str,
) -> dict:
    """Idempotently load a named fixture into a (session, dataset) scope.

    `target_dataset_id` is the caller-chosen dataset scope name (the path
    parameter on the API). `fixture_key` selects which seeded fixture to
    load (e.g., "starter-five-v1"). If the target dataset already has rows,
    the loader is a no-op (deterministic reruns); the caller gets back the
    existing counts.
    """
    from app.fixtures.graph_seed import get_fixture

    fixture = get_fixture(fixture_key)
    if fixture is None:
        raise NotFoundError(f"unknown fixture: {fixture_key}")

    summary = get_dataset_summary(db, session, target_dataset_id)
    if summary["node_count"] == 0 and summary["edge_count"] == 0:
        for n in fixture.nodes:
            add_node(
                db, settings, session, target_dataset_id,
                node_ref=n.ref, kind=n.kind, label=n.label,
                attributes=dict(n.attributes),
            )
        for e in fixture.edges:
            add_edge(
                db, settings, session, target_dataset_id,
                source_ref=e.source_ref, target_ref=e.target_ref,
                relation=e.relation, attributes=dict(e.attributes),
            )
    log.info(
        "loaded fixture",
        extra={
            "target_dataset_id": target_dataset_id,
            "fixture_key": fixture_key,
            "node_count": summary["node_count"] or len(fixture.nodes),
            "edge_count": summary["edge_count"] or len(fixture.edges),
        },
    )
    return get_dataset_summary(db, session, target_dataset_id)


# ---- Helpers / guards ----

def _check_dataset_id(dataset_id: str) -> None:
    if not dataset_id or not isinstance(dataset_id, str) or len(dataset_id) > 128:
        raise AppError(
            "invalid dataset_id",
            status_code=400,
            code="bad_request",
            details={"dataset_id": dataset_id},
        )


def _enforce_cardinality_node(
    db: Session, settings: Settings, session_id: uuid.UUID, dataset_id: str
) -> None:
    count = db.execute(
        select(func.count(GraphNode.id))
        .where(GraphNode.session_id == session_id)
        .where(GraphNode.dataset_id == dataset_id)
    ).scalar_one()
    if int(count) >= settings.max_graph_nodes:
        raise InvalidStateError(
            "max_graph_nodes exceeded",
            details={
                "limit": settings.max_graph_nodes,
                "dataset_id": dataset_id,
            },
        )


def _enforce_cardinality_edge(
    db: Session, settings: Settings, session_id: uuid.UUID, dataset_id: str
) -> None:
    count = db.execute(
        select(func.count(GraphEdge.id))
        .where(GraphEdge.session_id == session_id)
        .where(GraphEdge.dataset_id == dataset_id)
    ).scalar_one()
    if int(count) >= settings.max_graph_edges:
        raise InvalidStateError(
            "max_graph_edges exceeded",
            details={
                "limit": settings.max_graph_edges,
                "dataset_id": dataset_id,
            },
        )


def _get_node_by_ref(
    db: Session, session_id: uuid.UUID, dataset_id: str, node_ref: str
) -> GraphNode | None:
    stmt = (
        select(GraphNode)
        .where(GraphNode.session_id == session_id)
        .where(GraphNode.dataset_id == dataset_id)
        .where(GraphNode.node_ref == node_ref)
    )
    return db.execute(stmt).scalar_one_or_none()
