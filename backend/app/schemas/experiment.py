"""Experiment + Module DTOs. Concrete manifests wired in G05."""
from __future__ import annotations

from typing import List, Literal
from uuid import UUID

from pydantic import BaseModel, Field


class LocalizedText(BaseModel):
    """A bilingual string. Technical symbols stay untranslated per A12."""
    en: str
    ar: str


class ModuleSummary(BaseModel):
    id: str
    version: str
    title: LocalizedText
    description: LocalizedText
    technology: List[str] = Field(default_factory=list)
    public_demo_enabled: bool = True


class ExperimentSummary(BaseModel):
    id: str
    module_id: str
    version: str
    title: LocalizedText
    description: LocalizedText
    level: Literal["beginner", "intermediate", "advanced"]
    estimated_minutes: int
    prerequisites: List[str] = Field(default_factory=list)
    dataset_key: str
    required_services: List[str] = Field(default_factory=list)
    capabilities: List[str] = Field(default_factory=list)
    public_demo_enabled: bool = True


class ExperimentDetail(ExperimentSummary):
    """Full experiment with steps. Returned by GET /experiments/{id}."""
    pass  # steps model will be added when manifests are wired (G05)


class ModuleRegistryMeta(BaseModel):
    count: int
    ids: List[str]
