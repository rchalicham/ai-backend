# Household Intelligence Migration Guide

## Compatibility

Household Intelligence is an additive business capability above Enterprise
Reasoning and Expense Intelligence. It introduces `householdIntelligence` and a
new REST family without changing platform services, Expense Intelligence,
parser behavior, extraction, enterprise knowledge, graph, learning, or
reasoning.

## Adoption

Supply:

1. a serialized `enterprise_reasoning` response;
2. a serialized `expense_intelligence` response; and
3. `household_data` containing an immutable Household and optional members,
   relationships, ownership, responsibilities, consumption, preferences,
   goals, assets, vehicles, properties, and pets.

Consume the complete dashboard result or focused REST views. Treat insights as
descriptive and recommendations as human-decision candidates.

Receipt API composition attaches an unassigned empty Household profile when no
explicit household evidence is available. This does not infer identity.

## Rollback

Remove Household Intelligence routers and response composition. The capability
performs no platform or Expense Intelligence writes, so rollback requires no
platform data migration.
