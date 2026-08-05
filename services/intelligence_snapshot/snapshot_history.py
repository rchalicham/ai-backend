from .models import SnapshotHistory


class SnapshotHistoryEngine:
    def build(self, receipt_id, snapshots):
        return SnapshotHistory(receipt_id, tuple(item.summary for item in snapshots))

