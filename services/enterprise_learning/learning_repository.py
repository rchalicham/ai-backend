from __future__ import annotations

from dataclasses import replace
from typing import Protocol, runtime_checkable

from .models import (
    LearningSnapshot,
    LearningSnapshotComparison,
    utc_now,
)


@runtime_checkable
class EnterpriseLearningRepositoryProtocol(Protocol):
    def load(self, snapshot_id: str, version: int | None = None) -> LearningSnapshot | None: ...
    def save(self, snapshot: LearningSnapshot) -> LearningSnapshot: ...
    def archive(self, snapshot_id: str, version: int | None = None) -> LearningSnapshot: ...
    def version(self, snapshot: LearningSnapshot, expected_version: int | None = None) -> LearningSnapshot: ...
    def compare(self, snapshot_id: str, from_version: int, to_version: int) -> LearningSnapshotComparison: ...


class EnterpriseLearningRepository:
    """Storage-neutral in-memory reference repository. Runtime never auto-writes."""

    def __init__(self) -> None:
        self._snapshots: dict[str, list[LearningSnapshot]] = {}

    def load(self, snapshot_id: str, version: int | None = None) -> LearningSnapshot | None:
        history = self._snapshots.get(snapshot_id, ())
        if version is None:
            return next((x for x in reversed(history) if x.version.status == "active"), None)
        return next((x for x in history if x.version.entity_version == version), None)

    def save(self, snapshot: LearningSnapshot) -> LearningSnapshot:
        if not snapshot.snapshot_id:
            raise ValueError("learning_snapshot_requires_identity")
        if self._snapshots.get(snapshot.snapshot_id):
            raise ValueError("learning_snapshot_already_exists_use_version")
        saved = replace(snapshot, version=replace(
            snapshot.version, entity_version=1, status="active",
            updated_at=utc_now(), supersedes_version=None,
        ))
        self._snapshots[snapshot.snapshot_id] = [saved]
        return saved

    def version(
        self, snapshot: LearningSnapshot, expected_version: int | None = None,
    ) -> LearningSnapshot:
        history = self._snapshots.get(snapshot.snapshot_id, [])
        current = history[-1] if history else None
        current_version = current.version.entity_version if current else 0
        if expected_version is not None and expected_version != current_version:
            raise ValueError("learning_snapshot_version_conflict")
        saved = replace(snapshot, version=replace(
            snapshot.version,
            entity_version=current_version + 1,
            status="active",
            created_at=current.version.created_at if current else snapshot.version.created_at,
            updated_at=utc_now(),
            supersedes_version=current_version or None,
        ))
        self._snapshots.setdefault(snapshot.snapshot_id, []).append(saved)
        return saved

    def archive(self, snapshot_id: str, version: int | None = None) -> LearningSnapshot:
        history = self._snapshots.get(snapshot_id, [])
        value = self.load(snapshot_id, version)
        if value is None:
            raise KeyError("learning_snapshot_not_found")
        archived = replace(value, version=replace(
            value.version, status="archived", updated_at=utc_now(),
        ))
        history[history.index(value)] = archived
        return archived

    def compare(
        self, snapshot_id: str, from_version: int, to_version: int,
    ) -> LearningSnapshotComparison:
        before = self.load(snapshot_id, from_version)
        after = self.load(snapshot_id, to_version)
        if before is None or after is None:
            raise KeyError("learning_snapshot_version_not_found")
        old = {x.proposal_id: x for x in before.proposals}
        new = {x.proposal_id: x for x in after.proposals}
        old_audit = {x.audit_id for x in before.audit}
        return LearningSnapshotComparison(
            snapshot_id,
            from_version,
            to_version,
            tuple(sorted(set(new) - set(old))),
            tuple(sorted(set(old) - set(new))),
            tuple(sorted(k for k in set(old) & set(new) if old[k] != new[k])),
            tuple(sorted(x.audit_id for x in after.audit if x.audit_id not in old_audit)),
        )
