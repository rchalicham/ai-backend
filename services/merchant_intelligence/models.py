from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any
from uuid import uuid4


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


@dataclass(frozen=True, slots=True)
class VersionMetadata:
    schema_version: str
    entity_version: int = 1
    created_at: str = field(default_factory=utc_now)
    updated_at: str = field(default_factory=utc_now)
    supersedes_version: int | None = None
    status: str = "active"


@dataclass(frozen=True, slots=True)
class MerchantIdentity:
    merchant_id: str
    canonical_name: str
    country_codes: tuple[str, ...] = ()
    domains: tuple[str, ...] = ()
    external_references: tuple[tuple[str, str], ...] = ()


@dataclass(frozen=True, slots=True)
class MerchantAlias:
    alias_id: str
    merchant_id: str
    value: str
    locale: str = ""
    source: str = ""
    confidence: float = 0.0
    version: VersionMetadata = field(default_factory=lambda: VersionMetadata("merchant-alias-v1"))


@dataclass(frozen=True, slots=True)
class ReceiptFamily:
    family_id: str
    merchant_id: str
    name: str
    confidence: float = 0.0
    attributes: tuple[tuple[str, Any], ...] = ()
    history: tuple[tuple[str, Any], ...] = ()
    version: VersionMetadata = field(default_factory=lambda: VersionMetadata("receipt-family-v1"))


@dataclass(frozen=True, slots=True)
class LayoutProfile:
    profile_id: str
    merchant_id: str
    family_id: str = ""
    header_height_ratio: float | None = None
    table_width_ratio: float | None = None
    column_positions: tuple[float, ...] = ()
    payment_position_ratio: float | None = None
    footer_height_ratio: float | None = None
    whitespace_ratios: tuple[float, ...] = ()
    reading_pattern: tuple[str, ...] = ()
    sample_count: int = 0
    confidence: float = 0.0
    version: VersionMetadata = field(default_factory=lambda: VersionMetadata("merchant-layout-profile-v1"))


@dataclass(frozen=True, slots=True)
class VisualProfile:
    profile_id: str
    merchant_id: str
    family_id: str = ""
    logo_asset_references: tuple[str, ...] = ()
    dominant_colors: tuple[str, ...] = ()
    common_dimensions: tuple[tuple[float, float], ...] = ()
    spacing_statistics: tuple[float, ...] = ()
    image_statistics: tuple[tuple[str, float], ...] = ()
    version: VersionMetadata = field(default_factory=lambda: VersionMetadata("merchant-visual-profile-v1"))


@dataclass(frozen=True, slots=True)
class OcrCorrection:
    observed: str
    corrected: str
    occurrences: int = 1
    confidence: float = 0.0
    source: str = ""


@dataclass(frozen=True, slots=True)
class ProductVocabularyEntry:
    vocabulary_id: str
    merchant_id: str
    canonical_value: str
    aliases: tuple[str, ...] = ()
    common_ocr_errors: tuple[str, ...] = ()
    units: tuple[str, ...] = ()
    categories: tuple[str, ...] = ()
    observations: int = 0
    version: VersionMetadata = field(default_factory=lambda: VersionMetadata("merchant-product-vocabulary-v1"))


@dataclass(frozen=True, slots=True)
class MerchantStatistics:
    merchant_id: str
    receipt_count: int = 0
    average_width: float = 0.0
    average_height: float = 0.0
    typical_header_height: float = 0.0
    typical_footer_height: float = 0.0
    typical_item_count: float = 0.0
    typical_font_sizes: tuple[float, ...] = ()
    typical_line_spacing: float = 0.0
    typical_column_count: float = 0.0
    receipt_density: float = 0.0
    common_ocr_errors: tuple[OcrCorrection, ...] = ()
    average_confidence: float = 0.0
    receipt_frequency: float = 0.0
    version: VersionMetadata = field(default_factory=lambda: VersionMetadata("merchant-statistics-v1"))


@dataclass(frozen=True, slots=True)
class LearningMetadata:
    observation_count: int = 0
    correction_count: int = 0
    last_observed_at: str = ""
    last_corrected_at: str = ""
    learning_version: int = 1
    provenance: tuple[str, ...] = ()


@dataclass(frozen=True, slots=True)
class KnowledgeProfile:
    profile_id: str
    profile_type: str
    merchant_id: str
    family_id: str = ""
    attributes: tuple[tuple[str, Any], ...] = ()
    confidence: float = 0.0
    version: VersionMetadata = field(default_factory=lambda: VersionMetadata("merchant-knowledge-profile-v1"))


@dataclass(frozen=True, slots=True)
class MerchantBlueprint:
    identity: MerchantIdentity
    receipt_families: tuple[ReceiptFamily, ...] = ()
    aliases: tuple[MerchantAlias, ...] = ()
    layout_profiles: tuple[LayoutProfile, ...] = ()
    visual_profiles: tuple[VisualProfile, ...] = ()
    receipt_patterns: tuple[KnowledgeProfile, ...] = ()
    ocr_corrections: tuple[OcrCorrection, ...] = ()
    product_vocabulary: tuple[ProductVocabularyEntry, ...] = ()
    tax_profiles: tuple[KnowledgeProfile, ...] = ()
    coupon_profiles: tuple[KnowledgeProfile, ...] = ()
    payment_profiles: tuple[KnowledgeProfile, ...] = ()
    footer_profiles: tuple[KnowledgeProfile, ...] = ()
    font_families: tuple[str, ...] = ()
    receipt_widths: tuple[float, ...] = ()
    reading_patterns: tuple[str, ...] = ()
    statistics: MerchantStatistics | None = None
    learning: LearningMetadata = field(default_factory=LearningMetadata)
    version: VersionMetadata = field(default_factory=lambda: VersionMetadata("merchant-blueprint-v1"))

    @property
    def merchant_id(self) -> str:
        return self.identity.merchant_id


@dataclass(frozen=True, slots=True)
class ReceiptObservation:
    event_id: str
    merchant_id: str
    receipt_id: str
    family_id: str = ""
    measurements: tuple[tuple[str, float], ...] = ()
    vocabulary: tuple[str, ...] = ()
    confidence: float = 0.0
    observed_at: str = field(default_factory=utc_now)
    schema_version: str = "merchant-receipt-observation-v1"

    @classmethod
    def create(cls, merchant_id: str, receipt_id: str, **kwargs: Any) -> "ReceiptObservation":
        return cls(str(uuid4()), merchant_id, receipt_id, **kwargs)


@dataclass(frozen=True, slots=True)
class CorrectionEvent:
    event_id: str
    merchant_id: str
    receipt_id: str
    correction_type: str
    before: str
    after: str
    source: str = ""
    confidence: float = 1.0
    corrected_at: str = field(default_factory=utc_now)
    schema_version: str = "merchant-correction-event-v1"

    @classmethod
    def create(cls, merchant_id: str, receipt_id: str, correction_type: str, before: str, after: str, **kwargs: Any) -> "CorrectionEvent":
        return cls(str(uuid4()), merchant_id, receipt_id, correction_type, before, after, **kwargs)


@dataclass(frozen=True, slots=True)
class MerchantIntelligenceContext:
    merchant_key: str
    blueprint: MerchantBlueprint | None
    loaded: bool
    diagnostics: tuple[tuple[str, Any], ...] = ()
