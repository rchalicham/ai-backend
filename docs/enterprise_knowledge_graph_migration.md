# Enterprise Knowledge Graph Sidecar Migration Guide

## Compatibility

The Enterprise Knowledge Graph Framework is additive. Existing requests,
parser inputs, parser scoring, Product Intelligence, Llama input, and
`semantic` output remain unchanged. Orchestration may additionally return:

```json
{
  "enterpriseKnowledgeGraph": {
    "schema_version": "enterprise-graph-context-v1",
    "graph": {
      "graph_id": "receipt-graph:receipt-id",
      "nodes": [],
      "edges": [],
      "ontology_version": "enterprise-ontology-v1"
    },
    "diagnostics": {
      "sidecar": true,
      "affects_extraction": false,
      "parser_authority_changed": false,
      "storage_write_performed": false
    }
  }
}
```

Consumers that ignore unknown properties require no migration.

## Ontology and adapter onboarding

1. Reuse an existing ontology definition where its semantics fit.
2. Add a versioned domain extension when a new entity or relationship meaning
   is required; do not overload an existing type.
3. Preserve stable entity identity, edge evidence, provenance, additive
   confidence, timestamp, version, creation source, and explanation.
4. Validate graphs before exposing them to downstream consumers.
5. Implement durable graph stores behind `EnterpriseGraphRepository` and query
   contracts. Do not expose Neo4j, Neptune, JanusGraph, Cosmos DB, or another
   storage dialect to graph consumers.
6. Separate runtime read/write identities, tenant scope, audit history,
   retention, and rollback.
7. Review every Graph Learning suggestion before changing ontology or approved
   knowledge.

## Rollout

Deploy first in request-scoped observation mode. Compare parser and Product
Intelligence output before and after activation, inspect graph validation and
relationship explanations, and measure node/edge coverage. No durable graph
write is part of this phase.

The future Learning Engine must consume governed normalized semantic graph
outcomes. Learning directly from receipt images, OCR, isolated parser output,
or unreviewed request graphs is prohibited.

