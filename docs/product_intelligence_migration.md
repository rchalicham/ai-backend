# Product Intelligence Sidecar Migration Guide

## Compatibility

Product Intelligence is additive. Existing request contracts, parser inputs,
parser execution, scoring, Llama input, and `semantic` output are unchanged.
When orchestration executes, the response may additionally contain:

```json
{
  "productIntelligence": {
    "schema_version": "product-intelligence-result-v1",
    "enrichments": [],
    "diagnostics": {
      "sidecar": true,
      "affects_extraction": false,
      "parser_authority_changed": false,
      "extracted_values_replaced": false
    },
    "learning_suggestions": []
  }
}
```

Consumers that ignore unknown response properties require no migration.

## Knowledge onboarding

1. Create immutable `CanonicalProduct` definitions using enterprise names,
   never merchant receipt descriptions as canonical identities.
2. Add aliases with their merchant scope, provenance, and confidence.
3. Assign an extensible department, category, and subcategory path.
4. Add approved brand, manufacturer, package, unit, nutrition, and pricing
   metadata where available.
5. Save the initial version through `ProductRepository.saveProducts()`.
6. Create later versions with `versionProducts()`; never edit an active version
   in place.
7. Review Product Learning suggestions outside the runtime path before
   converting any proposal into approved knowledge.

## Rollout

Deploy in observation mode, measure match and unmatched rates, inspect
explanations, and compare parser output before and after activation. Parser
parity is mandatory because Product Intelligence may enrich only a copied item
view. Missing knowledge, unmatched descriptions, or sidecar failure must leave
current extraction unchanged.

Embedding matching, forecasting, automatic knowledge updates, and authoritative
Business Fact publication require separate architecture approval.

