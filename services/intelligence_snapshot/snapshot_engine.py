from __future__ import annotations

from threading import RLock

from .snapshot_archiver import SnapshotArchiver
from .snapshot_builder import SnapshotBuilder
from .snapshot_comparison import SnapshotComparisonEngine
from .snapshot_history import SnapshotHistoryEngine
from .snapshot_projection import SnapshotProjectionEngine
from .snapshot_validator import SnapshotValidator


class ReceiptIntelligenceSnapshotEngine:
    def __init__(self, repository, builder=None, validator=None):
        self.repository = repository
        self.builder = builder or SnapshotBuilder()
        self.validator = validator or SnapshotValidator()
        self.comparison = SnapshotComparisonEngine()
        self.history_engine = SnapshotHistoryEngine()
        self.projection_engine = SnapshotProjectionEngine()
        self.archiver = SnapshotArchiver()
        self._capture_lock = RLock()

    def capture(self, orchestration, *, receipt_id, tenant_id="default", execution_time_ms=0.0):
        with self._capture_lock:
            latest = self.repository.latest(receipt_id)
            version = latest.header.version.number + 1 if latest else 1
            snapshot = self.builder.build(
                orchestration, receipt_id=receipt_id, version=version,
                supersedes_snapshot_id=latest.header.snapshot_id if latest else "",
                tenant_id=tenant_id, execution_time_ms=execution_time_ms,
            )
            errors = self.validator.validate(snapshot)
            if errors: raise ValueError("invalid_snapshot:" + ",".join(errors))
            return self.repository.save(snapshot)

    def latest(self, receipt_id): return self.repository.latest(receipt_id)
    def load(self, snapshot_id): return self.repository.get(snapshot_id)
    def history(self, receipt_id): return self.history_engine.build(receipt_id, self.repository.history(receipt_id))
    def compare(self, before_id, after_id):
        before, after = self.load(before_id), self.load(after_id)
        if before is None or after is None: raise KeyError("snapshot_not_found")
        return self.comparison.compare(before, after)
    def project(self, snapshot): return self.projection_engine.project(snapshot)
