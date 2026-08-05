# Enterprise Learning Framework Migration Guide

## Compatibility

Enterprise Learning is an additive request-scoped sidecar after
Cross-Document Intelligence. Existing API inputs, extraction output, parser
authority, persistence behavior, and upstream architecture contracts are
unchanged. Compatible responses may now include `enterpriseLearning`.

## Runtime contract

The sidecar accepts normalized Cross-Document Intelligence only. It does not
accept raw OCR, parser guesses, or extracted Business Facts as learning truth.
Runtime evaluation produces immutable events, verified evidence, pending
proposals, explanations, quality and confidence records, and append-only audit
facts. It does not call repository `save` or `version`, approve a proposal, or
publish knowledge.

Consumers should:

1. Treat a missing `enterpriseLearning` field as sidecar degradation.
2. Treat every runtime proposal as `pending`.
3. Display evidence, provenance, confidence history, and governance warnings.
4. Invoke approval through an authenticated governance workflow outside receipt
   extraction.
5. Publish an approved proposal to a production knowledge repository only
   through that repository's separately authorized versioning process.

## Rollback

Disable or omit the Enterprise Learning sidecar. Because its output is not a
parser input and runtime performs no production writes, rollback requires no
data migration and leaves receipt extraction unchanged.
