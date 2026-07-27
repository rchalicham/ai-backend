# Receipt Classification Migration Guide

## Compatibility

No caller migration is required. Existing extraction inputs and outputs remain
unchanged. Image-backed orchestrator responses may additionally contain
`receiptClassification`; parsers ignore this sidecar.

## Enabling family comparisons

1. Keep using the existing explicit `merchant_knowledge_key` request option.
2. Add a versioned physical feature profile to a `ReceiptFamily.attributes`
   entry in Merchant Intelligence.
3. Observe comparisons and ranked candidates in the developer debug panel.
4. Review learning suggestions externally. The runtime never persists or
   approves them.

Without an explicitly loaded blueprint, `receiptClassification.feature_vector`
is still populated and `candidates` remains empty.

## Schema evolution

- Feature vectors identify both `schema_version` and numeric `version`.
- Family profiles retain the repository entity version.
- Additive metrics are safe: similarity uses the intersection and reports
  coverage.
- Breaking metric changes require a new feature-vector version and a profile
  migration.
- Similarity strategies are injectable and should retain stable names for
  diagnostics.

## Operational rollback

The subsystem is fail-open. A sidecar failure returns no classification and the
existing parser continues. Removing family physical profiles disables matching
without affecting repository knowledge or receipt extraction.

## Ownership boundary

Classification may propose feature-distribution observations. Production
blueprint updates belong to a future approval workflow in Merchant Intelligence.
Classification must never write repository state, inspect OCR text, or promote a
family candidate into merchant identity.
