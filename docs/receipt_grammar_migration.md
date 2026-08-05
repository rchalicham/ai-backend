# Receipt Grammar Framework Migration Guide

## Purpose

This guide introduces the Receipt Grammar Framework as a non-authoritative
sidecar immediately after Receipt Classification. It changes no extraction API,
parser input, parser output, OCR behavior, or production authority.

## Before and after

Before:

```text
Receipt DOM
  -> Physical Structure
  -> Merchant Knowledge
  -> Receipt Classification
  -> Current Parser
```

After:

```text
Receipt DOM
  -> Physical Structure
  -> Merchant Knowledge
  -> Receipt Classification
  -> Receipt Grammar sidecar
  -> Current Parser remains authoritative
```

The sidecar runs in the request scope. If no family is classified, no matching
grammar exists, compilation fails, or validation raises an unexpected error,
the orchestrator returns diagnostic `receiptGrammar` context and continues the
existing extraction path unchanged.

## Adoption steps

1. Author a `ReceiptGrammar` for a known `ReceiptFamily`.
2. Compile it with `ReceiptGrammarCompiler`.
3. Resolve every compilation error before repository activation.
4. Save the approved definition in `ReceiptGrammarRepository` under the exact
   classified family identifier.
5. Inject the repository through `ReceiptGrammarEngine` into
   `ReceiptAgentOrchestrator`.
6. Observe `receiptGrammar.compliance`, violations, warnings, candidate roles,
   and approval-only learning suggestions.
7. Compare sidecar results with reviewed receipt samples.
8. Version or archive grammar definitions through the repository lifecycle.

No adoption step grants parser authority to Receipt Grammar.

## Compatibility

- Existing routes and request schemas are unchanged.
- Existing `donut`, `semantic`, `llama`, `receiptDocument`,
  `receiptStructure`, `receiptClassification`, `merchantIntelligence`, and
  `receiptAgent` response members retain their behavior.
- `receiptGrammar` is an additive debug and architecture sidecar.
- The current parser does not consume `receiptGrammar`.
- An empty or unavailable grammar repository does not change extraction.
- Grammar learning generates suggestions only.

## Rollback

Rollback requires removing or disabling the injected grammar repository or
engine. Because the sidecar is not an input to extraction, rollback does not
require data conversion or parser migration. Archived grammar versions and
diagnostic output remain available for audit according to retention policy.

## Validation evidence

Before enabling an authored grammar for observation:

- compilation and cycle tests pass;
- references, transitions, relationships, required sections, optional sections,
  and rule conflicts are validated;
- serialization round trips without loss;
- repository optimistic version checks pass;
- compliance is tested against representative receipt samples;
- learning suggestions remain approval-only;
- sidecar failure and missing-grammar behavior leave semantic output unchanged;
- the Receipt Grammar developer tab exposes no production write action.

## Future authority

Receipt Grammar provides declarative semantic expectations for future
Constraint Solver and Product Intelligence stages. Any transfer of runtime
authority requires a separate ADR, measured sidecar evidence, contract review,
and the parser replacement gates in the Enterprise Architecture Specification.

