from .models import FamilyReviewPolicy, frozen_map


def build_policy(family, data):
    items = data.get("expectedItems") or {}
    return FamilyReviewPolicy(
        family=family,
        required_fields=tuple(data.get("requiredFields") or ()),
        optional_fields=tuple(data.get("optionalFields") or ()),
        expected_sections=tuple(data.get("expectedSections") or ()),
        minimum_items=items.get("minimum"),
        maximum_items=items.get("maximum"),
        minimum_completeness=float(data["minimumCompleteness"]),
        minimum_confidence=float(data["minimumConfidence"]),
        configuration=frozen_map(data),
    )
