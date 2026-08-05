# Enterprise Reasoning Engine Migration Guide

## Compatibility

Enterprise Reasoning is an additive, request-scoped sidecar after Enterprise
Learning. Existing endpoints, request payloads, extraction fields, persistence,
parser authority, and upstream sidecar contracts are unchanged. Compatible
responses may now include `enterpriseReasoning`.

## Input boundary

The engine accepts read-only normalized contracts from:

- Receipt Constraint Solver
- Product Intelligence
- Enterprise Knowledge Graph
- Cross-Document Intelligence
- Enterprise Learning

Raw OCR and parser guesses are rejected by the context builder. Receipt runtime
creates a deterministic receipt-evidence question with LLM use disabled.

## Output contract

`enterpriseReasoning` contains the classified intent, immutable execution plan,
selected tools, execution traces, fused evidence, candidate hypotheses,
validation results, rejected hypotheses, a non-authoritative decision,
confidence components, explanation, and provenance. Consumers must not treat
the decision as extracted Business Facts or parser output.

## Optional LLM synthesis

An LLM requires an explicitly configured `LLMProvider`, an `allow_llm` request,
a validated decision, and traceable approved evidence. The prompt builder
rejects raw OCR and parser-guess fields. LLM text cannot replace evidence,
validation, confidence, or the deterministic decision trace.

## Rollback

Disable or omit the Enterprise Reasoning sidecar. Because it performs no
production writes and is never consumed by the current parser, rollback needs
no data migration and does not change receipt extraction.
