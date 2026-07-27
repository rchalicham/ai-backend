from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import replace
from typing import Any

from .models import (
    CorrectionEvent,
    LayoutProfile,
    MerchantAlias,
    MerchantBlueprint,
    MerchantStatistics,
    ProductVocabularyEntry,
    ReceiptFamily,
    ReceiptObservation,
    VersionMetadata,
    utc_now,
)
from .serialization import MerchantIntelligenceSerializer


class MerchantIntelligenceRepository(ABC):
    @abstractmethod
    def get_blueprint(self, merchant_id: str, version: int | None = None) -> MerchantBlueprint | None:
        raise NotImplementedError

    @abstractmethod
    def save_blueprint(self, blueprint: MerchantBlueprint, expected_version: int | None = None) -> MerchantBlueprint:
        raise NotImplementedError

    @abstractmethod
    def blueprint_history(self, merchant_id: str) -> tuple[MerchantBlueprint, ...]:
        raise NotImplementedError

    @abstractmethod
    def update_statistics(self, statistics: MerchantStatistics) -> MerchantStatistics:
        raise NotImplementedError

    @abstractmethod
    def record_receipt(self, observation: ReceiptObservation) -> ReceiptObservation:
        raise NotImplementedError

    @abstractmethod
    def record_correction(self, correction: CorrectionEvent) -> CorrectionEvent:
        raise NotImplementedError

    @abstractmethod
    def find_receipt_families(self, merchant_id: str) -> tuple[ReceiptFamily, ...]:
        raise NotImplementedError

    @abstractmethod
    def find_aliases(self, value: str = "", merchant_id: str = "") -> tuple[MerchantAlias, ...]:
        raise NotImplementedError

    @abstractmethod
    def update_layout_profile(self, profile: LayoutProfile) -> LayoutProfile:
        raise NotImplementedError

    @abstractmethod
    def update_vocabulary(self, entry: ProductVocabularyEntry) -> ProductVocabularyEntry:
        raise NotImplementedError


class InMemoryMerchantIntelligenceRepository(MerchantIntelligenceRepository):
    def __init__(self) -> None:
        self._blueprints: dict[str, list[MerchantBlueprint]] = {}
        self.statistics: dict[str, list[MerchantStatistics]] = {}
        self.receipts: list[ReceiptObservation] = []
        self.corrections: list[CorrectionEvent] = []
        self.layout_profiles: dict[str, list[LayoutProfile]] = {}
        self.vocabulary: dict[str, list[ProductVocabularyEntry]] = {}

    def get_blueprint(self, merchant_id: str, version: int | None = None) -> MerchantBlueprint | None:
        history = self._blueprints.get(merchant_id, [])
        if version is None:
            return history[-1] if history else None
        return next((item for item in history if item.version.entity_version == version), None)

    def save_blueprint(self, blueprint: MerchantBlueprint, expected_version: int | None = None) -> MerchantBlueprint:
        history = self._blueprints.setdefault(blueprint.merchant_id, [])
        current = history[-1] if history else None
        current_version = current.version.entity_version if current else 0
        if expected_version is not None and current_version != expected_version:
            raise ValueError("merchant_blueprint_version_conflict")
        now = utc_now()
        saved = replace(
            blueprint,
            version=replace(
                blueprint.version,
                entity_version=current_version + 1,
                created_at=blueprint.version.created_at if not current else current.version.created_at,
                updated_at=now,
                supersedes_version=current_version or None,
            ),
        )
        history.append(saved)
        return saved

    def blueprint_history(self, merchant_id: str) -> tuple[MerchantBlueprint, ...]:
        return tuple(self._blueprints.get(merchant_id, ()))

    def update_statistics(self, statistics: MerchantStatistics) -> MerchantStatistics:
        history = self.statistics.setdefault(statistics.merchant_id, [])
        current_version = history[-1].version.entity_version if history else 0
        saved = replace(statistics, version=replace(
            statistics.version,
            entity_version=current_version + 1,
            supersedes_version=current_version or None,
            updated_at=utc_now(),
        ))
        history.append(saved)
        return saved

    def record_receipt(self, observation: ReceiptObservation) -> ReceiptObservation:
        self.receipts.append(observation)
        return observation

    def record_correction(self, correction: CorrectionEvent) -> CorrectionEvent:
        self.corrections.append(correction)
        return correction

    def find_receipt_families(self, merchant_id: str) -> tuple[ReceiptFamily, ...]:
        blueprint = self.get_blueprint(merchant_id)
        return blueprint.receipt_families if blueprint else ()

    def find_aliases(self, value: str = "", merchant_id: str = "") -> tuple[MerchantAlias, ...]:
        aliases = tuple(alias for history in self._blueprints.values() for alias in (history[-1].aliases if history else ()))
        if merchant_id:
            aliases = tuple(alias for alias in aliases if alias.merchant_id == merchant_id)
        if value:
            normalized = normalize_knowledge_key(value)
            aliases = tuple(alias for alias in aliases if normalize_knowledge_key(alias.value) == normalized)
        return aliases

    def update_layout_profile(self, profile: LayoutProfile) -> LayoutProfile:
        history = self.layout_profiles.setdefault(profile.profile_id, [])
        current_version = history[-1].version.entity_version if history else 0
        saved = replace(profile, version=replace(
            profile.version, entity_version=current_version + 1,
            supersedes_version=current_version or None, updated_at=utc_now(),
        ))
        history.append(saved)
        return saved

    def update_vocabulary(self, entry: ProductVocabularyEntry) -> ProductVocabularyEntry:
        history = self.vocabulary.setdefault(entry.vocabulary_id, [])
        current_version = history[-1].version.entity_version if history else 0
        saved = replace(entry, version=replace(
            entry.version, entity_version=current_version + 1,
            supersedes_version=current_version or None, updated_at=utc_now(),
        ))
        history.append(saved)
        return saved


