import json
import os
import sys
from dataclasses import FrozenInstanceError

import pytest

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)

from services.merchant_intelligence import (
    COLLECTIONS,
    MONGO_INDEXES,
    MONGO_SCHEMAS,
    CorrectionEvent,
    InMemoryMerchantIntelligenceRepository,
    LayoutProfile,
    MerchantBlueprintService,
    MerchantIntelligenceSchemaManager,
    MerchantIntelligenceSerializer,
    MerchantLearningService,
    ProductVocabularyEntry,
    ReceiptObservation,
)


@pytest.fixture()
def repository():
    return InMemoryMerchantIntelligenceRepository()


@pytest.fixture()
def blueprints(repository):
    return MerchantBlueprintService(repository)


@pytest.fixture()
def blueprint(blueprints):
    return blueprints.create_blueprint(
        "merchant-1",
        "Example Merchant",
        country_codes=("US",),
        domains=("example.test",),
    )


def test_blueprint_repository_creates_versions_and_preserves_history(repository, blueprints, blueprint):
    updated = blueprints.add_alias("merchant-1", "Example", source="manual", confidence=0.9)
    history = repository.blueprint_history("merchant-1")

    assert blueprint.version.entity_version == 1
    assert updated.version.entity_version == 2
    assert updated.version.supersedes_version == 1
    assert len(history) == 2
    assert history[0].aliases == ()
    assert history[1].aliases[0].value == "Example"
    with pytest.raises(FrozenInstanceError):
        updated.identity.canonical_name = "changed"  # type: ignore[misc]


def test_blueprint_repository_enforces_optimistic_versioning(repository, blueprints, blueprint):
    with pytest.raises(ValueError, match="version_conflict"):
        repository.save_blueprint(blueprint, expected_version=99)


def test_receipt_families_support_multiple_evolving_families(repository, blueprints, blueprint):
    blueprints.add_receipt_family("merchant-1", "family-store", "Store", 0.8)
    updated = blueprints.add_receipt_family("merchant-1", "family-fuel", "Fuel", 0.75)

    families = repository.find_receipt_families("merchant-1")

    assert {family.family_id for family in families} == {"family-store", "family-fuel"}
    assert updated.version.entity_version == 3
    assert all(family.version.schema_version == "receipt-family-v1" for family in families)


def test_alias_queries_are_normalized_and_data_driven(repository, blueprints, blueprint):
    blueprints.add_alias("merchant-1", "Example Market", locale="en-US", confidence=0.95)

    assert repository.find_aliases(" example-market ")[0].merchant_id == "merchant-1"
    assert repository.find_aliases(merchant_id="merchant-1")[0].value == "Example Market"
    assert repository.find_aliases("unknown") == ()


def test_layout_and_vocabulary_updates_create_independent_version_history(repository, blueprints, blueprint):
    profile = LayoutProfile("layout-1", "merchant-1", header_height_ratio=0.15, sample_count=1)
    entry = ProductVocabularyEntry("vocab-1", "merchant-1", "ALPHA", aliases=("A",))

    with_profile = blueprints.update_layout_profile(profile)
    with_vocabulary = blueprints.update_vocabulary(entry)

    assert with_profile.layout_profiles[0].version.entity_version == 1
    assert with_vocabulary.product_vocabulary[0].canonical_value == "ALPHA"
    assert len(repository.layout_profiles["layout-1"]) == 1
    assert len(repository.vocabulary["vocab-1"]) == 1


def test_learning_updates_running_statistics_without_retraining(repository, blueprints, blueprint):
    learning = MerchantLearningService(repository)
    first = ReceiptObservation.create(
        "merchant-1", "receipt-1",
        measurements=(("width", 400), ("height", 800), ("header_height", 100), ("line_spacing", 12)),
        confidence=0.8,
    )
    second = ReceiptObservation.create(
        "merchant-1", "receipt-2",
        measurements=(("width", 600), ("height", 1000), ("header_height", 140), ("line_spacing", 16)),
        confidence=1.0,
    )

    learning.record_receipt(first)
    updated = learning.record_receipt(second)

    assert updated.statistics.receipt_count == 2
    assert updated.statistics.average_width == 500
    assert updated.statistics.average_height == 900
    assert updated.statistics.typical_header_height == 120
    assert updated.statistics.typical_line_spacing == 14
    assert updated.statistics.average_confidence == 0.9
    assert updated.learning.observation_count == 2
    assert len(repository.receipts) == 2
    assert len(repository.statistics["merchant-1"]) == 2


