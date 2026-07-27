from __future__ import annotations

COLLECTIONS = (
    "merchant_blueprints",
    "receipt_families",
    "merchant_aliases",
    "merchant_layout_profiles",
    "merchant_statistics",
    "merchant_learning",
    "merchant_receipt_patterns",
    "merchant_visual_profiles",
    "merchant_product_catalog",
    "merchant_tax_profiles",
    "merchant_coupon_profiles",
    "merchant_payment_profiles",
)


def _validator(required: list[str], properties: dict) -> dict:
    return {
        "$jsonSchema": {
            "bsonType": "object",
            "required": ["schema_version", "merchant_id", *required],
            "properties": {
                "schema_version": {"bsonType": "string"},
                "merchant_id": {"bsonType": "string"},
                "entity_version": {"bsonType": ["int", "long"]},
                "created_at": {"bsonType": "string"},
                "updated_at": {"bsonType": "string"},
                **properties,
            },
        }
    }


MONGO_SCHEMAS = {
    "merchant_blueprints": _validator(
        ["identity", "version"],
        {"identity": {"bsonType": "object"}, "version": {"bsonType": "object"}},
    ),
    "receipt_families": _validator(
        ["family_id", "name"],
        {"family_id": {"bsonType": "string"}, "name": {"bsonType": "string"}, "confidence": {"bsonType": ["double", "int"]}},
    ),
    "merchant_aliases": _validator(
        ["alias_id", "value"],
        {"alias_id": {"bsonType": "string"}, "value": {"bsonType": "string"}, "normalized_value": {"bsonType": "string"}},
    ),
    "merchant_layout_profiles": _validator(["profile_id"], {"profile_id": {"bsonType": "string"}, "family_id": {"bsonType": "string"}}),
    "merchant_statistics": _validator([], {"receipt_count": {"bsonType": ["int", "long"]}}),
    "merchant_learning": _validator(["event_id", "event_type"], {"event_id": {"bsonType": "string"}, "event_type": {"bsonType": "string"}}),
    "merchant_receipt_patterns": _validator(["pattern_id"], {"pattern_id": {"bsonType": "string"}, "attributes": {"bsonType": "object"}}),
    "merchant_visual_profiles": _validator(["profile_id"], {"profile_id": {"bsonType": "string"}}),
    "merchant_product_catalog": _validator(["vocabulary_id", "canonical_value"], {"vocabulary_id": {"bsonType": "string"}, "canonical_value": {"bsonType": "string"}}),
    "merchant_tax_profiles": _validator(["profile_id"], {"profile_id": {"bsonType": "string"}}),
    "merchant_coupon_profiles": _validator(["profile_id"], {"profile_id": {"bsonType": "string"}}),
    "merchant_payment_profiles": _validator(["profile_id"], {"profile_id": {"bsonType": "string"}}),
}

MONGO_INDEXES = {
    "merchant_blueprints": [(("merchant_id", 1), ("entity_version", -1))],
    "receipt_families": [(("merchant_id", 1), ("family_id", 1), ("entity_version", -1))],
    "merchant_aliases": [(("normalized_value", 1),), (("merchant_id", 1), ("entity_version", -1))],
    "merchant_layout_profiles": [(("merchant_id", 1), ("family_id", 1), ("entity_version", -1))],
    "merchant_statistics": [(("merchant_id", 1), ("entity_version", -1))],
    "merchant_learning": [(("merchant_id", 1), ("created_at", -1)), (("event_id", 1),)],
    "merchant_receipt_patterns": [(("merchant_id", 1), ("pattern_id", 1))],
    "merchant_visual_profiles": [(("merchant_id", 1), ("family_id", 1))],
    "merchant_product_catalog": [(("merchant_id", 1), ("canonical_value", 1))],
    "merchant_tax_profiles": [(("merchant_id", 1), ("family_id", 1))],
    "merchant_coupon_profiles": [(("merchant_id", 1), ("family_id", 1))],
    "merchant_payment_profiles": [(("merchant_id", 1), ("family_id", 1))],
}
