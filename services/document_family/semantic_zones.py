from __future__ import annotations

import re

from services.receipt_dom import ReceiptDocument, ReceiptLine

from .models import SemanticZone, SemanticZoneType


def document_lines(document: ReceiptDocument) -> tuple[ReceiptLine, ...]:
    return tuple(node for node in document.walk() if isinstance(node, ReceiptLine))


class SemanticZoneEngine:
    PAYMENT = re.compile(r"\b(card|amex|visa|mastercard|approval|authorization|aid|entry method|chip|pan)\b", re.I)
    FINANCIAL = re.compile(r"\b(total|amount|subtotal|tax|tip|balance|due|refund)\b", re.I)
    REFERENCE = re.compile(r"\b(invoice|reference|ref\s*#|terminal|batch|sequence|seq\s*#|serial|receipt\s*(?:number|#)|rx\s*(?:number|#)|ndc|account\s*(?:number|#|summary))\b", re.I)
    ADDRESS = re.compile(r"(?:\b\d+\s+.+\b(?:st|street|ave|avenue|rd|road|blvd|drive|dr|lane|ln|highway|hwy)\b|\b[A-Z]{2}\s+\d{5}\b)", re.I)
    FOOTER = re.compile(r"\b(customer copy|thank you|warranty|return policy)\b", re.I)

    def build(self, document: ReceiptDocument, expected: tuple[SemanticZoneType, ...] = ()) -> tuple[SemanticZone, ...]:
        lines = document_lines(document)
        if not lines:
            return ()
        page_height = max((page.dimensions.height for page in document.pages), default=1.0)
        grouped: dict[SemanticZoneType, list[ReceiptLine]] = {}
        reasons: dict[SemanticZoneType, set[str]] = {}
        for line in lines:
            kind, reason = self._classify(line, page_height)
            grouped.setdefault(kind, []).append(line)
            reasons.setdefault(kind, set()).add(reason)
        return tuple(
            SemanticZone(
                zone_id=f"zone-{kind.value}", zone_type=kind,
                node_ids=tuple(line.id for line in values),
                confidence=round(min(0.98, 0.62 + 0.06 * len(values) + (0.08 if kind in expected else 0)), 3),
                reasons=tuple(sorted(reasons[kind])),
            )
            for kind, values in grouped.items()
        )

    def _classify(self, line: ReceiptLine, page_height: float) -> tuple[SemanticZoneType, str]:
        text = line.text.strip()
        if self.PAYMENT.search(text): return SemanticZoneType.PAYMENT, "payment_vocabulary"
        if self.FINANCIAL.search(text): return SemanticZoneType.FINANCIAL, "financial_vocabulary"
        if self.REFERENCE.search(text): return SemanticZoneType.REFERENCE, "reference_vocabulary"
        if self.ADDRESS.search(text): return SemanticZoneType.ADDRESS, "address_grammar"
        if self.FOOTER.search(text) or line.geometry.y > page_height * 0.88: return SemanticZoneType.FOOTER, "footer_position_or_vocabulary"
        if line.geometry.y < page_height * 0.18: return SemanticZoneType.MERCHANT, "header_position"
        return SemanticZoneType.ITEM, "body_default"
