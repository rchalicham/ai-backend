class SnapshotRegistry:
    def __init__(self, repository): self.repository = repository
    def latest(self, receipt_id): return self.repository.latest(receipt_id)
    def lookup(self, snapshot_id): return self.repository.get(snapshot_id)
    def history(self, receipt_id): return self.repository.history(receipt_id)
    def search(self, receipt_id="", family="", status=""):
        values = self.repository.history(receipt_id) if receipt_id else ()
        return tuple(item for item in values if (not family or item.metadata.document_family == family) and (not status or item.header.version.status == status))

