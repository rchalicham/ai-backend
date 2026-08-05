from .snapshot_loader import SnapshotLoader
from .snapshot_repository import InMemorySnapshotRepository
from .snapshot_engine import ReceiptIntelligenceSnapshotEngine


def load_snapshot_engine(repository=None):
    return ReceiptIntelligenceSnapshotEngine(repository or InMemorySnapshotRepository())


__all__ = ["SnapshotLoader", "load_snapshot_engine"]

