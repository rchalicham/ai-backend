# Expense Intelligence Migration Guide

## Compatibility

Expense Intelligence is the first business capability above the completed
platform. It introduces an additive `expenseIntelligence` response and a new
REST endpoint family. Existing platform inputs, outputs, package contracts,
parser behavior, extraction, knowledge, graph, learning, and reasoning remain
unchanged.

## Adoption

1. Supply a serialized `enterpriseReasoning` response.
2. Supply immutable Expense records with document and evidence identifiers.
3. Optionally supply Budget definitions.
4. Consume the complete dashboard result or a focused summary endpoint.
5. Treat trends as observations, anomalies as diagnostics, and recommendations
   as human-decision candidates.

## Receipt composition

Receipt endpoints attach an Expense Intelligence result in the API composition
root after receipt orchestration returns. The receipt orchestrator and all
platform services remain unchanged. A request with no explicit Expense records
returns a valid empty business-capability result.

## Rollback

Remove the Expense Intelligence routers and response attachment. Because the
capability performs no platform writes and is not consumed by the parser,
rollback requires no platform data migration.
