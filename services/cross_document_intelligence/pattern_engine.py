from __future__ import annotations

import hashlib
from collections import Counter
from datetime import datetime

from .models import ContextEntity, EvidenceRecord, Pattern, Timeline


class PatternEngine:
    """Detects deterministic historical patterns; it does not predict."""

    def detect(
        self,
        entities: tuple[ContextEntity, ...],
        timelines: tuple[Timeline, ...],
        evidence: tuple[EvidenceRecord, ...],
    ) -> tuple[Pattern, ...]:
        evidence_by_entity = {
            entity.entity_id: tuple(
                item.evidence_id for item in evidence if entity.entity_id in item.source_entity_ids
            )
            for entity in entities
        }
        patterns: list[Pattern] = []
        for entity in entities:
            count = len(entity.document_references)
            if count < 2:
                continue
            pattern_type = {
                "Product": "recurring_purchase",
                "Merchant": "merchant_loyalty",
                "Warranty": "repeated_warranty",
                "MedicalRecord": "repeated_medical_procedure",
                "Category": "household_consumption",
                "Price": "price_change",
            }.get(entity.entity_type, "historical_recurrence")
            patterns.append(Pattern(
                self._id(pattern_type, entity.entity_id),
                pattern_type,
                (entity.entity_id,),
                entity.document_references,
                evidence_by_entity.get(entity.entity_id, ()),
                count,
                f"{entity.label} recurs across {count} documents; detection only.",
                entity.confidence,
                False,
            ))
            if entity.entity_type == "Price":
                patterns.append(Pattern(
                    self._id("expense_trend", entity.entity_id),
                    "expense_trend",
                    (entity.entity_id,),
                    entity.document_references,
                    evidence_by_entity.get(entity.entity_id, ()),
                    count,
                    f"Repeated expense evidence for {entity.label}; no forecast produced.",
                    entity.confidence,
                    False,
                ))
            timestamps = sorted(
                value for value in (
                    self._date(reference.timestamp)
                    for reference in entity.document_references
                ) if value is not None
            )
            if len(timestamps) >= 3:
                intervals = [
                    (timestamps[index] - timestamps[index - 1]).days
                    for index in range(1, len(timestamps))
                ]
                if intervals and max(intervals) - min(intervals) <= 5:
                    patterns.append(Pattern(
                        self._id("subscription_pattern", entity.entity_id),
                        "subscription_pattern",
                        (entity.entity_id,),
                        entity.document_references,
                        evidence_by_entity.get(entity.entity_id, ()),
                        count,
                        f"Evidence recurs at a consistent {round(sum(intervals) / len(intervals))}-day interval.",
                        entity.confidence,
                        False,
                    ))
            months = [
                self._month(reference.timestamp)
                for reference in entity.document_references
                if self._month(reference.timestamp)
            ]
            month_counts = Counter(months)
            if month_counts and max(month_counts.values()) >= 2:
                patterns.append(Pattern(
                    self._id("seasonal_purchase", entity.entity_id),
                    "seasonal_purchase",
                    (entity.entity_id,),
                    entity.document_references,
                    evidence_by_entity.get(entity.entity_id, ()),
                    max(month_counts.values()),
                    f"{entity.label} recurs in the same calendar month across evidence.",
                    entity.confidence,
                    False,
                ))
        return tuple(patterns)

    @staticmethod
    def _month(value: str) -> int | None:
        try:
            return datetime.fromisoformat(value.replace("Z", "+00:00")).month
        except (TypeError, ValueError):
            return None

    @staticmethod
    def _date(value: str):
        try:
            return datetime.fromisoformat(value.replace("Z", "+00:00"))
        except (TypeError, ValueError):
            return None

    @staticmethod
    def _id(*values: str) -> str:
        return hashlib.sha256("|".join(values).encode("utf-8")).hexdigest()[:24]
