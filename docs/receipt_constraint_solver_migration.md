# Receipt Constraint Solver Framework Migration Guide

## Purpose

This guide introduces the Receipt Constraint Solver as a non-authoritative
sidecar immediately after Receipt Grammar. The change is additive and preserves
the current parser, APIs, extraction schemas, and production behavior.

## Runtime transition

Before:

```text
Receipt Classification
  -> Receipt Grammar sidecar
  -> Current Parser remains authoritative
```

After:

```text
Receipt Classification
  -> Receipt Grammar sidecar
  -> Receipt Constraint Solver sidecar
  -> Current Parser remains authoritative
```

The current parser continues independently from existing inputs. Neither
`receiptGrammar` nor `receiptConstraintResult` is passed to it.

## Adoption steps

1. Define immutable `ReceiptConstraint` rules for a known Receipt Family.
2. Compile the definition with `ReceiptConstraintCompiler`.
3. Resolve duplicate IDs, invalid references, missing dependencies, conflicts,
   invalid weights or penalties, and dependency cycles.
4. Save the approved set in `ReceiptConstraintRepository`.
5. Inject the repository through `ConstraintEngine`.
6. Observe candidate scores, violations, penalties, confidence, and explanations
   through `receiptConstraintResult` and the developer UI.
7. Compare decisions with reviewed sample hypotheses.
8. Version, archive, or roll back only through the governed repository
   lifecycle.

No adoption step grants extraction or Business Fact authority.

## Candidate inputs

Runtime sidecar mode generates a structural hypothesis from Receipt Grammar
compliance. Arithmetic evaluation requires explicitly supplied candidate
values. The solver does not read OCR or parser output to create monetary
hypotheses.

Examples of future supplied hypotheses include:

```json
[
  {
    "candidate_id": "candidate-a",
    "interpretation": {
      "subtotal": "10.00",
      "tax": "1.00",
      "total": "11.00",
      "sections": ["header", "items", "financial_summary", "footer"]
    }
  },
  {
    "candidate_id": "candidate-b",
    "interpretation": {
      "subtotal": "10.00",
      "discount": "1.00",
      "tax": "1.00",
      "total": "10.00",
      "sections": ["header", "items", "financial_summary", "footer"]
    }
  }
]
```

These values are hypotheses, not extracted or accepted Business Facts.

## Compatibility and degradation

- Existing request contracts are unchanged.
- `receiptConstraintResult` is an additive debug and architecture sidecar.
- Missing family, missing constraint set, invalid compilation, or unexpected
  evaluation failure produces diagnostics and leaves extraction unchanged.
- Arithmetic validators never change supplied values.
- Grammar integration consumes existing compliance and does not mutate Grammar.
- Learning creates approval-only suggestions and never writes production
  constraints.

## Rollback

Remove or disable the injected constraint repository or engine. The default
empty repository already produces a safe diagnostic result. No parser or data
migration is required because the sidecar has no extraction authority.

## Validation evidence

Before observational activation:

- compiler, dependency, conflict, and category tests pass;
- arithmetic tolerance and currency-precision tests pass;
- structural and Grammar integration tests pass;
- candidate generation, ranking, explanations, and confidence are deterministic;
- repository serialization and version comparisons round trip;
- suggestions remain approval-only;
- the developer UI exposes no production write control;
- regression tests prove current parser output is unchanged.

Any future authority requires a separate ADR, calibrated sidecar evidence,
contract governance, and satisfaction of the parser replacement gates.

