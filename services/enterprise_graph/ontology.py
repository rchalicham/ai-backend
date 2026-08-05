from __future__ import annotations

from .models import EntityType, RelationshipType
from .schema import EntityDefinition, OntologySchema, RelationshipDefinition


class EnterpriseOntology:
    """Extensible enterprise semantic contract independent of graph storage."""

    def __init__(
        self,
        entity_definitions: tuple[EntityDefinition, ...] = (),
        relationship_definitions: tuple[RelationshipDefinition, ...] = (),
        domain_extensions: tuple[str, ...] = (),
        version: str = "enterprise-ontology-v1",
    ) -> None:
        defaults = tuple(
            EntityDefinition(item.value, f"Canonical {item.value} enterprise entity.")
            for item in EntityType
        )
        relationship_defaults = tuple(
            RelationshipDefinition(
                item.value,
                f"Enterprise relationship {item.value}.",
                allow_self_reference=item in {RelationshipType.RELATED_TO, RelationshipType.SIMILAR_TO},
                acyclic=item in {RelationshipType.HAS_PARENT, RelationshipType.HAS_CHILD, RelationshipType.PART_OF},
            )
            for item in RelationshipType
        )
        self.schema = OntologySchema(
            version,
            self._merge(defaults, entity_definitions),
            self._merge(relationship_defaults, relationship_definitions),
            tuple(domain_extensions),
        )

    @staticmethod
    def _merge(defaults, extensions):
        values = {item.name: item for item in defaults}
        values.update({item.name: item for item in extensions})
        return tuple(values[key] for key in sorted(values))

    def entity_definition(self, entity_type: EntityType | str) -> EntityDefinition | None:
        name = entity_type.value if isinstance(entity_type, EntityType) else str(entity_type)
        return next((item for item in self.schema.entity_definitions if item.name == name), None)

    def relationship_definition(
        self, relationship_type: RelationshipType | str,
    ) -> RelationshipDefinition | None:
        name = relationship_type.value if isinstance(relationship_type, RelationshipType) else str(relationship_type)
        return next((item for item in self.schema.relationship_definitions if item.name == name), None)

    def supports_entity(self, entity_type: EntityType | str) -> bool:
        return self.entity_definition(entity_type) is not None

    def supports_relationship(self, relationship_type: RelationshipType | str) -> bool:
        return self.relationship_definition(relationship_type) is not None