class MongoMerchantIntelligenceRepository(MerchantIntelligenceRepository):
    """Append-only Mongo adapter. Connection lifecycle belongs to the caller."""

    def __init__(self, database: Any) -> None:
        self.database = database
        self.serializer = MerchantIntelligenceSerializer()

    @classmethod
    def from_uri(cls, uri: str, database_name: str = "merchant_intelligence") -> "MongoMerchantIntelligenceRepository":
        from pymongo import MongoClient

        client = MongoClient(uri, serverSelectionTimeoutMS=2000)
        return cls(client[database_name])

    def get_blueprint(self, merchant_id: str, version: int | None = None) -> MerchantBlueprint | None:
        query: dict[str, Any] = {"merchant_id": merchant_id}
        if version is not None:
            query["entity_version"] = version
        document = self.database["merchant_blueprints"].find_one(query, sort=[("entity_version", -1)])
        return self.serializer.blueprint_from_dict(self._payload(document)) if document else None

    def save_blueprint(self, blueprint: MerchantBlueprint, expected_version: int | None = None) -> MerchantBlueprint:
        current = self.get_blueprint(blueprint.merchant_id)
        current_version = current.version.entity_version if current else 0
        if expected_version is not None and expected_version != current_version:
            raise ValueError("merchant_blueprint_version_conflict")
        saved = replace(blueprint, version=replace(
            blueprint.version,
            entity_version=current_version + 1,
            supersedes_version=current_version or None,
            updated_at=utc_now(),
        ))
        self.database["merchant_blueprints"].insert_one(self._document(saved, saved.merchant_id, saved.version))
        self._persist_blueprint_components(saved)
        return saved

    def blueprint_history(self, merchant_id: str) -> tuple[MerchantBlueprint, ...]:
        documents = self.database["merchant_blueprints"].find({"merchant_id": merchant_id}).sort("entity_version", 1)
        return tuple(self.serializer.blueprint_from_dict(self._payload(document)) for document in documents)

    def update_statistics(self, statistics: MerchantStatistics) -> MerchantStatistics:
        current = self.database["merchant_statistics"].find_one({"merchant_id": statistics.merchant_id}, sort=[("entity_version", -1)])
        current_version = int((current or {}).get("entity_version", 0))
        saved = replace(statistics, version=replace(
            statistics.version, entity_version=current_version + 1,
            supersedes_version=current_version or None, updated_at=utc_now(),
        ))
        self.database["merchant_statistics"].insert_one(self._document(saved, saved.merchant_id, saved.version))
        return saved

    def record_receipt(self, observation: ReceiptObservation) -> ReceiptObservation:
        document = self.serializer.to_dict(observation)
        document.update({"merchant_id": observation.merchant_id, "event_type": "receipt_observation", "created_at": observation.observed_at})
        self.database["merchant_learning"].insert_one(document)
        return observation

    def record_correction(self, correction: CorrectionEvent) -> CorrectionEvent:
        document = self.serializer.to_dict(correction)
        document.update({"merchant_id": correction.merchant_id, "event_type": "correction", "created_at": correction.corrected_at})
        self.database["merchant_learning"].insert_one(document)
        return correction

    def find_receipt_families(self, merchant_id: str) -> tuple[ReceiptFamily, ...]:
        blueprint = self.get_blueprint(merchant_id)
        return blueprint.receipt_families if blueprint else ()

    def find_aliases(self, value: str = "", merchant_id: str = "") -> tuple[MerchantAlias, ...]:
        query: dict[str, Any] = {}
        if value:
            query["normalized_value"] = normalize_knowledge_key(value)
        if merchant_id:
            query["merchant_id"] = merchant_id
        documents = self.database["merchant_aliases"].find(query)
        return tuple(self.serializer._construct(MerchantAlias, self._payload(document)) for document in documents)

    def update_layout_profile(self, profile: LayoutProfile) -> LayoutProfile:
        return self._append_versioned("merchant_layout_profiles", profile, profile.merchant_id)

    def update_vocabulary(self, entry: ProductVocabularyEntry) -> ProductVocabularyEntry:
        return self._append_versioned("merchant_product_catalog", entry, entry.merchant_id)

    def _append_versioned(self, collection: str, value: Any, merchant_id: str) -> Any:
        identifier_name = "profile_id" if hasattr(value, "profile_id") else "vocabulary_id"
        identifier = getattr(value, identifier_name)
        current = self.database[collection].find_one({identifier_name: identifier}, sort=[("entity_version", -1)])
        current_version = int((current or {}).get("entity_version", 0))
        saved = replace(value, version=replace(
            value.version, entity_version=current_version + 1,
            supersedes_version=current_version or None, updated_at=utc_now(),
        ))
        document = self._document(saved, merchant_id, saved.version)
        document[identifier_name] = identifier
        self.database[collection].insert_one(document)
        return saved

    def _document(self, value: Any, merchant_id: str, version: VersionMetadata) -> dict[str, Any]:
        document = self.serializer.to_dict(value)
        document.update({
            "merchant_id": merchant_id,
            "schema_version": version.schema_version,
            "entity_version": version.entity_version,
            "created_at": version.created_at,
            "updated_at": version.updated_at,
        })
        return document

    def _persist_blueprint_components(self, blueprint: MerchantBlueprint) -> None:
        for alias in blueprint.aliases:
            document = self._document(alias, blueprint.merchant_id, alias.version)
            document["normalized_value"] = normalize_knowledge_key(alias.value)
            self.database["merchant_aliases"].insert_one(document)
        for family in blueprint.receipt_families:
            self.database["receipt_families"].insert_one(self._document(family, blueprint.merchant_id, family.version))
        for profile in blueprint.visual_profiles:
            self.database["merchant_visual_profiles"].insert_one(self._document(profile, blueprint.merchant_id, profile.version))
        for profile in blueprint.receipt_patterns:
            self.database["merchant_receipt_patterns"].insert_one(self._document(profile, blueprint.merchant_id, profile.version))
        for collection, profiles in (
            ("merchant_tax_profiles", blueprint.tax_profiles),
            ("merchant_coupon_profiles", blueprint.coupon_profiles),
            ("merchant_payment_profiles", blueprint.payment_profiles),
        ):
            for profile in profiles:
                self.database[collection].insert_one(self._document(profile, blueprint.merchant_id, profile.version))

    @staticmethod
    def _payload(document: dict[str, Any] | None) -> dict[str, Any]:
        if not document:
            return {}
        return {key: value for key, value in document.items() if key not in {"_id", "schema_version", "entity_version", "created_at", "updated_at", "merchant_id"} or key == "merchant_id"}


def normalize_knowledge_key(value: str) -> str:
    return "".join(character.lower() for character in str(value).strip() if character.isalnum())