def test_learning_incrementally_updates_vocabulary_profiles_and_family(repository, blueprints, blueprint):
    learning = MerchantLearningService(repository)
    observation = ReceiptObservation.create(
        "merchant-1", "receipt-1",
        family_id="family-a",
        measurements=(
            ("header_height_ratio", 0.12),
            ("table_width_ratio", 0.8),
            ("footer_height_ratio", 0.1),
        ),
        vocabulary=("ALPHA", "BETA"),
        confidence=0.86,
    )

    updated = learning.record_receipt(observation)

    assert {entry.canonical_value for entry in updated.product_vocabulary} == {"ALPHA", "BETA"}
    assert all(entry.observations == 1 for entry in updated.product_vocabulary)
    assert updated.layout_profiles[0].header_height_ratio == 0.12
    assert updated.layout_profiles[0].sample_count == 1
    assert updated.receipt_families[0].family_id == "family-a"


def test_corrections_are_append_only_and_accumulate_ocr_vocabulary(repository, blueprints, blueprint):
    learning = MerchantLearningService(repository)
    first = CorrectionEvent.create(
        "merchant-1", "receipt-1", "ocr_vocabulary", "ALPMA", "ALPHA", source="human"
    )
    second = CorrectionEvent.create(
        "merchant-1", "receipt-2", "ocr_vocabulary", "ALPMA", "ALPHA", source="human"
    )

    learning.record_correction(first)
    updated = learning.record_correction(second)

    assert len(repository.corrections) == 2
    assert updated.ocr_corrections[0].occurrences == 2
    assert updated.product_vocabulary[0].canonical_value == "ALPHA"
    assert updated.product_vocabulary[0].common_ocr_errors == ("ALPMA",)
    assert updated.learning.correction_count == 2


def test_serializer_round_trips_complete_blueprint(blueprints, blueprint):
    updated = blueprints.add_alias("merchant-1", "Example", confidence=0.9)
    serializer = MerchantIntelligenceSerializer()
    payload = serializer.to_dict(updated)
    restored = serializer.blueprint_from_dict(payload)

    assert json.loads(serializer.to_json(updated))["identity"]["merchant_id"] == "merchant-1"
    assert restored == updated
    assert restored.aliases[0].confidence == 0.9
    assert restored.identity.external_references == ()


def test_explicit_context_lookup_performs_no_detection(repository, blueprints, blueprint):
    loaded = blueprints.load_context("merchant-1")
    missing = blueprints.load_context("")

    assert loaded.loaded is True
    assert loaded.blueprint == blueprint
    assert dict(loaded.diagnostics)["detectionPerformed"] is False
    assert missing.loaded is False
    assert dict(missing.diagnostics)["reason"] == "merchant_key_not_supplied"


def test_all_versioned_mongo_schemas_and_indexes_are_declared():
    assert set(COLLECTIONS) == set(MONGO_SCHEMAS)
    assert set(COLLECTIONS) == set(MONGO_INDEXES)
    for collection in COLLECTIONS:
        schema = MONGO_SCHEMAS[collection]["$jsonSchema"]
        assert "schema_version" in schema["required"]
        assert "merchant_id" in schema["required"]
        assert MONGO_INDEXES[collection]


class _FakeCollection:
    def __init__(self):
        self.indexes = []

    def create_index(self, index):
        self.indexes.append(index)


class _FakeDatabase:
    def __init__(self, existing=()):
        self.collections = {name: _FakeCollection() for name in existing}
        self.created = []
        self.modified = []

    def list_collection_names(self):
        return list(self.collections)

    def create_collection(self, name, validator):
        self.created.append((name, validator))
        self.collections[name] = _FakeCollection()

    def command(self, operation, name, validator):
        self.modified.append((operation, name, validator))

    def __getitem__(self, name):
        return self.collections[name]


def test_schema_manager_is_idempotent_and_installs_indexes():
    database = _FakeDatabase(existing=("merchant_blueprints",))

    configured = MerchantIntelligenceSchemaManager(database).ensure_schema()

    assert configured == COLLECTIONS
    assert database.modified[0][0:2] == ("collMod", "merchant_blueprints")
    assert len(database.created) == len(COLLECTIONS) - 1
    assert all(database.collections[name].indexes for name in COLLECTIONS)
