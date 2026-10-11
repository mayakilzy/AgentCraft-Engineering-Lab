"""Graph endpoints — session-scoped CRUD and Cytoscape.js-ready read.

Per the contract §4:
- GET  /api/v1/graph/{dataset_id}        → Cytoscape elements list
- POST /api/v1/graph/{dataset_id}/nodes → add a node (scoped)
- POST /api/v1/graph/{dataset_id}/edges → add a directed edge (scoped)
- POST /api/v1/graph/{dataset_id}/seed  → load a deterministic fixture
"""
from __future__ import annotations

from fastapi import APIRouter, status

from app.api.deps import DbDep, GuestSessionDep, SettingsDep
from app.models.guest_session import GuestSession
from app.schemas.graph import (
    CytoscapeElement,
    CytoscapeEdgeData,
    CytoscapeNodeData,
    EdgeCreate,
    EdgeCreatedResponse,
    EdgeRead,
    GraphReadResponse,
    NodeCreate,
    NodeCreatedResponse,
    NodeRead,
)
from app.services import graph_service

router = APIRouter(prefix="/graph", tags=["graph"])


@router.get(
    "/{dataset_id}",
    response_model=GraphReadResponse,
)
def read_graph(
    dataset_id: str,
    db: DbDep,
    session: GuestSessionDep,
) -> GraphReadResponse:
    nodes = graph_service.list_nodes(db, session, dataset_id)
    edges = graph_service.list_edges(db, session, dataset_id)

    elements: list[CytoscapeElement] = []
    for n in nodes:
        elements.append(
            CytoscapeElement(
                group="nodes",
                data=CytoscapeNodeData(
                    id=n.node_ref, label=n.label, kind=n.kind
                ),
            )
        )
    for e, src_ref, tgt_ref in edges:
        elements.append(
            CytoscapeElement(
                group="edges",
                data=CytoscapeEdgeData(
                    id=str(e.id),
                    source=src_ref,
                    target=tgt_ref,
                    relation=e.relation,
                ),
            )
        )

    return GraphReadResponse(
        dataset_id=dataset_id,
        session_id=session.id,
        elements=elements,
        node_count=len(nodes),
        edge_count=len(edges),
    )


@router.post(
    "/{dataset_id}/nodes",
    response_model=NodeCreatedResponse,
    status_code=status.HTTP_201_CREATED,
)
def add_node(
    dataset_id: str,
    payload: NodeCreate,
    db: DbDep,
    settings: SettingsDep,
    session: GuestSessionDep,
) -> NodeCreatedResponse:
    node = graph_service.add_node(
        db, settings, session, dataset_id,
        node_ref=payload.node_ref,
        kind=payload.kind,
        label=payload.label,
        attributes=payload.attributes,
    )
    return NodeCreatedResponse(
        node=NodeRead(
            id=node.id,
            node_ref=node.node_ref,
            kind=node.kind,
            label=node.label,
            attributes=node.attributes_json,
        )
    )


@router.post(
    "/{dataset_id}/edges",
    response_model=EdgeCreatedResponse,
    status_code=status.HTTP_201_CREATED,
)
def add_edge(
    dataset_id: str,
    payload: EdgeCreate,
    db: DbDep,
    settings: SettingsDep,
    session: GuestSessionDep,
) -> EdgeCreatedResponse:
    edge, src_ref, tgt_ref = graph_service.add_edge(
        db, settings, session, dataset_id,
        source_ref=payload.source_ref,
        target_ref=payload.target_ref,
        relation=payload.relation,
        attributes=payload.attributes,
    )
    return EdgeCreatedResponse(
        edge=EdgeRead(
            id=edge.id,
            source_ref=src_ref,
            target_ref=tgt_ref,
            relation=edge.relation,
            attributes=edge.attributes_json,
        )
    )
