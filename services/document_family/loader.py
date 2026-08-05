from __future__ import annotations

import json
from pathlib import Path

from .models import DocumentFamily, EntityType, FamilyProfile, SemanticZoneType


class DocumentFamilyProfileLoader:
    def from_file(self, path: str | Path) -> FamilyProfile:
        return self.from_dict(json.loads(Path(path).read_text()))

    def from_dict(self, value: dict) -> FamilyProfile:
        return FamilyProfile(
            family=DocumentFamily(value["family"]), profile_id=value["profile_id"],
            version=int(value.get("version", 1)), grammar_id=value["grammar_id"],
            constraint_set_id=value["constraint_set_id"],
            expected_zones=tuple(SemanticZoneType(item) for item in value.get("expected_zones", ())),
            required_entities=tuple(EntityType(item) for item in value.get("required_entities", ())),
            item_table_expected=bool(value.get("item_table_expected", False)),
            activation_terms=tuple(value.get("activation_terms", ())),
            key_value_labels=tuple(value.get("key_value_labels", ())),
            entity_resolution_rules=tuple(value.get("entity_resolution_rules", ())),
        )
