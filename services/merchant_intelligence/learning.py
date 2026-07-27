from __future__ import annotations

from dataclasses import replace
from uuid import NAMESPACE_URL, uuid5

from .models import (
    CorrectionEvent,
    LayoutProfile,
    LearningMetadata,
    MerchantBlueprint,
    MerchantStatistics,
    OcrCorrection,
    ProductVocabularyEntry,
    ReceiptFamily,
    ReceiptObservation,
)
from .repository import MerchantIntelligenceRepository, normalize_knowledge_key


class MerchantLearningService:
    """Incremental, append-first knowledge updates with no model retraining."""

    def __init__(self, repository: MerchantIntelligenceRepository) -> None:
        self.repository = repository

    def record_receipt(self, observation: ReceiptObservation) -> MerchantBlueprint:
        self.repository.record_receipt(observation)
        blueprint = self._required(observation.merchant_id)
        statistics = self.update_merchant_statistics(blueprint.statistics, observation)
        saved_statistics = self.repository.update_statistics(statistics)
        vocabulary = self.update_vocabulary(blueprint.product_vocabulary, observation)
        original_vocabulary = {entry.vocabulary_id: entry for entry in blueprint.product_vocabulary}
        vocabulary = tuple(
            self.repository.update_vocabulary(entry)
            if original_vocabulary.get(entry.vocabulary_id) != entry else entry
            for entry in vocabulary
        )
        profiles = self.update_profiles(blueprint.layout_profiles, observation)
        original_profiles = {profile.profile_id: profile for profile in blueprint.layout_profiles}
        profiles = tuple(
            self.repository.update_layout_profile(profile)
            if original_profiles.get(profile.profile_id) != profile else profile
            for profile in profiles
        )
        families = self._families(blueprint.receipt_families, observation)
        learning = replace(
            blueprint.learning,
            observation_count=blueprint.learning.observation_count + 1,
            last_observed_at=observation.observed_at,
            learning_version=blueprint.learning.learning_version + 1,
            provenance=tuple(dict.fromkeys((*blueprint.learning.provenance, observation.event_id))),
        )
        updated = replace(
            blueprint,
            statistics=saved_statistics,
            product_vocabulary=vocabulary,
            layout_profiles=profiles,
            receipt_families=families,
            learning=learning,
        )
        return self.repository.save_blueprint(updated, blueprint.version.entity_version)

    def record_correction(self, correction: CorrectionEvent) -> MerchantBlueprint:
        self.repository.record_correction(correction)
        blueprint = self._required(correction.merchant_id)
        corrections = self._ocr_corrections(blueprint.ocr_corrections, correction)
        vocabulary = blueprint.product_vocabulary
        if correction.correction_type in {"vocabulary", "product_vocabulary", "ocr_vocabulary"}:
            vocabulary = self._correct_vocabulary(vocabulary, correction)
            vocabulary = tuple(
                self.repository.update_vocabulary(entry) if entry.canonical_value == correction.after else entry
                for entry in vocabulary
            )
        learning = replace(
            blueprint.learning,
            correction_count=blueprint.learning.correction_count + 1,
            last_corrected_at=correction.corrected_at,
            learning_version=blueprint.learning.learning_version + 1,
            provenance=tuple(dict.fromkeys((*blueprint.learning.provenance, correction.event_id))),
        )
        updated = replace(blueprint, ocr_corrections=corrections, product_vocabulary=vocabulary, learning=learning)
        return self.repository.save_blueprint(updated, blueprint.version.entity_version)

    def update_merchant_statistics(
        self, current: MerchantStatistics | None, observation: ReceiptObservation,
    ) -> MerchantStatistics:
        current = current or MerchantStatistics(observation.merchant_id)
        measurements = dict(observation.measurements)
        count = current.receipt_count + 1

        def mean(old: float, key: str) -> float:
            value = float(measurements.get(key, old))
            return round(old + (value - old) / count, 4)

        return replace(
            current,
            receipt_count=count,
            average_width=mean(current.average_width, "width"),
            average_height=mean(current.average_height, "height"),
            typical_header_height=mean(current.typical_header_height, "header_height"),
            typical_footer_height=mean(current.typical_footer_height, "footer_height"),
            typical_item_count=mean(current.typical_item_count, "item_count"),
            typical_line_spacing=mean(current.typical_line_spacing, "line_spacing"),
            typical_column_count=mean(current.typical_column_count, "column_count"),
            receipt_density=mean(current.receipt_density, "density"),
            average_confidence=round(current.average_confidence + (observation.confidence - current.average_confidence) / count, 4),
            receipt_frequency=float(count),
        )

    def update_vocabulary(
        self, current: tuple[ProductVocabularyEntry, ...], observation: ReceiptObservation,
    ) -> tuple[ProductVocabularyEntry, ...]:
        values = list(current)
        by_key = {normalize_knowledge_key(entry.canonical_value): index for index, entry in enumerate(values)}
        for raw in observation.vocabulary:
            key = normalize_knowledge_key(raw)
            if not key:
                continue
            if key in by_key:
                index = by_key[key]
                values[index] = replace(values[index], observations=values[index].observations + 1)
            else:
                entry = ProductVocabularyEntry(
                    vocabulary_id=str(uuid5(NAMESPACE_URL, f"{observation.merchant_id}:vocabulary:{key}")),
                    merchant_id=observation.merchant_id,
                    canonical_value=raw,
                    observations=1,
                )
                by_key[key] = len(values)
                values.append(entry)
        return tuple(values)

    def update_profiles(
        self, current: tuple[LayoutProfile, ...], observation: ReceiptObservation,
    ) -> tuple[LayoutProfile, ...]:
        measurements = dict(observation.measurements)
        if not any(key in measurements for key in ("header_height_ratio", "table_width_ratio", "footer_height_ratio")):
            return current
        profile_id = str(uuid5(NAMESPACE_URL, f"{observation.merchant_id}:layout:{observation.family_id or 'default'}"))
        existing = next((profile for profile in current if profile.profile_id == profile_id), None)
        count = (existing.sample_count if existing else 0) + 1

        def mean(old: float | None, key: str) -> float | None:
            if key not in measurements:
                return old
            baseline = float(old or 0.0)
            return round(baseline + (float(measurements[key]) - baseline) / count, 4)

        profile = LayoutProfile(
            profile_id=profile_id,
            merchant_id=observation.merchant_id,
            family_id=observation.family_id,
            header_height_ratio=mean(existing.header_height_ratio if existing else None, "header_height_ratio"),
            table_width_ratio=mean(existing.table_width_ratio if existing else None, "table_width_ratio"),
            footer_height_ratio=mean(existing.footer_height_ratio if existing else None, "footer_height_ratio"),
            column_positions=existing.column_positions if existing else (),
            whitespace_ratios=existing.whitespace_ratios if existing else (),
            reading_pattern=existing.reading_pattern if existing else (),
            sample_count=count,
            confidence=observation.confidence,
            version=existing.version if existing else LayoutProfile(profile_id, observation.merchant_id).version,
        )
        return tuple(value for value in current if value.profile_id != profile_id) + (profile,)

    @staticmethod
    def _families(current: tuple[ReceiptFamily, ...], observation: ReceiptObservation) -> tuple[ReceiptFamily, ...]:
        if not observation.family_id or any(family.family_id == observation.family_id for family in current):
            return current
        return (*current, ReceiptFamily(
            family_id=observation.family_id,
            merchant_id=observation.merchant_id,
            name=observation.family_id,
            confidence=observation.confidence,
            history=(("firstObservation", observation.event_id),),
        ))

    @staticmethod
    def _ocr_corrections(current: tuple[OcrCorrection, ...], event: CorrectionEvent) -> tuple[OcrCorrection, ...]:
        existing = next((item for item in current if item.observed == event.before and item.corrected == event.after), None)
        if existing:
            updated = replace(existing, occurrences=existing.occurrences + 1, confidence=max(existing.confidence, event.confidence))
            return tuple(updated if item == existing else item for item in current)
        return (*current, OcrCorrection(event.before, event.after, 1, event.confidence, event.source))

    @staticmethod
    def _correct_vocabulary(
        current: tuple[ProductVocabularyEntry, ...], event: CorrectionEvent,
    ) -> tuple[ProductVocabularyEntry, ...]:
        key = normalize_knowledge_key(event.after)
        existing = next((entry for entry in current if normalize_knowledge_key(entry.canonical_value) == key), None)
        if existing:
            updated = replace(
                existing,
                common_ocr_errors=tuple(dict.fromkeys((*existing.common_ocr_errors, event.before))),
                observations=existing.observations + 1,
            )
            return tuple(updated if entry == existing else entry for entry in current)
        return (*current, ProductVocabularyEntry(
            vocabulary_id=str(uuid5(NAMESPACE_URL, f"{event.merchant_id}:vocabulary:{key}")),
            merchant_id=event.merchant_id,
            canonical_value=event.after,
            common_ocr_errors=(event.before,),
            observations=1,
        ))

    def _required(self, merchant_id: str) -> MerchantBlueprint:
        blueprint = self.repository.get_blueprint(merchant_id)
        if blueprint is None:
            raise KeyError(f"merchant_blueprint_not_found:{merchant_id}")
        return blueprint
