from __future__ import annotations

from collections.abc import Mapping
from typing import Any, Iterable

from services.merchant_intelligence import MerchantBlueprint

from .models import ReceiptFamilyFeatureProfile


def _flatten_numeric(value: Any, prefix: str = "") -> dict[str, float]:
    result: dict[str, float] = {}
    if isinstance(value, Mapping):
        for key, item in value.items():
            child = f"{prefix}.{key}" if prefix else str(key)
            result.update(_flatten_numeric(item, child))
    elif isinstance(value, (int, float)) and not isinstance(value, bool):
        result[prefix] = float(value)
    return result


class ReceiptBlueprintMatcher:
    """Adapts repository data into physical family profiles without identity inference."""

    FEATURE_KEYS = ("feature_vector", "physical_features", "feature_profile")

    def profiles(self, blueprints: Iterable[MerchantBlueprint]) -> tuple[ReceiptFamilyFeatureProfile, ...]:
        profiles: list[ReceiptFamilyFeatureProfile] = []
        for blueprint in blueprints:
            for family in blueprint.receipt_families:
                attributes = dict(family.attributes)
                raw = next((attributes[key] for key in self.FEATURE_KEYS if key in attributes), {})
                metrics = _flatten_numeric(raw)
                metrics.update(self._layout_metrics(blueprint, family.family_id))
                metrics.update(self._statistical_metrics(blueprint))
                if not metrics:
                    continue
                weights = _flatten_numeric(attributes.get("feature_weights", {}))
                profiles.append(ReceiptFamilyFeatureProfile(
                    receipt_family=family.family_id,
                    feature_metrics=tuple(sorted(metrics.items())),
                    profile_version=family.version.entity_version,
                    blueprint_reference=blueprint.merchant_id,
                    confidence=family.confidence or 1.0,
                    weights=tuple(sorted(weights.items())),
                ))
        return tuple(profiles)

    @staticmethod
    def _layout_metrics(blueprint: MerchantBlueprint, family_id: str) -> dict[str, float]:
        matched = [profile for profile in blueprint.layout_profiles if profile.family_id in {"", family_id}]
        if not matched:
            return {}
        profile = matched[-1]
        values = {
            "layout.header_height_ratio": profile.header_height_ratio,
            "layout.footer_height_ratio": profile.footer_height_ratio,
            "table.average_width_ratio": profile.table_width_ratio,
            "layout.reading_column_count": float(len(profile.column_positions)) if profile.column_positions else None,
        }
        if profile.whitespace_ratios:
            values["density.whitespace_percentage"] = sum(profile.whitespace_ratios) / len(profile.whitespace_ratios)
        return {key: float(value) for key, value in values.items() if value is not None}

    @staticmethod
    def _statistical_metrics(blueprint: MerchantBlueprint) -> dict[str, float]:
        stats = blueprint.statistics
        if stats is None:
            return {}
        values = {
            "page.width": stats.average_width,
            "page.height": stats.average_height,
            "layout.reading_column_count": stats.typical_column_count,
            "spacing.average_line_spacing": stats.typical_line_spacing,
            "density.mean_density": stats.receipt_density,
            "geometry.confidence": stats.average_confidence,
        }
        return {key: float(value) for key, value in values.items() if value}
