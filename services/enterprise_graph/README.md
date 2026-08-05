# Enterprise Knowledge Graph Framework

`enterprise_graph` is the storage-agnostic, non-authoritative semantic graph
sidecar after Product Intelligence.

It maps canonical enrichments and explicit receipt context into immutable
entities and evidence-bearing relationships governed by the versioned
Enterprise Ontology. Every relationship carries additive confidence, evidence,
provenance, timestamp, version, creation source, and explanation.

The package includes deterministic construction, ontology validation,
storage-neutral traversal and domain queries, an append-only in-memory reference
repository, serialization, diagnostics, explanations, and approval-only
learning suggestions.

Runtime graph construction performs no persistence. The framework is not a
Neo4j integration, LLM memory, search engine, parser, or extraction authority.
Future Neo4j, Neptune, JanusGraph, Cosmos DB, or other adapters must preserve
the repository and semantic contracts.

