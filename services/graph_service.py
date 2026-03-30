from __future__ import annotations

import os
from typing import Literal

from neo4j import GraphDatabase


AllowedRelationship = Literal["HAS_DOCUMENT", "BELONGS_TO", "OWNS", "USED_IN_EVENT"]


class GraphService:
    def __init__(
        self,
        uri: str | None = None,
        user: str | None = None,
        password: str | None = None,
    ):
        self.uri = uri or os.getenv("NEO4J_URI", "bolt://neo4j:7687")
        self.user = user or os.getenv("NEO4J_USER", "neo4j")
        self.password = password or os.getenv("NEO4J_PASSWORD", "test1234")
        self.driver = GraphDatabase.driver(self.uri, auth=(self.user, self.password))

    def create_entity(self, entity_id: str, name: str | None = None) -> dict:
        query = """
        MERGE (e:Entity {id: $entity_id})
        SET e.name = coalesce($name, e.name)
        RETURN e { .id, .name } AS entity
        """
        with self.driver.session() as session:
            record = session.execute_write(
                lambda tx: tx.run(query, entity_id=entity_id, name=name).single()
            )
        return record["entity"]

    def create_document(self, document_id: str, name: str | None = None) -> dict:
        query = """
        MERGE (d:Document {id: $document_id})
        SET d.name = coalesce($name, d.name)
        RETURN d { .id, .name } AS document
        """
        with self.driver.session() as session:
            record = session.execute_write(
                lambda tx: tx.run(query, document_id=document_id, name=name).single()
            )
        return record["document"]

    def create_relationship(
        self,
        from_id: str,
        from_type: Literal["Entity", "Document"],
        to_id: str,
        to_type: Literal["Entity", "Document"],
        relationship_type: AllowedRelationship,
    ) -> dict:
        if relationship_type not in {"HAS_DOCUMENT", "BELONGS_TO", "OWNS", "USED_IN_EVENT"}:
            raise ValueError("Unsupported relationship type.")

        query = f"""
        MATCH (a:{from_type} {{id: $from_id}})
        MATCH (b:{to_type} {{id: $to_id}})
        MERGE (a)-[r:{relationship_type}]->(b)
        RETURN a.id AS from_id, labels(a)[0] AS from_type,
               type(r) AS relationship,
               b.id AS to_id, labels(b)[0] AS to_type
        """
        with self.driver.session() as session:
            record = session.execute_write(
                lambda tx: tx.run(
                    query,
                    from_id=from_id,
                    to_id=to_id,
                ).single()
            )
        if record is None:
            raise ValueError("Source or target node was not found.")
        return {
            "from_id": record["from_id"],
            "from_type": record["from_type"],
            "relationship": record["relationship"],
            "to_id": record["to_id"],
            "to_type": record["to_type"],
        }

    def get_related_data(self, entity_id: str) -> dict:
        query = """
        MATCH (e:Entity {id: $entity_id})
        OPTIONAL MATCH (e)-[r]->(n)
        RETURN e { .id, .name } AS entity,
               collect(
                   CASE
                       WHEN n IS NULL THEN NULL
                       ELSE {
                           from_id: e.id,
                           from_type: 'Entity',
                           relationship: type(r),
                           to_id: n.id,
                           to_type: labels(n)[0]
                       }
                   END
               ) AS relationships
        """
        with self.driver.session() as session:
            record = session.execute_read(
                lambda tx: tx.run(query, entity_id=entity_id).single()
            )
        if record is None:
            return {"entity": None, "relationships": []}
        relationships = [item for item in record["relationships"] if item is not None]
        return {
            "entity": record["entity"],
            "relationships": relationships,
        }
