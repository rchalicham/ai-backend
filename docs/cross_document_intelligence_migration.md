# Cross-Document Intelligence Sidecar Migration Guide

## Compatibility

CDIF is additive. Existing requests, extraction, parser scoring, Product
Intelligence, Enterprise Graph construction, and Llama input are unchanged.
Orchestration may additionally return:

```json
{
  "crossDocumentIntelligence": {
    "schema_version": "cross-document-intelligence-v1",
    "context": {
      "entities": [],
      "related_documents": [],
      "timelines": [],
      "evidence": [],
      "correlations": [],
      "patterns": [],
      "anomalies": []
    },
    "memory": {
      "deterministic": true,
      "llm_memory": false
    },
    "diagnostics": {
      "affects_extraction": false,
      "parser_authority_changed": false,
      "documents_modified": false,
      "graph_modified": false,
      "machine_learning_used": false,
      "memory_write_performed": false
    }
  }
}
```

Consumers that ignore unknown properties require no migration.

## Historical memory onboarding

1. Supply only versioned normalized semantic memory derived from governed
   Enterprise Graph contracts.
2. Preserve document references, evidence, canonical identity, confidence,
   timestamps, versions, and provenance.
3. Keep runtime access read-only and tenant-scoped.
4. Version and archive snapshots through `CrossDocumentRepository`; never edit
   an active snapshot in place.
5. Validate correlation explanations and evidence coverage before downstream
   use.
6. Treat patterns as historical detections and anomalies as diagnostics.
7. Review every learning suggestion before changing ontology or knowledge.

Learning directly from images, OCR, parser results, source documents, or
unreviewed request memory is prohibited. Future durable stores must implement
the repository contract without leaking storage-specific APIs.

## Rollout

Begin with current-document-only observation mode, then introduce bounded
read-only historical snapshots. Compare all existing parser, Product
Intelligence, and Enterprise Graph outputs before and after activation. Missing
history or CDIF failure must degrade to an empty or current-document-only
context without affecting any upstream output.
