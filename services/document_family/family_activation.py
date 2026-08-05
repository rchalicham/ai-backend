from __future__ import annotations

from collections import defaultdict

from services.receipt_classification import ReceiptClassification
from services.receipt_dom import ReceiptDocument
from services.receipt_structure import ReceiptPhysicalStructure

from .family_registry import DocumentFamilyRegistry
from .models import DocumentFamily, FamilyActivation, FamilyEvidence
from .semantic_zones import document_lines


class DocumentFamilyActivationEngine:
    """Ranks generic family evidence; it does not parse or mutate document values."""

    FAMILY_ALIASES = {
        "retail receipt": DocumentFamily.RETAIL_RECEIPT,
        "retail_receipt": DocumentFamily.RETAIL_RECEIPT,
        "restaurant receipt": DocumentFamily.RESTAURANT_RECEIPT,
        "fuel receipt": DocumentFamily.FUEL_RECEIPT,
        "pharmacy receipt": DocumentFamily.PHARMACY_RECEIPT,
        "payment slip": DocumentFamily.PAYMENT_SLIP,
        "payment-slip": DocumentFamily.PAYMENT_SLIP,
        "credit card slip": DocumentFamily.CREDIT_CARD_SLIP,
        "invoice": DocumentFamily.INVOICE,
        "statement": DocumentFamily.STATEMENT,
        "warranty": DocumentFamily.WARRANTY,
        "refund": DocumentFamily.REFUND_RECEIPT,
        "return": DocumentFamily.RETURN_RECEIPT,
        "donation": DocumentFamily.DONATION_RECEIPT,
    }

    def __init__(self, registry: DocumentFamilyRegistry | None = None) -> None:
        self.registry = registry or DocumentFamilyRegistry()

    def activate(self, document: ReceiptDocument, structure: ReceiptPhysicalStructure,
                 classification: ReceiptClassification | None, merchant_knowledge=None,
                 grammar_context=None, enterprise_knowledge=None) -> FamilyActivation:
        scores: dict[DocumentFamily, float] = defaultdict(float)
        evidence: dict[DocumentFamily, list[FamilyEvidence]] = defaultdict(list)
        for candidate in classification.candidates if classification else ():
            family = self._family(candidate.receipt_family)
            weight = min(0.55, candidate.confidence * 0.55)
            scores[family] += weight
            evidence[family].append(FamilyEvidence("classification", candidate.receipt_family, weight, candidate.reason))
        normalized_text = "\n".join(line.text for line in document_lines(document)).lower()
        for profile in self.registry.profiles():
            if profile.family is DocumentFamily.UNKNOWN:
                continue
            matched = tuple(term for term in profile.activation_terms if term in normalized_text)
            for term in matched:
                weight = 0.16 if len(term) >= 6 else 0.1
                scores[profile.family] += weight
                evidence[profile.family].append(FamilyEvidence("document_text", term, weight, "generic_family_activation_term"))
            if profile.item_table_expected and structure.candidate_tables:
                scores[profile.family] += 0.08
                evidence[profile.family].append(FamilyEvidence("physical_structure", "candidate_table", 0.08, "item_table_compatible"))
        ranked = sorted(scores.items(), key=lambda item: (-item[1], item[0].value))
        family, score = ranked[0] if ranked and ranked[0][1] >= 0.16 else (DocumentFamily.UNKNOWN, 0.2)
        profile = self.registry.profile(family)
        return FamilyActivation(
            family=family, confidence=round(min(0.99, score), 3), profile_id=profile.profile_id,
            evidence=tuple(evidence[family]),
            alternatives=tuple((item[0].value, round(min(0.99, item[1]), 3)) for item in ranked[1:4]),
        )

    def _family(self, value: str) -> DocumentFamily:
        normalized = str(value or "").strip().lower().replace("-", " ")
        if normalized in self.FAMILY_ALIASES:
            return self.FAMILY_ALIASES[normalized]
        try:
            return DocumentFamily(normalized.replace(" ", "_"))
        except ValueError:
            return DocumentFamily.UNKNOWN
