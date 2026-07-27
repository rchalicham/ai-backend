from __future__ import annotations

from dataclasses import replace
from typing import Any
from uuid import NAMESPACE_URL, uuid5

from .models import (
    LayoutProfile,
    MerchantAlias,
    MerchantBlueprint,
    MerchantIdentity,
    MerchantIntelligenceContext,
    ProductVocabularyEntry,
    ReceiptFamily,
)
from .repository import MerchantIntelligenceRepository, normalize_knowledge_key


class MerchantBlueprintService:
    """Data-management facade; it performs no identification or detection."""

    def __init__(self, repository: MerchantIntelligenceRepository) -> None:
        self.repository = repository

    def get_blueprint(self, merchant_id: str, version: int | None = None) -> MerchantBlueprint | None:
        return self.repository.get_blueprint(merchant_id, version)

    def create_blueprint(self, merchant_id: str, canonical_name: str, **identity_values: Any) -> MerchantBlueprint:
        blueprint = MerchantBlueprint(
            identity=MerchantIdentity(merchant_id=merchant_id, canonical_name=canonical_name, **identity_values)
        )
        return self.repository.save_blueprint(blueprint, expected_version=0)

    def save_blueprint(self, blueprint: MerchantBlueprint, expected_version: int | None = None) -> MerchantBlueprint:
        return self.repository.save_blueprint(blueprint, expected_version)

    def add_alias(self, merchant_id: str, value: str, **values: Any) -> MerchantBlueprint:
        blueprint = self._required(merchant_id)
        normalized = normalize_knowledge_key(value)
        existing = next((alias for alias in blueprint.aliases if normalize_knowledge_key(alias.value) == normalized), None)
        if existing:
            alias = replace(existing, confidence=max(existing.confidence, float(values.get("confidence", 0.0))))
            aliases = tuple(alias if current.alias_id == alias.alias_id else current for current in blueprint.aliases)
        else:
            alias = MerchantAlias(
                alias_id=str(uuid5(NAMESPACE_URL, f"{merchant_id}:alias:{normalized}")),
                merchant_id=merchant_id,
                value=value,
                **values,
            )
            aliases = (*blueprint.aliases, alias)
        return self.repository.save_blueprint(replace(blueprint, aliases=aliases), blueprint.version.entity_version)

    def add_receipt_family(
        self, merchant_id: str, family_id: str, name: str,
        confidence: float = 0.0, attributes: tuple[tuple[str, Any], ...] = (),
    ) -> MerchantBlueprint:
        blueprint = self._required(merchant_id)
        family = ReceiptFamily(family_id, merchant_id, name, confidence, attributes)
        families = tuple(current for current in blueprint.receipt_families if current.family_id != family_id) + (family,)
        return self.repository.save_blueprint(replace(blueprint, receipt_families=families), blueprint.version.entity_version)

    def update_layout_profile(self, profile: LayoutProfile) -> MerchantBlueprint:
        blueprint = self._required(profile.merchant_id)
        saved_profile = self.repository.update_layout_profile(profile)
        profiles = tuple(current for current in blueprint.layout_profiles if current.profile_id != profile.profile_id) + (saved_profile,)
        return self.repository.save_blueprint(replace(blueprint, layout_profiles=profiles), blueprint.version.entity_version)

    def update_vocabulary(self, entry: ProductVocabularyEntry) -> MerchantBlueprint:
        blueprint = self._required(entry.merchant_id)
        saved_entry = self.repository.update_vocabulary(entry)
        vocabulary = tuple(current for current in blueprint.product_vocabulary if current.vocabulary_id != entry.vocabulary_id) + (saved_entry,)
        return self.repository.save_blueprint(replace(blueprint, product_vocabulary=vocabulary), blueprint.version.entity_version)

    def load_context(self, merchant_key: str) -> MerchantIntelligenceContext:
        if not merchant_key:
            return MerchantIntelligenceContext("", None, False, (("reason", "merchant_key_not_supplied"),))
        blueprint = self.repository.get_blueprint(merchant_key)
        return MerchantIntelligenceContext(
            merchant_key=merchant_key,
            blueprint=blueprint,
            loaded=blueprint is not None,
            diagnostics=(
                ("lookupMode", "explicit_key_only"),
                ("detectionPerformed", False),
                ("affectsExtraction", False),
            ),
        )

    def _required(self, merchant_id: str) -> MerchantBlueprint:
        blueprint = self.repository.get_blueprint(merchant_id)
        if blueprint is None:
            raise KeyError(f"merchant_blueprint_not_found:{merchant_id}")
        return blueprint
