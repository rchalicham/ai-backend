class SnapshotValidator:
    def validate(self, snapshot):
        errors = []
        if not snapshot.header.snapshot_id: errors.append("missing_snapshot_id")
        if not snapshot.header.receipt_id: errors.append("missing_receipt_id")
        if snapshot.header.version.number < 1: errors.append("invalid_version")
        if snapshot.diagnostics.parser_modified: errors.append("parser_modified")
        if snapshot.diagnostics.receipt_modified: errors.append("receipt_modified")
        if snapshot.diagnostics.large_artifacts_embedded: errors.append("large_artifacts_embedded")
        return tuple(errors)

