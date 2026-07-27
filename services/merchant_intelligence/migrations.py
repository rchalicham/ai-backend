from __future__ import annotations

from typing import Any

from .schemas import COLLECTIONS, MONGO_INDEXES, MONGO_SCHEMAS


class MerchantIntelligenceSchemaManager:
    """Idempotently installs validators and indexes; never rewrites knowledge."""

    def __init__(self, database: Any) -> None:
        self.database = database

    def ensure_schema(self) -> tuple[str, ...]:
        existing = set(self.database.list_collection_names())
        configured = []
        for collection_name in COLLECTIONS:
            validator = MONGO_SCHEMAS[collection_name]
            if collection_name not in existing:
                self.database.create_collection(collection_name, validator=validator)
            else:
                self.database.command("collMod", collection_name, validator=validator)
            collection = self.database[collection_name]
            for index in MONGO_INDEXES.get(collection_name, ()):
                collection.create_index(list(index))
            configured.append(collection_name)
        return tuple(configured)
