from __future__ import annotations

from .models import KeyValueRelationship


class KeyValueRelationshipValidator:
    def validate(self, relationships: tuple[KeyValueRelationship, ...]) -> tuple[KeyValueRelationship, ...]:
        return tuple(item for item in relationships if item.key and item.value and item.key.lower() != item.value.lower() and item.confidence >= 0.5)
