from __future__ import annotations

import re

from services.receipt_dom import ReceiptDocument

from .models import EntityCandidate, EntityType, FamilyEvidence, KeyValueRelationship, SemanticZone, SemanticZoneType
from .semantic_zones import document_lines


class PaymentCandidateEngine:
    BRAND = re.compile(r"\b(american express|amex|visa|mastercard|discover)\b", re.I)
    PAN = re.compile(r"(?:x|\*){3,}\s*(\d{4})\b", re.I)

    def resolve(self, document: ReceiptDocument, zones: tuple[SemanticZone, ...], relationships: tuple[KeyValueRelationship, ...]) -> tuple[EntityCandidate, ...]:
        payment_nodes = {node for zone in zones if zone.zone_type in {SemanticZoneType.PAYMENT, SemanticZoneType.REFERENCE} for node in zone.node_ids}
        output = []
        for line in document_lines(document):
            if line.id not in payment_nodes:
                continue
            text = line.text.strip()
            brand = self.BRAND.search(text)
            if brand:
                output.append(self._candidate(line.id, EntityType.PAYMENT_BRAND, brand.group(1).upper(), 0.91, "payment_brand_vocabulary"))
            pan = self.PAN.search(text.replace(" ", ""))
            if pan:
                output.append(self._candidate(line.id, EntityType.MASKED_PAN, pan.group(1), 0.95, "masked_pan_pattern"))
            if text.lower().startswith("aid:"):
                output.append(self._candidate(line.id, EntityType.PAYMENT_IDENTIFIER, text.split(":", 1)[-1].strip(), 0.97, "emv_aid_prefix_not_phone"))
            if "entry method" in text.lower():
                output.append(self._candidate(line.id, EntityType.ENTRY_METHOD, text.split(":", 1)[-1].strip(), 0.92, "payment_entry_method"))
        for relation in relationships:
            key = relation.key.lower()
            kind = EntityType.APPROVAL_CODE if "approval" in key else EntityType.AUTHORIZATION_CODE if "author" in key else EntityType.REFERENCE_NUMBER if any(token in key for token in ("invoice", "reference", "batch", "terminal")) else None
            if kind:
                output.append(EntityCandidate(f"payment-{relation.relationship_id}", kind, relation.value, relation.confidence, relation.zone_id, relation.evidence, "geometry_key_value_payment_candidate"))
        return tuple(sorted(output, key=lambda item: (-item.confidence, item.entity_type.value, item.value)))

    def _candidate(self, node_id, kind, value, confidence, reason):
        evidence = FamilyEvidence("payment_zone", value, confidence, reason, (node_id,))
        return EntityCandidate(f"payment-{kind.value}-{node_id}", kind, value, confidence, "zone-payment_zone", (evidence,), reason)
