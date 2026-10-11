"""Graph DTOs — request/response models for the scoped graph API.

Per the architecture contract §6: nodes are `{id,label,kind,attributes}`;
directed edges are `{id,source,target,relation,attributes}` with the
invariant that source/target exist and are scoped to the same session.
"""
from __future__ import annotations

from typing import Any, Dict, List, Optional
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, field_validator


class NodeCreate(BaseModel):
    """Client-submitted node. `node_ref` is the stable external id used by
    fixtures; the database primary key is a UUID minted server-side.
    """

    model_config = ConfigDict(extra="forbid")

    node_ref: str = Field(..., min_length=1, max_length=128)
    kind: str = Field(..., min_length=1, max_length=64)
    label: str = Field(..., min_length=1, max_length=255)
    attributes: Optional[Dict[str, Any]] = None


class NodeRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    node_ref: str
    kind: str
    label: str
    attributes: Optional[Dict[str, Any]] = None


class EdgeCreate(BaseModel):
    """Client-submitted edge. `source_ref`/`target_ref` are node_refs in the
    same dataset; the service resolves them to node UUIDs server-side and
    rejects cross-session/cross-dataset endpoints.
    """

    model_config = ConfigDict(extra="forbid")

    source_ref: str = Field(..., min_length=1, max_length=128)
    target_ref: str = Field(..., min_length=1, max_length=128)
    relation: str = Field(..., min_length=1, max_length=64)
    attributes: Optional[Dict[str, Any]] = None

    @field_validator("source_ref", "target_ref")
    @classmethod
    def _non_empty(cls, v: str) -> str:
        if not v or not v.strip():
            raise ValueError("must not be empty")
        return v


class EdgeRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    source_ref: str
    target_ref: str
    relation: str
    attributes: Optional[Dict[str, Any]] = None


class CytoscapeNodeData(BaseModel):
    id: str
    label: str
    kind: str


class CytoscapeEdgeData(BaseModel):
    id: str
    source: str  # Cytoscape expects node ids here
    target: str
    relation: str


class CytoscapeElement(BaseModel):
    """One Cytoscape.js element (node or edge).

    `group` is `"nodes"` or `"edges"` — Cytoscape.js field name.
    """

    group: str
    data: CytoscapeNodeData | CytoscapeEdgeData


class GraphReadResponse(BaseModel):
    """Response for `GET /api/v1/graph/{dataset_id}` — Cytoscape.js-ready."""

    dataset_id: str
    session_id: UUID
    elements: List[CytoscapeElement]
    node_count: int
    edge_count: int


class NodeCreatedResponse(BaseModel):
    node: NodeRead


class EdgeCreatedResponse(BaseModel):
    edge: EdgeRead
