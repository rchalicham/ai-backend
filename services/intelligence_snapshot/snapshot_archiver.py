class SnapshotArchiver:
    def apply_retention(self, repository, receipt_id, keep_last=10, archive=True, delete=False):
        history = repository.history(receipt_id)
        candidates = history[:-max(1, int(keep_last))]
        for snapshot in candidates:
            if delete: repository.delete(snapshot.header.snapshot_id)
            elif archive and snapshot.header.version.status == "active": repository.archive(snapshot.header.snapshot_id)
        return repository.history(receipt_id)

