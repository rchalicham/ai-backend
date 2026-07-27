# Merchant Intelligence Repository Migration

## Current phase

The repository is optional infrastructure. Existing receipt requests do not
connect to Mongo and do not load knowledge unless both conditions are met:

1. a `MerchantBlueprintService` is explicitly injected; and
2. the caller supplies `merchant_knowledge_key`.

Without those conditions, receipt processing is unchanged.

## Schema installation

```python
repository = MongoMerchantIntelligenceRepository.from_uri(uri, database_name)
manager = MerchantIntelligenceSchemaManager(repository.database)
manager.ensure_schema()
```

`ensure_schema()` creates missing collections, updates validators with
`collMod`, and installs indexes. It does not rewrite knowledge records.

Run schema installation as a deployment migration, not during request startup.

## Data migration strategy

```mermaid
flowchart LR
    source[/Existing merchant data/]
    normalize[Normalize stable IDs]
    validate[Validate v1 schemas]
    blueprint[Write blueprint v1]
    profiles[Write profile records]
    verify[Verify counts and history]
    activate[Enable explicit lookup]

    source --> normalize
    normalize --> validate
    validate --> blueprint
    blueprint --> profiles
    profiles --> verify
    verify --> activate
```

1. Assign stable `merchant_id`, `family_id`, `profile_id`, and vocabulary IDs.
2. Convert executable or hardcoded knowledge into data records.
3. Validate documents against the versioned schemas.
4. Insert initial records with `entity_version: 1`.
5. Preserve source provenance in learning metadata.
6. Verify aliases, families, vocabulary, and counts.
7. Enable only explicit-key loading.

## Version rules

- Updates append a new version; they do not replace history.
- `expected_version` is required for coordinated writers.
- `supersedes_version` points to the immediately prior snapshot.
- Learning observations and corrections remain append-only.
- Breaking field or meaning changes require a new `schema_version`.
- Collection migrations must be forward-readable before writers switch.

## Prohibited migration behavior

- Adding merchant-specific branches to Python code
- Running detection during repository lookup
- Feeding knowledge into current parsing, scoring, OCR, or LLM paths
- Updating blueprints in place without history
- Creating Mongo connections implicitly during API import
- Treating vocabulary storage as product classification

## Future activation

A future detection engine may produce a candidate merchant ID. Only then should
it request a blueprint. Detection confidence and blueprint knowledge remain
separate artifacts so knowledge updates cannot silently alter current receipt
results.
