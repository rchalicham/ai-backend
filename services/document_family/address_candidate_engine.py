from __future__ import annotations

import re

from services.receipt_dom import ReceiptDocument

from .models import EntityCandidate, EntityType, FamilyEvidence, SemanticZone, SemanticZoneType
from .semantic_zones import document_lines


class AddressCandidateEngine:
    STREET = re.compile(r"\b\d+\s+.+\b(st|street|ave|avenue|rd|road|blvd|drive|dr|lane|ln|hwy|highway)\b", re.I)
    CITY = re.compile(r"\b[A-Za-z .'-]+,?\s+[A-Z]{2}\s+\d{5}(?:-\d{4})?\b")

    def resolve(self, document: ReceiptDocument, zones: tuple[SemanticZone, ...], merchant_context=None) -> tuple[EntityCandidate, ...]:
        zone_nodes = {node for zone in zones if zone.zone_type in {SemanticZoneType.ADDRESS, SemanticZoneType.MERCHANT} for node in zone.node_ids}
        matches = []
        for line in document_lines(document):
            if line.id not in zone_nodes:
                continue
            text = line.text.strip()
            reason = "street_suffix_grammar" if self.STREET.search(text) else "city_state_zip_grammar" if self.CITY.search(text) else ""
            if reason:
                confidence = 0.91 if reason.startswith("street") else 0.94
                evidence = FamilyEvidence("address_grammar", text, confidence, reason, (line.id,))
                matches.append(EntityCandidate(f"address-{line.id}", EntityType.ADDRESS, text, confidence, "zone-address_zone", (evidence,), reason))
        return tuple(matches)
