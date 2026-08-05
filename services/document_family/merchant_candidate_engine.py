from __future__ import annotations

import re

from services.receipt_dom import ReceiptDocument

from .models import EntityCandidate, EntityType, FamilyEvidence, SemanticZone, SemanticZoneType
from .semantic_zones import document_lines


class MerchantCandidateEngine:
    EXCLUDED = re.compile(r"\b(amex|visa|mastercard|credit card|approval|authorization|invoice|amount|total|aid|entry method)\b", re.I)
    ADDRESS = re.compile(r"(?:\b\d+\s+.+\b(?:st|street|ave|avenue|rd|road|blvd|drive|dr|lane|ln|hwy|highway)\b|\b[A-Z]{2}\s+\d{5}\b)", re.I)

    def rank(self, document: ReceiptDocument, zones: tuple[SemanticZone, ...], merchant_knowledge=None) -> tuple[EntityCandidate, ...]:
        allowed = {node for zone in zones if zone.zone_type is SemanticZoneType.MERCHANT for node in zone.node_ids}
        candidates = []
        for line in document_lines(document):
            text = line.text.strip()
            if line.id not in allowed or len(text) < 3 or self.EXCLUDED.search(text) or self.ADDRESS.search(text) or re.search(r"\d{4,}", text):
                continue
            uppercase = sum(character.isupper() for character in text) / max(sum(character.isalpha() for character in text), 1)
            header_priority = max(0.0, 0.12 - 0.025 * max(0, line.reading_order))
            confidence = min(0.98, 0.54 + uppercase * 0.16 + line.confidence * 0.12 + header_priority)
            evidence = FamilyEvidence("merchant_zone", text, confidence, "header_zone_non_excluded_candidate", (line.id,))
            candidates.append(EntityCandidate(f"merchant-{line.id}", EntityType.MERCHANT, text, round(confidence, 3), "zone-merchant_zone", (evidence,), "merchant_zone_header_candidate"))
        return tuple(sorted(candidates, key=lambda item: (-item.confidence, item.value.lower())))
