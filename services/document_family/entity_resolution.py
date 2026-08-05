from __future__ import annotations

import re

from services.receipt_dom import ReceiptDocument

from .models import EntityCandidate, EntityType, FamilyEvidence, KeyValueRelationship, SemanticZone, SemanticZoneType
from .semantic_zones import document_lines


class EntityResolutionEngine:
    MONEY = re.compile(r"(?:\$\s*)?(-?\d+[.,]\d{2})\b")
    DATE = re.compile(r"\b(?:\d{1,2}[/-]){2}\d{2,4}\b")

    def resolve(self, document: ReceiptDocument, zones: tuple[SemanticZone, ...], relationships: tuple[KeyValueRelationship, ...],
                merchant_candidates=(), payment_candidates=(), address_candidates=()) -> tuple[EntityCandidate, ...]:
        zone_by_node = {node: zone for zone in zones for node in zone.node_ids}
        output = list(merchant_candidates) + list(payment_candidates) + list(address_candidates)
        for line in document_lines(document):
            zone = zone_by_node.get(line.id)
            text = line.text.strip()
            date = self.DATE.search(text)
            if date:
                output.append(self._candidate(line, EntityType.DATE, date.group(0), 0.9, zone, "date_pattern"))
            money = self.MONEY.search(text)
            if money and zone and zone.zone_type is SemanticZoneType.FINANCIAL:
                output.append(self._candidate(line, EntityType.FINANCIAL_AMOUNT, money.group(1).replace(",", "."), 0.9, zone, "financial_zone_money"))
        for relation in relationships:
            if any(token in relation.key.lower() for token in ("amount", "total", "balance", "due", "refund")):
                money = self.MONEY.search(relation.value)
                if money:
                    evidence = FamilyEvidence("key_value_relationship", relation.value, relation.confidence, "financial_key_value", (relation.key_node_id, relation.value_node_id))
                    output.append(EntityCandidate(
                        f"entity-financial-{relation.relationship_id}", EntityType.FINANCIAL_AMOUNT,
                        money.group(1).replace(",", "."), relation.confidence,
                        relation.zone_id, (evidence,), "financial_key_value_relationship",
                    ))
        return tuple(self._resolve_competition(output))

    def _candidate(self, line, kind, value, confidence, zone, reason):
        evidence = FamilyEvidence("entity_resolution", line.text, confidence, reason, (line.id,))
        return EntityCandidate(f"entity-{kind.value}-{line.id}", kind, value, confidence, zone.zone_id if zone else "", (evidence,), reason)

    def _resolve_competition(self, values):
        best = {}
        for value in values:
            key = (value.entity_type, value.value.lower())
            if key not in best or value.confidence > best[key].confidence:
                best[key] = value
        return sorted(best.values(), key=lambda item: (-item.confidence, item.entity_type.value, item.value.lower()))
