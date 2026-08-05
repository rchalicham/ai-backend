from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class EntityDefinition:
    name: str
    description: str
    parent: str = ""
    required_properties: tuple[str, ...] = ()
    metadata: tuple[tuple[str, str], ...] = ()


@dataclass(frozen=True, slots=True)
class RelationshipDefinition:
    name: str
    description: str
    source_types: tuple[str, ...] = ()
    target_types: tuple[str, ...] = ()
    allow_self_reference: bool = False
    acyclic: bool = False
    metadata: tuple[tuple[str, str], ...] = ()


@dataclass(frozen=True, slots=True)
class OntologySchema:
    version: str
    entity_definitions: tuple[EntityDefinition, ...]
    relationship_definitions: tuple[RelationshipDefinition, ...]
    domain_extensions: tuple[str, ...] = ()

