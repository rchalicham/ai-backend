class SnapshotDiagnosticsEngine:
    def summarize(self, snapshot):
        return {
            "snapshotId": snapshot.header.snapshot_id,
            "receiptId": snapshot.header.receipt_id,
            "version": snapshot.header.version.number,
            "referenceCount": len(snapshot.references),
            "warningCount": len(snapshot.diagnostics.warnings),
            "parserModified": snapshot.diagnostics.parser_modified,
            "receiptModified": snapshot.diagnostics.receipt_modified,
        }

