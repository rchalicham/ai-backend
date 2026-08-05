from .models import SemanticCompleteness


def _present(value):
    return value is not None and value != "" and value != [] and value != {}


class SemanticCompletenessEngine:
    def evaluate(self, context, policy, configuration):
        projection = context.get("businessProjection") or {}
        fields = {}
        for item in projection.get("fields") or ():
            if isinstance(item, dict) and item.get("key"):
                fields[str(item["key"])] = item.get("displayed_value", item.get("displayedValue"))
        aliases = configuration["fieldAliases"]

        def value_for(name):
            for alias in aliases.get(name, [name]):
                if _present(fields.get(alias)):
                    return fields[alias]
            return None

        missing_required = tuple(name for name in policy.required_fields if not _present(value_for(name)))
        missing_optional = tuple(name for name in policy.optional_fields if not _present(value_for(name)))
        required_score = 1.0 if not policy.required_fields else 1.0 - len(missing_required) / len(policy.required_fields)
        optional_score = 1.0 if not policy.optional_fields else 1.0 - len(missing_optional) / len(policy.optional_fields)

        family_context = context.get("documentFamilyContext") or {}
        observed_zones = {
            str(item.get("zone_type") or item.get("zoneType") or "")
            for item in family_context.get("semantic_zones", family_context.get("semanticZones", ()))
            if isinstance(item, dict)
        }
        missing_sections = tuple(section for section in policy.expected_sections if section not in observed_zones)
        section_score = 1.0 if not policy.expected_sections else 1.0 - len(missing_sections) / len(policy.expected_sections)

        projected_items = fields.get("items")
        item_count = len(projected_items) if isinstance(projected_items, list) else 0
        item_ok = ((policy.minimum_items is None or item_count >= policy.minimum_items) and
                   (policy.maximum_items is None or item_count <= policy.maximum_items))
        grammar = context.get("receiptGrammar") or {}
        constraints = context.get("receiptConstraintResult") or {}
        grammar_score = float(grammar.get("confidence") or grammar.get("grammarConfidence") or 1.0 if grammar else 0.0)
        constraint_score = float(constraints.get("confidence") or constraints.get("overallConfidence") or 1.0 if constraints else 0.0)
        projection_score = float(((projection.get("overall_confidence") or {}).get("display")) or 0.0)
        weights = configuration["weights"]
        item_score = 1.0 if item_ok else 0.0
        score = (
            required_score * float(weights["requiredFields"]) +
            optional_score * float(weights["optionalFields"]) +
            section_score * float(weights["sections"]) +
            item_score * float(weights["items"]) +
            grammar_score * float(weights["grammar"]) +
            constraint_score * float(weights["constraints"]) +
            projection_score * float(weights["projection"])
        )
        return SemanticCompleteness(
            round(max(0.0, min(1.0, score)), 4), round(required_score, 4), round(optional_score, 4),
            round(section_score, 4), missing_required, missing_optional, missing_sections, item_ok,
            round(grammar_score, 4), round(constraint_score, 4), round(projection_score, 4),
        )
