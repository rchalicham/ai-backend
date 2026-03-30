from __future__ import annotations

import os
from typing import Any

from bson import ObjectId
from pymongo import MongoClient


class AttributeCatalogService:
    def __init__(self, mongo_uri: str | None = None, database_name: str | None = None):
        self.mongo_uri = mongo_uri or os.getenv("MONGO_URI", "mongodb://localhost:27017/clients")
        self.database_name = database_name or self._resolve_database_name(self.mongo_uri)
        self.client = MongoClient(self.mongo_uri, serverSelectionTimeoutMS=2000)
        database = self.client[self.database_name]
        self.global_collection = database["attribute_catalog"]
        self.domain_collection = database["domain_attribute_catalog"]

    def _resolve_database_name(self, mongo_uri: str) -> str:
        tail = mongo_uri.rsplit("/", 1)[-1]
        return (tail.split("?", 1)[0] or "clients").strip()

    def _normalize_domain_type(self, domain_type: str | None) -> str:
        return (domain_type or "").strip().lower()

    def _to_global_domain(self, domain_type: str) -> str:
        return {
            "groceries": "grocery",
            "banking": "bank",
        }.get(domain_type, domain_type)

    def _normalize_global_attribute(self, item: dict[str, Any]) -> dict[str, Any]:
        return {
            "attribute_id": str(item.get("_id", "")),
            "attribute_key": str(item.get("attribute_key", "")).strip(),
            "label": str(item.get("label") or item.get("attribute_key") or "").strip(),
            "type": str(item.get("type") or "string").strip().lower(),
            "required_default": bool(item.get("required_default", False)),
            "enum_values": item.get("enum_values") if isinstance(item.get("enum_values"), list) else [],
            "tags": item.get("tags") if isinstance(item.get("tags"), list) else [],
            "priority": int(item.get("priority", 0) or 0),
            "source": "global",
        }

    def _load_global_defaults(self, domain_type: str) -> list[dict[str, Any]]:
        mapped_domain = self._to_global_domain(domain_type)
        cursor = self.global_collection.find(
            {"domain": mapped_domain},
            {"attribute_key": 1, "label": 1, "type": 1, "required_default": 1, "enum_values": 1, "tags": 1, "priority": 1},
        ).sort("priority", -1)
        return [self._normalize_global_attribute(item) for item in cursor]

    def _resolve_ref(self, ref: dict[str, Any]) -> dict[str, Any] | None:
        attribute_id = str(ref.get("attributeId") or "").strip()
        attribute_key = str(ref.get("attributeKey") or "").strip()
        global_item: dict[str, Any] | None = None
        if attribute_id:
            try:
                global_item = self.global_collection.find_one({"_id": ObjectId(attribute_id)})
            except Exception:
                global_item = None
        if global_item is None and attribute_key:
            global_item = self.global_collection.find_one({"attribute_key": attribute_key})
        if global_item is None:
            return None

        normalized = self._normalize_global_attribute(global_item)
        if ref.get("label"):
            normalized["label"] = str(ref["label"]).strip()
        if ref.get("type"):
            normalized["type"] = str(ref["type"]).strip().lower()
        if ref.get("required") is not None:
            normalized["required_default"] = bool(ref.get("required"))
        if isinstance(ref.get("enumValues"), list) and ref.get("enumValues"):
            normalized["enum_values"] = ref["enumValues"]
        if isinstance(ref.get("validationRules"), dict):
            normalized["validation_rules"] = ref["validationRules"]
        normalized["source"] = "domain_ref"
        return normalized

    def _custom_attribute(self, item: dict[str, Any]) -> dict[str, Any] | None:
        name = str(item.get("name") or "").strip()
        if not name:
            return None
        return {
            "attribute_id": "",
            "attribute_key": name,
            "label": str(item.get("label") or name).strip(),
            "type": str(item.get("type") or "string").strip().lower(),
            "required_default": bool(item.get("required", False)),
            "enum_values": item.get("enumValues") if isinstance(item.get("enumValues"), list) else [],
            "tags": [],
            "priority": int(item.get("priority", 0) or 0),
            "validation_rules": item.get("validationRules") if isinstance(item.get("validationRules"), dict) else {},
            "source": "domain_custom",
        }

    def _compose_domain_catalog(self, document: dict[str, Any] | None) -> list[dict[str, Any]]:
        if not isinstance(document, dict):
            return []
        merged: dict[str, dict[str, Any]] = {}
        for ref in document.get("attributeRefs", []) if isinstance(document.get("attributeRefs"), list) else []:
            if not isinstance(ref, dict):
                continue
            resolved = self._resolve_ref(ref)
            if resolved and resolved["attribute_key"]:
                merged[resolved["attribute_key"]] = resolved
        for custom in document.get("customAttributes", []) if isinstance(document.get("customAttributes"), list) else []:
            if not isinstance(custom, dict):
                continue
            normalized = self._custom_attribute(custom)
            if normalized and normalized["attribute_key"]:
                merged[normalized["attribute_key"]] = normalized
        return list(merged.values())

    def get_candidate_attributes(
        self,
        template_name: str,
        guidance: str | None = None,
        domain_id: str | None = None,
        domain_type: str | None = None,
        limit: int = 100,
    ) -> list[dict[str, Any]]:
        normalized_domain_type = self._normalize_domain_type(domain_type)
        merged: dict[str, dict[str, Any]] = {}

        if normalized_domain_type:
            for item in self._load_global_defaults(normalized_domain_type):
                merged.setdefault(item["attribute_key"], item)

            default_doc = self.domain_collection.find_one(
                {"scope": "domain_type_default", "domainType": normalized_domain_type},
                {"attributeRefs": 1, "customAttributes": 1, "description": 1},
            )
            for item in self._compose_domain_catalog(default_doc):
                merged[item["attribute_key"]] = item

        if domain_id:
            domain_doc = self.domain_collection.find_one(
                {"domainId": domain_id},
                {"attributeRefs": 1, "customAttributes": 1, "description": 1},
            )
            for item in self._compose_domain_catalog(domain_doc):
                merged[item["attribute_key"]] = item

        ordered = sorted(merged.values(), key=lambda item: item.get("priority", 0), reverse=True)
        return ordered[:limit]
