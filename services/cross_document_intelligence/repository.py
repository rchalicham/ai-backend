from __future__ import annotations

from dataclasses import replace
from typing import Protocol, runtime_checkable

from .models import MemoryComparison, MemorySnapshot, utc_now


@runtime_checkable
class CrossDocumentRepositoryProtocol(Protocol):
    def load(self, memory_id: str, version: int | None = None) -> MemorySnapshot | None: ...
    def save(self, memory: MemorySnapshot) -> MemorySnapshot: ...
    def archive(self, memory_id: str, version: int | None = None) -> MemorySnapshot: ...
    def version(self, memory: MemorySnapshot, expected_version: int | None = None) -> MemorySnapshot: ...
    def compare(self, memory_id: str, from_version: int, to_version: int) -> MemoryComparison: ...


class CrossDocumentRepository:
    """In-memory reference repository; runtime reads but never auto-writes."""

    def __init__(self) -> None:
        self._memory: dict[str, list[MemorySnapshot]] = {}

    def load(self, memory_id: str, version: int | None = None) -> MemorySnapshot | None:
        history = self._memory.get(memory_id, ())
        if version is None:
            return next((item for item in reversed(history) if item.version.status == "active"), None)
        return next((item for item in history if item.version.entity_version == version), None)

    def save(self, memory: MemorySnapshot) -> MemorySnapshot:
        if not memory.memory_id:
            raise ValueError("cross_document_memory_requires_identity")
        if self._memory.get(memory.memory_id):
            raise ValueError("cross_document_memory_already_exists_use_version")
        saved = replace(memory, version=replace(
            memory.version, entity_version=1, status="active",
            updated_at=utc_now(), supersedes_version=None,
        ))
        self._memory[memory.memory_id] = [saved]
        return saved

    def version(
        self, memory: MemorySnapshot, expected_version: int | None = None,
    ) -> MemorySnapshot:
        history = self._memory.get(memory.memory_id, [])
        current = history[-1] if history else None
        current_version = current.version.entity_version if current else 0
        if expected_version is not None and expected_version != current_version:
            raise ValueError("cross_document_memory_version_conflict")
        saved = replace(memory, version=replace(
            memory.version,
            entity_version=current_version + 1,
            status="active",
            created_at=current.version.created_at if current else memory.version.created_at,
            updated_at=utc_now(),
            supersedes_version=current_version or None,
        ))
        self._memory.setdefault(memory.memory_id, []).append(saved)
        return saved

    def archive(self, memory_id: str, version: int | None = None) -> MemorySnapshot:
        history = self._memory.get(memory_id, [])
        value = self.load(memory_id, version)
        if value is None:
            raise KeyError("cross_document_memory_not_found")
        archived = replace(value, version=replace(
            value.version, status="archived", updated_at=utc_now(),
        ))
        history[history.index(value)] = archived
        return archived

    def compare(self, memory_id: str, from_version: int, to_version: int) -> MemoryComparison:
        before = self.load(memory_id, from_version)
        after = self.load(memory_id, to_version)
        if before is None or after is None:
            raise KeyError("cross_document_memory_version_not_found")
        before_documents = {item.document_id for item in before.documents}
        after_documents = {item.document_id for item in after.documents}
        before_entities = {item.entity_id: item for item in before.entities}
        after_entities = {item.entity_id: item for item in after.entities}
        return MemoryComparison(
            memory_id,
            from_version,
            to_version,
            tuple(sorted(after_documents - before_documents)),
            tuple(sorted(before_documents - after_documents)),
            tuple(sorted(set(after_entities) - set(before_entities))),
            tuple(sorted(set(before_entities) - set(after_entities))),
            tuple(sorted(
                key for key in set(before_entities) & set(after_entities)
                if before_entities[key] != after_entities[key]
            )),
        )

    def list_memory(self, include_archived: bool = False) -> tuple[MemorySnapshot, ...]:
        values = tuple(
            history[-1] for _, history in sorted(self._memory.items()) if history
        )
        return values if include_archived else tuple(
            item for item in values if item.version.status == "active"
        )

