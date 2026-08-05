# Receipt Intelligence Snapshot Migration

## Purpose

`ReceiptIntelligenceSnapshot` is the permanent, immutable AI record for one processing execution. It is separate from the Receipt business document and from authoritative parser output.

## Runtime migration

```text
Receipt image
  -> existing parser and enterprise sidecars
  -> Presentation Projection
  -> Snapshot Builder
  -> append-only Snapshot Repository
  -> Snapshot Projection
  -> developer UI
```

The integration is additive. `receiptIntelligenceSnapshot`, `snapshotProjection`, and `snapshotHistory` are attached after processing. Parser fields and Receipt fields are neither rewritten nor removed.

## Version lifecycle

Each successful processing or reprocessing creates a new version. A version has a unique snapshot ID and points to the snapshot it supersedes. Existing versions are never overwritten. Retention policies may keep the latest N versions, archive older versions, or explicitly delete archived snapshots.

## Artifact ownership

Geometry, Receipt DOM, Enterprise Graph, and Learning artifacts remain in their owning repositories. Snapshots store `SnapshotReference` values containing artifact type, ID, version, checksum, loader, and small metadata. Consumers load these artifacts lazily.

## UI compatibility

New receipts use the snapshot context as the developer diagnostics source. Receipts created before this migration continue using legacy embedded sidecars. Reprocess an older receipt to create snapshot v1.

## Configuration

- `INTELLIGENCE_SNAPSHOT_MONGO_URI` (falls back to `MONGO_URI`)
- `INTELLIGENCE_SNAPSHOT_DATABASE` (default `receipt_intelligence`)
- `INTELLIGENCE_SNAPSHOT_COLLECTION` (default `snapshots`)

## Rollback

Disable snapshot repository configuration and the runtime uses an in-memory repository. Removing snapshot fields does not affect parser output, Receipt persistence, or Business Projection behavior.

