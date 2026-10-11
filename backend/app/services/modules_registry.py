"""Modules registry interface.

Per the architecture contract §3: a registry that validates manifests on
app boot, rejects duplicated IDs and unknown operation/validator keys, and
exposes allowlisted manifests only. This file is the **interface** plus a
trivial in-memory implementation seeded from trusted repository files.

Concrete manifests + operation handlers are wired in G05; the lab-modules
directory holds trusted fixture manifests.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Iterator

from app.core.errors import InvalidStateError
from app.core.logging import get_logger

log = get_logger(__name__)


@dataclass(frozen=True)
class ManifestRef:
    """A lightweight handle to a bundled manifest.

    Full schema validation lands in G05; this is enough for G01 to wire the
    registry API surface and a `GET /modules` listing.
    """
    id: str
    module_id: str
    version: str
    title_en: str
    title_ar: str
    description_en: str
    description_ar: str
    technology: tuple[str, ...] = ()
    public_demo_enabled: bool = True


class ModuleRegistry:
    """Holds manifests. Validation is fail-closed: unknown keys reject."""

    def __init__(self) -> None:
        self._items: dict[str, ManifestRef] = {}

    def register(self, manifest: ManifestRef) -> None:
        if not manifest.id or not manifest.module_id:
            raise InvalidStateError("manifest missing id or module_id")
        if manifest.id in self._items:
            raise InvalidStateError(
                f"duplicate manifest id: {manifest.id}",
                details={"existing_module": self._items[manifest.id].module_id},
            )
        self._items[manifest.id] = manifest
        log.info(
            "registered manifest",
            extra={"manifest_id": manifest.id, "module_id": manifest.module_id},
        )

    def all(self) -> Iterator[ManifestRef]:
        return iter(self._items.values())

    def get(self, manifest_id: str) -> ManifestRef | None:
        return self._items.get(manifest_id)

    def count(self) -> int:
        return len(self._items)


# Singleton registry. Seeded in G05 from lab-modules/*.yaml. For G01 we
# leave it empty so `GET /modules` returns `{"count": 0, "ids": []}` —
# honest, not mocked.
_registry = ModuleRegistry()


def get_registry() -> ModuleRegistry:
    return _registry
