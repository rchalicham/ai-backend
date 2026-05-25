from __future__ import annotations

import hashlib
import re
from collections import Counter
from dataclasses import dataclass, field
from typing import Any

from services.receipt_entity_extraction import ReceiptEntityExtractionEngine
from services.receipt_ontology_engine import ReceiptOntologyEngine
from services.receipt_section_engine import ReceiptSectionExtractionEngine
from services.receipt_visual_hierarchy import LEGAL_DISCLAIMER_TERMS

try:
    from rapidfuzz import fuzz
except Exception:  # pragma: no cover - dependency may be unavailable in minimal local test envs.
    fuzz = None


RECEIPT_LEVEL_TERMS = (
    "SUBTOTAL", "SUB TOTAL", "TOTAL", "TAX", "TIP", "CHANGE", "BALANCE", "PAYMENT",
    "APPROVED", "AUTH", "AID", "TERMINAL", "TRANS", "TRANSACTION", "CARD", "VISA",
    "MASTERCARD", "AMEX", "DISCOVER", "CASH", "CREDIT", "DEBIT", "THANK", "SURVEY",
    "FEEDBACK", "SAVINGS", "ITEM COUNT", "SOLD ITEM",
)
RECEIPT_LEVEL_OCR_MUTATIONS = {
    "GATT", "HARGE", "T0TAL", "TOTAI", "TQTAL", "SUBT0TAL", "CHARGF", "CHAR6E",
}
MONTH_ABBREVIATIONS = {
    "JAN": "01",
    "FEB": "02",
    "MAR": "03",
    "APR": "04",
    "MAY": "05",
    "JUN": "06",
    "JUL": "07",
    "AUG": "08",
    "SEP": "09",
    "SEPT": "09",
    "OCT": "10",
    "NOV": "11",
    "DEC": "12",
}


@dataclass(frozen=True)
class OCRBox:
    text: str
    x: float = 0
    y: float = 0
    width: float = 0
    height: float = 0
    confidence: float = 1.0
    page: int = 1

    @classmethod
    def from_payload(cls, payload: dict[str, Any]) -> "OCRBox":
        bbox = payload.get("bbox") or payload.get("box") or {}
        if isinstance(bbox, list) and len(bbox) >= 4:
            x_values = [float(point[0]) for point in bbox if isinstance(point, (list, tuple)) and len(point) >= 2]
            y_values = [float(point[1]) for point in bbox if isinstance(point, (list, tuple)) and len(point) >= 2]
            bbox = {
                "x": min(x_values) if x_values else 0,
                "y": min(y_values) if y_values else 0,
                "width": (max(x_values) - min(x_values)) if len(x_values) >= 2 else 0,
                "height": (max(y_values) - min(y_values)) if len(y_values) >= 2 else 0,
            }
        return cls(
            text=str(payload.get("text") or payload.get("value") or "").strip(),
            x=float(payload.get("x", bbox.get("x", bbox.get("left", 0))) or 0),
            y=float(payload.get("y", bbox.get("y", bbox.get("top", 0))) or 0),
            width=float(payload.get("width", bbox.get("width", bbox.get("w", 0))) or 0),
            height=float(payload.get("height", bbox.get("height", bbox.get("h", 0))) or 0),
            confidence=float(payload.get("confidence", payload.get("conf", 1.0)) or 0),
            page=int(payload.get("page", payload.get("pageNumber", 1)) or 1),
        )


@dataclass
class ReconstructedLine:
    text: str
    confidence: float = 1.0
    page: int = 1
    y: float = 0
    boxes: list[OCRBox] = field(default_factory=list)

    @property
    def x(self) -> float:
        if not self.boxes:
            return 0
        return min(box.x for box in self.boxes)

    @property
    def width(self) -> float:
        if not self.boxes:
            return max(80.0, len(self.text) * 7.0)
        left = min(box.x for box in self.boxes)
        right = max(box.x + box.width for box in self.boxes)
        return max(0.0, right - left)

    @property
    def height(self) -> float:
        if not self.boxes:
            return 14.0
        top = min(box.y for box in self.boxes)
        bottom = max(box.y + box.height for box in self.boxes)
        return max(0.0, bottom - top)


@dataclass
class OCRRegion:
    id: str
    kind: str
    text: str
    page: int
    x: float
    y: float
    width: float
    height: float
    confidence: float
    line_indexes: list[int] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "kind": self.kind,
            "text": self.text,
            "page": self.page,
            "bbox": {
                "x": round(self.x, 2),
                "y": round(self.y, 2),
                "width": round(self.width, 2),
                "height": round(self.height, 2),
            },
            "confidence": round(self.confidence, 3),
            "lineIndexes": self.line_indexes,
        }


@dataclass
class SemanticBlock:
    id: str
    kind: str
    text: str
    confidence: float
    line_indexes: list[int] = field(default_factory=list)
    region_ids: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "kind": self.kind,
            "text": self.text,
            "confidence": round(self.confidence, 3),
            "lineIndexes": self.line_indexes,
            "regionIds": self.region_ids,
        }


@dataclass
class ParsedReceiptCandidate:
    merchant: str = ""
    merchant_trace: dict[str, Any] = field(default_factory=dict)
    lines: list[ReconstructedLine] = field(default_factory=list)
    items: list[dict[str, Any]] = field(default_factory=list)
    facts: dict[str, str] = field(default_factory=dict)
    regions: list[OCRRegion] = field(default_factory=list)
    semantic_blocks: list[SemanticBlock] = field(default_factory=list)
    tables: list[dict[str, Any]] = field(default_factory=list)
    graph: dict[str, Any] = field(default_factory=dict)
    layout_json: dict[str, Any] = field(default_factory=dict)
    warnings: list[str] = field(default_factory=list)
    confidence: dict[str, Any] = field(default_factory=dict)
    retry_plan: list[dict[str, Any]] = field(default_factory=list)
    entities: dict[str, Any] = field(default_factory=dict)
    section_extraction: dict[str, Any] = field(default_factory=dict)
    ontology: dict[str, Any] = field(default_factory=dict)


def _compact_text(value: str) -> str:
    return re.sub(r"\s+", " ", str(value or "")).strip()


def _amount(value: Any) -> str:
    text = str(value or "").replace("$", "").replace(",", ".")
    match = re.search(r"-?\d{1,5}(?:\.\d{2})\b", text)
    return match.group(0) if match else ""


def _numeric(value: Any) -> float:
    parsed = _amount(value)
    return float(parsed) if parsed else 0.0


def _line_signature(text: str) -> str:
    normalized = re.sub(r"[^A-Z0-9.]+", "", str(text or "").upper())
    normalized = re.sub(r"\b\d{5,12}\b", "", normalized)
    return hashlib.sha1(normalized.encode("utf-8")).hexdigest()


class ReceiptLineReconstructor:
    """Rebuilds receipt rows from OCR boxes, preserving visual left-to-right order."""

    def reconstruct(self, raw_text: str, lines: list[str] | None = None, boxes: list[dict[str, Any]] | None = None) -> list[ReconstructedLine]:
        ocr_boxes = [OCRBox.from_payload(box) for box in boxes or [] if isinstance(box, dict) and str(box.get("text") or box.get("value") or "").strip()]
        if ocr_boxes:
            return self._from_boxes(ocr_boxes)
        source_lines = [line for line in (lines or []) if str(line).strip()]
        if not source_lines:
            source_lines = [line for line in (raw_text or "").splitlines() if str(line).strip()]
        return [
            ReconstructedLine(text=_compact_text(line), confidence=1.0, page=1, y=float(index))
            for index, line in enumerate(source_lines)
            if _compact_text(line)
        ]

    def _from_boxes(self, boxes: list[OCRBox]) -> list[ReconstructedLine]:
        by_page: dict[int, list[OCRBox]] = {}
        for box in boxes:
            by_page.setdefault(box.page, []).append(box)

        lines: list[ReconstructedLine] = []
        for page, page_boxes in sorted(by_page.items()):
            sorted_boxes = sorted(page_boxes, key=lambda box: (box.y, box.x))
            median_height = self._median([box.height for box in sorted_boxes if box.height > 0]) or 14
            y_tolerance = max(8.0, median_height * 0.72)
            rows: list[list[OCRBox]] = []
            for box in sorted_boxes:
                target = next((row for row in rows if abs(self._row_center(row) - (box.y + box.height / 2)) <= y_tolerance), None)
                if target is None:
                    rows.append([box])
                else:
                    target.append(box)

            for row in rows:
                ordered = sorted(row, key=lambda box: box.x)
                text = _compact_text(" ".join(box.text for box in ordered if box.text))
                if text:
                    lines.append(ReconstructedLine(
                        text=text,
                        confidence=sum(box.confidence for box in ordered) / max(len(ordered), 1),
                        page=page,
                        y=self._row_center(ordered),
                        boxes=ordered,
                    ))
        return sorted(lines, key=lambda line: (line.page, line.y))

    def _row_center(self, boxes: list[OCRBox]) -> float:
        return sum(box.y + box.height / 2 for box in boxes) / max(len(boxes), 1)

    def _median(self, values: list[float]) -> float:
        if not values:
            return 0
        sorted_values = sorted(values)
        return sorted_values[len(sorted_values) // 2]


class ReceiptDuplicateSuppressor:
    def __init__(self) -> None:
        self.last_diagnostics: list[dict[str, Any]] = []

    def suppress(self, lines: list[ReconstructedLine]) -> list[ReconstructedLine]:
        seen: dict[str, ReconstructedLine] = {}
        output: list[ReconstructedLine] = []
        subtotal_seen = False
        diagnostics: list[dict[str, Any]] = []
        for line in lines:
            text = _compact_text(line.text)
            if not text:
                continue
            upper = text.upper()
            if subtotal_seen and self._looks_like_item_line(text):
                signature = _line_signature(text)
                if signature in seen:
                    diagnostics.append(self._diagnostic(line, seen[signature], "duplicate_later_ocr_pass_after_subtotal"))
                    continue
            if re.search(r"\bSUB\s*TOTAL\b|\bSUBTOTAL\b", upper):
                subtotal_seen = True
            if self._looks_like_split_table_component(text):
                output.append(line)
                continue
            signature = _line_signature(text)
            current = seen.get(signature)
            if current and current.confidence >= line.confidence:
                diagnostics.append(self._diagnostic(line, current, "duplicate_lower_confidence_line"))
                continue
            if current and current in output:
                output.remove(current)
                diagnostics.append(self._diagnostic(current, line, "duplicate_replaced_by_higher_confidence_line"))
            seen[signature] = line
            output.append(line)
        self.last_diagnostics = diagnostics[:120]
        return output

    def _looks_like_item_line(self, text: str) -> bool:
        upper = text.upper()
        return bool(re.search(r"[A-Za-z]{3,}", text) and re.search(r"\d{1,5}(?:[., ]\d{2})\b", text)) and not any(term in upper for term in RECEIPT_LEVEL_TERMS)

    def _looks_like_split_table_component(self, text: str) -> bool:
        compacted = _compact_text(text)
        upper = compacted.upper()
        if re.fullmatch(r"\$?\s*\d{1,7}(?:[.,]\d{2})\s*[A-Z]?", compacted, flags=re.IGNORECASE):
            return True
        if re.fullmatch(r"\d{1,4}(?:[.,]\d+)?", compacted):
            return True
        if (
            re.search(r"[A-Za-z]{3,}", compacted)
            and not any(term in upper for term in RECEIPT_LEVEL_TERMS)
            and not re.search(r"\d{4,}", compacted)
        ):
            return True
        return False

    def _diagnostic(self, duplicate: ReconstructedLine, selected: ReconstructedLine, reason: str) -> dict[str, Any]:
        return {
            "reason": reason,
            "duplicate": {
                "text": duplicate.text,
                "confidence": round(duplicate.confidence, 3),
                "lineIndex": duplicate.boxes[0].page if duplicate.boxes else None,
            },
            "selected": {
                "text": selected.text,
                "confidence": round(selected.confidence, 3),
            },
            "signature": _line_signature(duplicate.text),
        }


class MerchantNormalizer:
    PHARMACY_TERMS = ("PHARMACY", "PHARMA", "DRUG", "RX", "PRESCRIPTION")
    BUSINESS_SUFFIX_TERMS = (
        "LLC", "L L C", "INC", "LTD", "CORP", "CORPORATION", "COMPANY", "CO",
        "CENTER", "CENTERS", "CENTRE", "MARKET", "MART", "STORE", "STORES",
        "PHARMACY", "RESTAURANT", "KITCHEN", "CAFE", "GROCERY",
    )
    KNOWN: dict[str, tuple[str, tuple[str, ...]]] = {}
    HIGH_CONFIDENCE_THRESHOLD = 0.82
    LOW_CONFIDENCE_PRESERVE_THRESHOLD = 0.72
    RECEIPT_NOISE = re.compile(
        r"\b(?:REG|TRN|CSHR|STR|STORE|SUBTOTAL|TOTAL|TAX|VISA|CREDIT|DEBIT|APPROVED|AUTH|REF|AID|TERMINAL|"
        r"CHANGE|RETURN|POLICY|RECEIPT|DATE|PHARMACY\s*:\s*\d|NO SIGNATURE|NO PURCHASE|SURVEY|FEEDBACK|QUANTITY|PRICE|"
        r"VOID WHERE PROHIBITED|PROHIBITED|SWEEPSTAKES|SWEEPST|OFFICIAL RULES|RULES)\b",
        flags=re.IGNORECASE,
    )

    def normalize(self, raw_text: str, candidate: str = "") -> str:
        return self.resolve(raw_text, candidate)["merchant"]

    def resolve(self, raw_text: str, candidate: str = "") -> dict[str, Any]:
        scored = self.candidates(raw_text, candidate)
        raw_merchant = self._raw_ocr_merchant(raw_text, candidate)
        top = scored[0] if scored else None
        rejected = scored[1:8] if scored else []
        if top and top["confidence"] >= self.HIGH_CONFIDENCE_THRESHOLD:
            return {
                "merchant": top["merchant"],
                "confidence": top["confidence"],
                "source": "normalized",
                "rawMerchant": raw_merchant,
                "selectedCandidate": top,
                "evidence": top.get("evidence", []),
                "rejectedCandidates": rejected,
                "preservedRawOcr": False,
            }
        if raw_merchant:
            return {
                "merchant": raw_merchant,
                "confidence": round(float(top.get("confidence", 0.0)) if top else 0.58, 3),
                "source": "raw_ocr_preserved",
                "rawMerchant": raw_merchant,
                "selectedCandidate": top,
                "evidence": top.get("evidence", []) if top else [],
                "rejectedCandidates": rejected,
                "preservedRawOcr": True,
                "reason": "normalized_candidate_below_confidence_threshold",
            }
        if top and top["confidence"] >= self.LOW_CONFIDENCE_PRESERVE_THRESHOLD:
            return {
                "merchant": top["merchant"],
                "confidence": top["confidence"],
                "source": "normalized_low_confidence_no_raw_ocr",
                "rawMerchant": "",
                "selectedCandidate": top,
                "evidence": top.get("evidence", []),
                "rejectedCandidates": rejected,
                "preservedRawOcr": False,
            }
        return {
            "merchant": "",
            "confidence": 0.0,
            "source": "empty",
            "rawMerchant": raw_merchant,
            "selectedCandidate": top,
            "evidence": [],
            "rejectedCandidates": rejected,
            "preservedRawOcr": False,
        }

    def _raw_ocr_merchant(self, raw_text: str, candidate: str = "") -> str:
        compact_candidate = _compact_text(candidate)
        header_context = [_compact_text(line) for line in raw_text.splitlines()[:18] if _compact_text(line)]
        ranked = self._ranked_raw_ocr_merchant(raw_text, candidate)
        if ranked:
            return ranked
        recovered_acronym = self._recover_acronym_merchant(raw_text)
        if recovered_acronym:
            return recovered_acronym
        first_lines = header_context[:8]
        for index, line in enumerate(first_lines):
            if index == 0 and re.fullmatch(r"[A-Z0-9]{3,4}", line):
                return line
            domain = self._domain_merchant_from_line(line)
            if domain:
                return domain
            if self._looks_like_header_merchant(line) and not self._followed_by_split_item_price(header_context, index):
                return self._title_preserving_acronyms(line)
        if compact_candidate and self._looks_like_header_merchant(compact_candidate):
            candidate_score, _reasons = self._raw_merchant_line_score([compact_candidate], 0)
            if candidate_score >= 0.72:
                return self._title_preserving_acronyms(compact_candidate)
        return ""

    def _followed_by_split_item_price(self, lines: list[str], index: int) -> bool:
        for candidate in lines[index + 1: min(len(lines), index + 4)]:
            text = _compact_text(candidate)
            if re.fullmatch(r"\d{1,3}", text):
                continue
            if re.fullmatch(r"-?\$?\d{1,7}(?:[.,]\d{2})", text, flags=re.IGNORECASE):
                return True
            if re.search(r"[A-Za-z]{3,}", text):
                return False
        return False

    def candidates(self, raw_text: str, candidate: str = "") -> list[dict[str, Any]]:
        combined = _compact_text(f"{candidate}\n{raw_text}")
        upper_combined = combined.upper()
        raw_upper = _compact_text(raw_text).upper()
        generated_candidates = self.generate_candidates(raw_text, candidate)
        text_candidates = [item["text"] for item in generated_candidates]
        scored: list[dict[str, Any]] = []
        domain_source = f"{candidate}\n{raw_text}".upper()
        for domain, merchant in self._domain_evidence(domain_source):
            scored.append(self._candidate(
                merchant,
                0.98,
                [f"domain:{domain}"],
                [{"type": "domain_ocr", "value": domain, "weight": 1.0, "confidence": 0.98}],
                text_candidates,
            ))
        for token, merchant_payload in self.KNOWN.items():
            merchant, aliases = merchant_payload
            alias_terms = (token, *aliases)
            score = 0.0
            reasons: list[str] = []
            evidence: list[dict[str, Any]] = []
            for alias in alias_terms:
                alias_upper = alias.upper()
                if alias_upper and alias_upper in raw_upper:
                    keyword_score = 0.9 if alias_upper == token.upper() else 0.82
                    score = max(score, keyword_score)
                    reasons.append(f"keyword:{alias}")
                    evidence.append({"type": "logo_or_header_ocr", "value": alias, "weight": 0.82, "confidence": keyword_score})
                for window in generated_candidates:
                    similarity = self._similarity(alias_upper, window["text"].upper())
                    if similarity >= 84:
                        source = window.get("source")
                        confidence_bonus = 0.04 if source == "header" else 0.0
                        fuzzy_score = 0.70 + (similarity - 84) / 140 + confidence_bonus
                        if source == "candidate":
                            fuzzy_score = min(fuzzy_score, 0.68)
                        if source in {"body", "body:pair", "body:triple"}:
                            fuzzy_score = min(fuzzy_score, 0.78)
                        score = max(score, fuzzy_score)
                        reasons.append(f"fuzzy:{alias}:{round(similarity, 1)}:{source}")
                        evidence.append({"type": "fuzzy_embedding", "value": window["text"], "weight": 0.35, "confidence": round(fuzzy_score, 3)})
            score = max(score, self._address_phone_score(merchant, upper_combined, reasons, evidence))
            score = max(score, self._semantic_store_score(merchant, upper_combined, reasons, evidence))
            score = max(score, self._partial_ocr_score(merchant, generated_candidates, upper_combined, reasons, evidence))
            if score >= 0.72:
                scored.append(self._candidate(merchant, score, reasons, evidence, text_candidates))
        scored.sort(key=lambda item: (item["confidence"], len(item["reasons"])), reverse=True)
        return scored

    def _candidate(
        self,
        merchant: str,
        score: float,
        reasons: list[str],
        evidence: list[dict[str, Any]],
        text_candidates: list[str],
    ) -> dict[str, Any]:
        confidence = round(min(0.99, score), 3)
        return {
            "merchant": merchant,
            "confidence": confidence,
            "reasons": reasons,
            "evidence": evidence,
            "qdrantReadyText": " ".join(text_candidates[:8])[:500],
            "qdrantPayload": {
                "documentType": "receipt",
                "entityType": "merchant",
                "normalizedMerchant": merchant,
                "candidateText": " ".join(text_candidates[:8])[:500],
                "correlationReasons": reasons[:12],
                "evidence": evidence[:12],
            },
        }

    def _domain_evidence(self, upper_combined: str) -> list[tuple[str, str]]:
        found: list[tuple[str, str]] = []
        for line in str(upper_combined or "").splitlines():
            for match in re.finditer(r"\b(?:WWW\s*)?([A-Z0-9][A-Z0-9 -]{2,35})\s*\.\s*(COM|NET|ORG)\b", line):
                label = re.sub(r"\s+", " ", match.group(1)).strip(" -")
                domain = f"{label}.{match.group(2)}"
                merchant = self._merchant_from_domain_label(label)
                if merchant:
                    found.append((domain, merchant))
        return found

    def _domain_merchant_from_line(self, line: str) -> str:
        for domain, merchant in self._domain_evidence(line.upper()):
            return merchant
        return ""

    def _merchant_from_domain_label(self, label: str) -> str:
        cleaned = re.sub(r"(?:FEEDBACK|SURVEY|REWARDS|REWARD)$", "", str(label or "").upper())
        cleaned = re.sub(r"[-_]+", " ", cleaned)
        cleaned = re.sub(r"[^A-Z0-9 ]+", "", cleaned)
        cleaned = re.sub(r"\s+", " ", cleaned).strip()
        if not cleaned or cleaned in {"WWW", "EMAIL", "RECEIPT"}:
            return ""
        return cleaned.title()

    def generate_candidates(self, raw_text: str, candidate: str = "") -> list[dict[str, Any]]:
        generated: list[dict[str, Any]] = []
        if _compact_text(candidate):
            generated.append({"text": _compact_text(candidate), "source": "candidate", "confidence": 0.95})
        lines = [_compact_text(line) for line in (raw_text or "").splitlines() if _compact_text(line)]
        for index, line in enumerate(lines[:18]):
            canonical_line = self._canonical(line)
            source = "header" if index <= 4 else "body"
            if canonical_line and not self.RECEIPT_NOISE.search(line):
                generated.append({"text": line, "source": source, "confidence": max(0.55, 0.95 - (index * 0.035))})
            if index + 1 < len(lines):
                pair = _compact_text(f"{line} {lines[index + 1]}")
                if len(pair) <= 120:
                    generated.append({"text": pair, "source": f"{source}:pair", "confidence": max(0.5, 0.9 - (index * 0.03))})
            if index + 2 < len(lines):
                triple = _compact_text(f"{line} {lines[index + 1]} {lines[index + 2]}")
                if len(triple) <= 160:
                    generated.append({"text": triple, "source": f"{source}:triple", "confidence": max(0.45, 0.86 - (index * 0.03))})

        recovered = self._recover_partial_ocr_fragments(lines)
        generated.extend({"text": text, "source": "partial-ocr", "confidence": 0.74} for text in recovered)
        seen: set[str] = set()
        unique: list[dict[str, Any]] = []
        for item in generated:
            key = self._canonical(item["text"])
            if key and key not in seen:
                seen.add(key)
                unique.append(item)
        return unique

    def _merchant_text_windows(self, raw_text: str, candidate: str = "") -> list[str]:
        return [item["text"] for item in self.generate_candidates(raw_text, candidate)]

    def _recover_partial_ocr_fragments(self, lines: list[str]) -> list[str]:
        return []

    def _address_phone_score(self, merchant: str, combined: str, reasons: list[str], evidence: list[dict[str, Any]]) -> float:
        return 0.0

    def _semantic_store_score(self, merchant: str, combined: str, reasons: list[str], evidence: list[dict[str, Any]]) -> float:
        return 0.0

    def _partial_ocr_score(self, merchant: str, windows: list[dict[str, Any]], combined: str, reasons: list[str], evidence: list[dict[str, Any]]) -> float:
        return 0.0

    def _similarity(self, left: str, right: str) -> float:
        left_clean = self._canonical(left)
        right_clean = self._canonical(right)
        if not left_clean or not right_clean:
            return 0.0
        if left_clean in right_clean:
            return 100.0
        if fuzz is not None:
            return float(max(fuzz.partial_ratio(left_clean, right_clean), fuzz.token_set_ratio(left_clean, right_clean)))
        left_tokens = set(left_clean.split())
        right_tokens = set(right_clean.split())
        return 100.0 * len(left_tokens & right_tokens) / max(len(left_tokens | right_tokens), 1)

    def _canonical(self, value: str) -> str:
        text = str(value or "").upper()
        replacements = {
            "PHARHACY": "PHARMACY",
            "PHARNACY": "PHARMACY",
            "PLYNQUTH": "PLYMOUTH",
        }
        for wrong, right in replacements.items():
            text = text.replace(wrong, right)
        return re.sub(r"[^A-Z0-9 ]+", " ", text)

    def _looks_like_header_merchant(self, line: str) -> bool:
        upper = line.upper()
        return (
            bool(re.search(r"[A-Za-z]{3,}", line))
            and not re.fullmatch(r"[A-Za-z]{3,4}", upper)
            and not re.search(r"\d{4,}", line)
            and not re.search(r"\d{1,7}(?:[.,]\d{2})", line)
            and not re.search(r"[®™©]", line)
            and not self._looks_like_policy_or_footer_text(upper)
            and not self.RECEIPT_NOISE.search(upper)
            and not any(term in upper for term in LEGAL_DISCLAIMER_TERMS)
        )

    def _looks_like_policy_or_footer_text(self, upper: str) -> bool:
        canonical = re.sub(r"[^A-Z]+", " ", upper)
        canonical = re.sub(r"\s+", " ", canonical).strip()
        footer_patterns = (
            r"\bR[ET]{1,2}\s+U[LIT]{2,4}\s+R[E]{1,3}C[EI]{1,3}L?PT\b",
            r"\bR[E]{1,3}C[EI]{1,3}L?PT\b.*\bSUB(?:J|L)ECT\b",
            r"\bRETURN\s+POLIC[UY]\b",
            r"\bWITH\s+R[E]{1,3}C[EI]{1,3}L?PT\b",
            r"\bSUB(?:J|L)ECT\s+TO\b",
        )
        return any(re.search(pattern, canonical) for pattern in footer_patterns)

    def _ranked_raw_ocr_merchant(self, raw_text: str, candidate: str = "") -> str:
        lines = [_compact_text(line) for line in str(raw_text or "").splitlines() if _compact_text(line)]
        if not lines:
            return ""
        scored: list[dict[str, Any]] = []
        for index, line in enumerate(lines[:90]):
            if self._domain_merchant_from_line(line):
                return self._domain_merchant_from_line(line)
            if not self._looks_like_header_merchant(line):
                continue
            if self._looks_like_ocr_filler(line):
                continue
            if self._looks_like_generic_business_fragment(line):
                continue
            score, reasons = self._raw_merchant_line_score(lines, index)
            if score >= 0.68:
                scored.append({"line": line, "score": score, "index": index, "reasons": reasons})

        if not scored:
            return ""
        scored.sort(key=lambda item: (item["score"], -item["index"]), reverse=True)
        best = scored[0]
        return self._title_preserving_acronyms(self._clean_business_merchant(best["line"]))

    def _raw_merchant_line_score(self, lines: list[str], index: int) -> tuple[float, list[str]]:
        line = lines[index]
        upper = line.upper()
        reasons: list[str] = []
        score = 0.34
        if index <= 1:
            score += 0.2
            reasons.append("top_header")
        elif index <= 5:
            score += 0.12
            reasons.append("upper_header")
        elif index <= 18:
            score += 0.04
            reasons.append("header_repeat_window")
        else:
            score -= min(0.18, (index - 18) * 0.006)

        has_business_suffix = self._has_business_suffix(upper)
        if has_business_suffix:
            score += 0.28
            reasons.append("business_suffix")
        if self._near_address_or_phone(lines, index):
            score += 0.14
            reasons.append("near_address_or_phone")
        if self._line_has_repeat_support(lines, index):
            score += 0.16
            reasons.append("repeated_ocr_support")
        if re.search(r"\b(?:MARKET|PHARMACY|KITCHEN|CENTER|CENTERS|STORE|STORES)\b", upper):
            score += 0.08
            reasons.append("store_semantic")
        if self._followed_by_split_item_price(lines, index):
            score = min(score, 0.42)
            reasons.append("followed_by_item_price")
        if index > 8 and not (has_business_suffix or self._near_address_or_phone(lines, index) or self._line_has_repeat_support(lines, index)):
            score = min(score, 0.55)
            reasons.append("late_without_structural_support")
        return min(0.96, score), reasons

    def _has_business_suffix(self, upper: str) -> bool:
        normalized = re.sub(r"[^A-Z0-9 ]+", " ", upper)
        normalized = re.sub(r"\s+", " ", normalized).strip()
        if re.search(r"\b(?:LLC|L\s*L\s*C|LEC|LEE)\b\.?$", normalized):
            return True
        return any(re.search(rf"\b{re.escape(term)}\b", normalized) for term in self.BUSINESS_SUFFIX_TERMS)

    def _near_address_or_phone(self, lines: list[str], index: int) -> bool:
        window = lines[max(0, index - 2): min(len(lines), index + 5)]
        for line in window:
            upper = line.upper()
            if re.search(r"\(?\d{3,4}\)?[-\s)]*\d{3}[-\s]*\d{4}", line):
                return True
            if re.search(r"\b\d{2,6}\b", upper) and re.search(
                r"\b(?:ROAD|RD|STREET|ST|AVENUE|AVE|LAKE|NORTH|SOUTH|EAST|WEST|PLYMOUTH|PLYNQUTH|MN|MM)\b",
                upper,
            ):
                return True
        return False

    def _line_has_repeat_support(self, lines: list[str], index: int) -> bool:
        current = self._canonical_for_consensus(lines[index])
        if not current:
            return False
        support = 0
        for other_index, other in enumerate(lines[:100]):
            if other_index == index:
                continue
            other_key = self._canonical_for_consensus(other)
            if not other_key:
                continue
            if current in other_key or other_key in current:
                support += 1
                continue
            if self._similarity(current, other_key) >= 76:
                support += 1
        return support >= 1

    def _canonical_for_consensus(self, value: str) -> str:
        text = self._canonical(value)
        text = re.sub(r"\b(?:LEC|LEE)\b", "LLC", text)
        text = re.sub(r"\b(?:CENFERS|CRENSERS)\b", "CENTERS", text)
        text = re.sub(r"\s+", " ", text).strip()
        return text

    def _looks_like_ocr_filler(self, line: str) -> bool:
        tokens = re.findall(r"[A-Za-z0-9]+", line)
        if not tokens:
            return True
        if len(tokens) >= 4 and sum(1 for token in tokens if len(token) <= 2) / len(tokens) >= 0.75:
            return True
        letters = re.sub(r"[^A-Za-z]", "", line)
        if len(letters) >= 8:
            vowels = sum(1 for char in letters.lower() if char in "aeiou")
            if vowels == 0 or vowels / len(letters) < 0.16:
                return True
        return False

    def _looks_like_generic_business_fragment(self, line: str) -> bool:
        canonical = self._canonical_for_consensus(line)
        return bool(re.fullmatch(r"(?:HOME|STORE|RETAIL|PHARMACY)?\s*(?:CENTER|CENTERS|STORE|STORES|MARKET|MART)\s+(?:LLC|INC|LTD|CORP|CO)", canonical))

    def _clean_business_merchant(self, value: str) -> str:
        cleaned = _compact_text(value).strip(" -_[]")
        cleaned = re.sub(r"\b(?:LEC|LEE)\b\.?$", "LLC", cleaned, flags=re.IGNORECASE)
        cleaned = re.sub(r"\b(?:CENFERS|CRENSERS)\b", "CENTERS", cleaned, flags=re.IGNORECASE)
        cleaned = re.sub(r"\.\s+LLC\b", ", LLC", cleaned, flags=re.IGNORECASE)
        return _compact_text(cleaned)

    def _recover_acronym_merchant(self, raw_text: str) -> str:
        lines = [_compact_text(line) for line in str(raw_text or "").splitlines() if _compact_text(line)]
        combined = "\n".join(lines).upper()
        if not re.search(r"\bPHAR[HMN]?ACY\b|\bPHARMACY\b", combined):
            return ""
        if not re.search(r"\bRETURN\s+POLIC", combined):
            return ""
        for line in lines[:80]:
            for token in re.findall(r"\b[A-Za-z][A-Za-z0-9]{2,4}\b", line):
                normalized = token.upper().replace("5", "S").replace("U", "V").replace("1", "I")
                if normalized == "CVS":
                    return "CVS"
        return ""

    def _title_preserving_acronyms(self, value: str) -> str:
        words = []
        for word in value.split():
            parts = [part if part.isupper() else part.title() for part in word.split("/")]
            words.append("/".join(parts))
        return " ".join(words)


class ReceiptSemanticParser:
    def parse(self, lines: list[ReconstructedLine]) -> tuple[list[dict[str, Any]], dict[str, str]]:
        items: list[dict[str, Any]] = []
        facts: dict[str, str] = {}
        consumed: set[int] = set()
        for index, line in enumerate(lines):
            if index in consumed:
                continue
            text = _compact_text(line.text)
            upper = text.upper()
            amounts = re.findall(r"\d{1,5}(?:[.,]\d{2}|\s+\d{2})\b", text)
            if amounts:
                value = amounts[-1].replace(" ", ".").replace(",", ".")
                if "SUB" in upper and "TOTAL" in upper:
                    facts["subtotal"] = value
                    continue
                if "TAX" in upper:
                    facts["tax"] = value
                    continue
                if "TOTAL" in upper and "SUB" not in upper and not any(card in upper for card in ("VISA", "AMEX", "MASTERCARD", "DISCOVER")):
                    facts["total"] = value
                    continue
            item, consumed_indexes = self._parse_item_at(index, lines)
            if item:
                items.append(item)
                consumed.update(consumed_indexes)
        return self._dedupe_items(items), facts

    def _parse_item_at(self, index: int, lines: list[ReconstructedLine]) -> tuple[dict[str, Any] | None, set[int]]:
        current = _compact_text(lines[index].text)
        next_line = _compact_text(lines[index + 1].text) if index + 1 < len(lines) else ""
        following_line = _compact_text(lines[index + 2].text) if index + 2 < len(lines) else ""
        item = self._parse_item_line(current, next_line)
        if item:
            return item, {index}
        if self._looks_like_product_name(current) and self._looks_like_quantity(next_line) and self._looks_like_standalone_amount(following_line):
            amount_match = re.search(r"\d{1,5}(?:[.,]\d{2}|\s+\d{2})", following_line.replace("$", ""))
            if amount_match:
                name, qty = self._extract_name_qty(current)
                if self._valid_item_name(name):
                    amount = amount_match.group(0).replace(" ", ".").replace(",", ".")
                    return {"name": name, "qty": qty or next_line, "count": qty or next_line, "amount": amount, "price": amount, "weight": 0.86}, {index, index + 1, index + 2}
        return None, set()

    def _parse_item_line(self, text: str, next_line: str = "") -> dict[str, Any] | None:
        upper = text.upper()
        if any(term in upper for term in RECEIPT_LEVEL_TERMS) or self._near_receipt_level_term(upper):
            return None
        if self._looks_like_survey_or_barcode(upper):
            return None
        normalized_text = text.replace("$", "")
        match = re.search(r"(?P<name>.+?)\s+(?P<amount>\d{1,5}(?:[.,]\d{2}|\s+\d{2}))\s*[^0-9]*$", normalized_text)
        if not match and re.fullmatch(r"\d{1,5}(?:[.,]\d{2}|\s+\d{2})\s*", next_line.replace("$", "")):
            amount_match = re.search(r"\d{1,5}(?:[.,]\d{2}|\s+\d{2})", next_line.replace("$", ""))
            if amount_match:
                match = {"name": text, "amount": amount_match.group(0)}
        if not match:
            return None
        raw_name = match["name"] if isinstance(match, dict) else match.group("name")
        raw_amount = match["amount"] if isinstance(match, dict) else match.group("amount")
        qty_from_price_pattern = self._extract_quantity_from_price_pattern(normalized_text)
        name, qty = self._extract_name_qty(raw_name)
        if qty_from_price_pattern:
            qty = qty_from_price_pattern
        amount = raw_amount.replace(" ", ".").replace(",", ".")
        if not self._valid_item_name(name):
            return None
        return {"name": name, "qty": qty, "count": qty, "amount": amount, "price": amount, "weight": 1.0}

    def _valid_item_name(self, name: str) -> bool:
        upper = _compact_text(name).upper()
        if len(upper) < 3 or not re.search(r"[A-Za-z]{3,}", upper):
            return False
        if re.fullmatch(r"\d{3,}", upper):
            return False
        if self._near_receipt_level_term(upper):
            return False
        tokens = re.findall(r"[A-Z0-9]+", upper)
        alpha_tokens = [token for token in tokens if re.search(r"[A-Z]{3,}", token)]
        if len(alpha_tokens) == 0:
            return False
        return True

    def _looks_like_product_name(self, text: str) -> bool:
        upper = _compact_text(text).upper()
        if any(term in upper for term in RECEIPT_LEVEL_TERMS) or self._near_receipt_level_term(upper):
            return False
        return bool(re.search(r"[A-Za-z]{3,}", upper)) and not self._looks_like_survey_or_barcode(upper)

    def _looks_like_quantity(self, text: str) -> bool:
        return bool(re.fullmatch(r"\d{1,3}(?:[.,]\d+)?", _compact_text(text)))

    def _looks_like_standalone_amount(self, text: str) -> bool:
        return bool(re.fullmatch(r"\$?\s*\d{1,5}(?:[.,]\d{2}|\s+\d{2})\s*[A-Z]?", _compact_text(text), flags=re.IGNORECASE))

    def _looks_like_survey_or_barcode(self, upper: str) -> bool:
        if any(token in upper for token in ("SURVEY", "BARCODE", "COUPON", "REWARD", "RECEIPT ID")):
            return True
        digits = re.sub(r"\D", "", upper)
        return len(digits) >= 8 and not re.search(r"\d{1,5}[.,]\d{2}", upper)

    def _near_receipt_level_term(self, upper: str) -> bool:
        token = re.sub(r"[^A-Z]", "", upper.split()[0] if upper.split() else "")
        if len(token) < 4:
            return False
        if token in RECEIPT_LEVEL_OCR_MUTATIONS:
            return True
        targets = ("TOTAL", "SUBTOTAL", "CHARGE", "PAYMENT", "CHANGE", "VISA", "CARD", "AUTH", "CASH")
        if fuzz is not None:
            return any(fuzz.ratio(token, target) >= 72 for target in targets)
        return token in targets or any(self._one_edit_apart(token, target) for target in targets)

    def _one_edit_apart(self, left: str, right: str) -> bool:
        if abs(len(left) - len(right)) > 1:
            return False
        if len(left) == len(right):
            return sum(1 for a, b in zip(left, right) if a != b) <= 1
        short, long = (left, right) if len(left) < len(right) else (right, left)
        for index in range(len(long)):
            if long[:index] + long[index + 1:] == short:
                return True
        return False

    def _extract_quantity_from_price_pattern(self, value: str) -> str:
        patterns = [
            r"\b(?P<qty>\d{1,3})\s*(?:@|X|x)\s*\d{1,5}(?:[.,]\d{2})\b",
            r"\b(?P<qty>\d{1,3})\s+EA\b",
            r"\bQTY\s*(?P<qty>\d{1,3})\b",
        ]
        for pattern in patterns:
            match = re.search(pattern, value, flags=re.IGNORECASE)
            if match:
                return match.group("qty")
        return ""

    def _extract_name_qty(self, value: str) -> tuple[str, str]:
        text = _compact_text(value).strip(" -_:;")
        quantity_prefix = re.match(
            r"^(?P<qty>\d{1,3}(?:[.,]\d+)?)\s*(?:(?:EA|QTY)\s+|(?:@|X|x)\s*\d{1,5}(?:[.,]\d{2})\s+)?(?P<name>[A-Za-z][A-Za-z0-9&'. /-].*)$",
            text,
            flags=re.IGNORECASE,
        )
        if quantity_prefix:
            return self._clean_item_name(quantity_prefix.group("name")), quantity_prefix.group("qty").replace(",", ".")
        leading = re.match(r"^(?P<qty>\d{1,3}(?:[.,]\d+)?)\s+(?P<name>[A-Za-z][A-Za-z0-9&'. /-].*)$", text)
        if leading and len(leading.group("qty")) <= 3:
            return self._clean_item_name(leading.group("name")), leading.group("qty").replace(",", ".")
        return self._clean_item_name(text), "1"

    def _clean_item_name(self, name: str) -> str:
        cleaned = re.sub(r"\b\d{5,12}\b\s*[A-Z]?\s*$", "", _compact_text(name)).strip(" -_:;")
        cleaned = re.sub(r"^\b(?:EA|QTY)\b\s+", "", cleaned, flags=re.IGNORECASE)
        cleaned = re.sub(r"\b\d{1,3}\s*(?:@|X|x)\s*\d{1,5}(?:[.,]\d{2})\b", "", cleaned).strip(" -_:;")
        replacements = {
            "S-TIER": "5-TIER",
            "STIER": "5-TIER",
            "SHELUIN": "SHELVING",
            "SHELVIN": "SHELVING",
            "CUSTOM TEM": "CUSTOM ITEM",
            "CUSTOM LTEM": "CUSTOM ITEM",
        }
        for wrong, right in replacements.items():
            cleaned = re.sub(rf"\b{wrong}\b", right, cleaned, flags=re.IGNORECASE)
        return _compact_text(cleaned)

    def _dedupe_items(self, items: list[dict[str, Any]]) -> list[dict[str, Any]]:
        clusters: list[list[dict[str, Any]]] = []
        for item in items:
            target = None
            item_key = self._item_key(item.get("name", ""))
            for cluster in clusters:
                representative = cluster[0]
                same_price = str(representative.get("amount")) == str(item.get("amount"))
                if same_price and self._similar_item_name(item_key, self._item_key(representative.get("name", ""))):
                    target = cluster
                    break
            if target is None:
                clusters.append([item])
            else:
                target.append(item)
        output = []
        for cluster in clusters:
            best = max(cluster, key=lambda item: (float(item.get("weight", 1.0) or 1.0), len(str(item.get("name", "")))))
            output.append(best)
        return [{**item, "id": index + 1} for index, item in enumerate(output)]

    def _item_key(self, name: str) -> str:
        key = re.sub(r"[^A-Z0-9 ]+", " ", str(name or "").upper())
        key = re.sub(r"\b\d{1,4}\b", " ", key)
        key = re.sub(r"\b(?:EA|QTY)\b", " ", key)
        return _compact_text(key)

    def _similar_item_name(self, left: str, right: str) -> bool:
        if not left or not right:
            return False
        if fuzz is not None:
            return fuzz.token_set_ratio(left, right) >= 74 or fuzz.ratio(left, right) >= 74
        left_tokens = set(left.split())
        right_tokens = set(right.split())
        return bool(left_tokens and right_tokens and len(left_tokens & right_tokens) / len(left_tokens | right_tokens) >= 0.5)


class ReceiptSpatialClusterer:
    """Groups reconstructed OCR rows into spatial regions for layout reasoning."""

    def cluster(self, lines: list[ReconstructedLine]) -> list[OCRRegion]:
        if not lines:
            return []
        ordered = sorted(enumerate(lines), key=lambda pair: (pair[1].page, pair[1].y))
        median_height = self._median([line.height for _, line in ordered if line.height > 0]) or 14.0
        gap_tolerance = max(18.0, median_height * 1.8)
        regions: list[list[tuple[int, ReconstructedLine]]] = []
        for indexed_line in ordered:
            if not regions:
                regions.append([indexed_line])
                continue
            previous = regions[-1][-1][1]
            line = indexed_line[1]
            page_changed = line.page != previous.page
            vertical_gap = (line.y - previous.y) > gap_tolerance
            semantic_break = self._is_semantic_boundary(previous.text, line.text)
            if page_changed or vertical_gap or semantic_break:
                regions.append([indexed_line])
            else:
                regions[-1].append(indexed_line)

        return [self._to_region(index, group) for index, group in enumerate(regions) if group]

    def _to_region(self, index: int, group: list[tuple[int, ReconstructedLine]]) -> OCRRegion:
        lines = [line for _, line in group]
        page = lines[0].page
        left = min(line.x for line in lines)
        top = min(line.y for line in lines)
        right = max(line.x + line.width for line in lines)
        bottom = max(line.y + line.height for line in lines)
        text = "\n".join(line.text for line in lines)
        confidence = sum(line.confidence for line in lines) / max(len(lines), 1)
        return OCRRegion(
            id=f"region-{index + 1}",
            kind=self._classify_region(text, index),
            text=text,
            page=page,
            x=left,
            y=top,
            width=max(0.0, right - left),
            height=max(0.0, bottom - top),
            confidence=confidence,
            line_indexes=[line_index for line_index, _ in group],
        )

    def _classify_region(self, text: str, index: int) -> str:
        upper = text.upper()
        if index == 0:
            return "header"
        if re.search(r"\bSUB\s*TOTAL\b|\bSUBTOTAL\b|\bTOTAL\b|\bTAX\b|\bTIP\b", upper):
            return "totals"
        if any(term in upper for term in ("VISA", "MASTERCARD", "AMEX", "DISCOVER", "CASH", "CREDIT", "DEBIT", "AUTH", "APPROVED")):
            return "payment"
        if any(term in upper for term in ("THANK", "SURVEY", "FEEDBACK", "RETURN POLICY")):
            return "footer"
        if re.search(r"[A-Za-z]{3,}.*\d{1,5}(?:[., ]\d{2})", text):
            return "items"
        return "unknown"

    def _is_semantic_boundary(self, previous: str, current: str) -> bool:
        previous_upper = previous.upper()
        current_upper = current.upper()
        if re.search(r"\bSUB\s*TOTAL\b|\bSUBTOTAL\b", current_upper):
            return True
        if any(term in current_upper for term in ("VISA", "MASTERCARD", "AMEX", "DISCOVER", "CASH", "CREDIT", "DEBIT")):
            return True
        if any(term in current_upper for term in ("THANK", "SURVEY", "FEEDBACK")) and "TOTAL" in previous_upper:
            return True
        return False

    def _median(self, values: list[float]) -> float:
        if not values:
            return 0
        sorted_values = sorted(values)
        return sorted_values[len(sorted_values) // 2]


class ReceiptSemanticBlockBuilder:
    """Turns spatial rows into semantic receipt blocks before LLM reasoning."""

    def build(self, lines: list[ReconstructedLine], regions: list[OCRRegion]) -> list[SemanticBlock]:
        if not lines:
            return []
        line_to_region: dict[int, str] = {}
        for region in regions:
            for line_index in region.line_indexes:
                line_to_region[line_index] = region.id

        blocks: list[SemanticBlock] = []
        current_kind = ""
        current_indexes: list[int] = []
        for index, line in enumerate(lines):
            kind = self._classify_line(index, line, lines)
            if current_indexes and kind != current_kind:
                blocks.append(self._make_block(len(blocks), current_kind, current_indexes, lines, line_to_region))
                current_indexes = []
            current_kind = kind
            current_indexes.append(index)
        if current_indexes:
            blocks.append(self._make_block(len(blocks), current_kind, current_indexes, lines, line_to_region))
        return blocks

    def _classify_line(self, index: int, line: ReconstructedLine, lines: list[ReconstructedLine]) -> str:
        text = line.text
        upper = text.upper()
        if index <= 3 and re.search(r"[A-Za-z]{3,}", text) and not re.search(r"\d{1,5}(?:[., ]\d{2})", text):
            return "merchant"
        if re.search(r"\bSUB\s*TOTAL\b|\bSUBTOTAL\b|\bTOTAL\b|\bTAX\b|\bTIP\b|\bCHANGE\b", upper):
            return "totals"
        if any(term in upper for term in ("VISA", "MASTERCARD", "AMEX", "DISCOVER", "CASH", "CREDIT", "DEBIT", "AUTH", "APPROVED")):
            return "payment"
        if any(term in upper for term in ("THANK", "SURVEY", "FEEDBACK", "RETURN POLICY", "COME AGAIN")):
            return "footer"
        if re.search(r"[A-Za-z]{3,}", text) and re.search(r"\d{1,5}(?:[., ]\d{2})\b", text):
            return "items"
        if index < 6:
            return "header"
        return "unknown"

    def _make_block(
        self,
        index: int,
        kind: str,
        line_indexes: list[int],
        lines: list[ReconstructedLine],
        line_to_region: dict[int, str],
    ) -> SemanticBlock:
        selected = [lines[line_index] for line_index in line_indexes]
        confidence = sum(line.confidence for line in selected) / max(len(selected), 1)
        region_ids = sorted({line_to_region[line_index] for line_index in line_indexes if line_index in line_to_region})
        return SemanticBlock(
            id=f"block-{index + 1}",
            kind=kind,
            text="\n".join(line.text for line in selected),
            confidence=confidence,
            line_indexes=line_indexes,
            region_ids=region_ids,
        )


class ReceiptTableReconstructor:
    """Builds item and total tables from parsed rows plus line references."""

    RETAIL_PRICE_PATTERN = re.compile(
        r"(?P<qty>\d{1,3}(?:[.,]\d+)?)\s*(?:@|X|x)\s*(?P<unit>\d{1,5}(?:[.,]\d{2}))",
        flags=re.IGNORECASE,
    )

    def extract_retail_multiline_items(self, lines: list[ReconstructedLine]) -> tuple[list[dict[str, Any]], dict[str, Any]]:
        diagnostics: dict[str, Any] = {
            "schemaVersion": "receipt-retail-row-reconstruction-v1",
            "strategy": "multi_line_geometry_price_pattern_graph",
            "rows": [],
            "pendingRows": [],
            "mergedRows": [],
            "arithmeticTraces": [],
            "rowGraph": {"nodes": [], "edges": []},
            "visualization": [],
        }
        if not lines:
            diagnostics["reason"] = "no_lines"
            return [], diagnostics

        median_gap = self._median_vertical_gap(lines)
        items: list[dict[str, Any]] = []
        pending: dict[str, Any] | None = None
        last_item: dict[str, Any] | None = None
        item_section_seen = False

        for index, line in enumerate(lines):
            text = _compact_text(line.text)
            upper = text.upper()
            if not text:
                continue
            if self._is_retail_item_section_marker(upper):
                item_section_seen = True
                if pending:
                    diagnostics["pendingRows"].append(self._pending_diagnostic(pending, "closed_by_item_section_marker"))
                    pending = None
                diagnostics["rows"].append(self._retail_row_diag(index, line, "item_section_marker"))
                continue
            if self._is_totals_or_payment_row(upper):
                if pending:
                    diagnostics["pendingRows"].append(self._pending_diagnostic(pending, "closed_by_totals_or_payment"))
                    pending = None
                diagnostics["rows"].append(self._retail_row_diag(index, line, "table_boundary"))
                continue

            pricing = self._retail_pricing_payload(text)
            if pricing:
                target = pending if pending and self._can_attach_pricing_line(pending, line, median_gap) else None
                if target:
                    item = self._merged_retail_item(target, line, index, pricing, len(items) + 1)
                    items.append(item)
                    last_item = item
                    pending = None
                    diagnostics["rows"].append(self._retail_row_diag(index, line, "pricing_line", parent=item["id"]))
                    diagnostics["mergedRows"].append(self._merged_row_trace(item, pricing))
                    diagnostics["arithmeticTraces"].append(item["confidenceTrace"]["arithmetic"])
                    self._add_row_graph(diagnostics["rowGraph"], item)
                    continue
                inline_name = self._inline_name_from_pricing_text(text)
                if inline_name and self._valid_item_name(inline_name):
                    synthetic_pending = {"lineIndexes": [index], "lines": [line], "text": inline_name, "x": line.x, "y": line.y}
                    item = self._merged_retail_item(synthetic_pending, line, index, pricing, len(items) + 1)
                    items.append(item)
                    last_item = item
                    diagnostics["rows"].append(self._retail_row_diag(index, line, "inline_item_pricing", parent=item["id"]))
                    diagnostics["mergedRows"].append(self._merged_row_trace(item, pricing))
                    diagnostics["arithmeticTraces"].append(item["confidenceTrace"]["arithmetic"])
                    self._add_row_graph(diagnostics["rowGraph"], item)
                    continue
                diagnostics["rows"].append(self._retail_row_diag(index, line, "orphan_pricing_line", reason="missing_description_parent"))
                continue

            if self._looks_like_modifier_line(text) and last_item and self._line_vertical_gap(last_item.get("lineIndexes", [])[-1], index, lines) <= max(36.0, median_gap * 2.4):
                last_item.setdefault("modifierLines", []).append(text)
                last_item.setdefault("lineIndexes", []).append(index)
                diagnostics["rows"].append(self._retail_row_diag(index, line, "modifier_line", parent=last_item["id"]))
                diagnostics["rowGraph"]["nodes"].append({"id": f"line-{index}", "type": "modifier_line", "text": text})
                diagnostics["rowGraph"]["edges"].append({"from": f"item-{last_item['id']}", "to": f"line-{index}", "type": "HAS_MODIFIER_LINE"})
                continue

            if self._retail_description_candidate(text):
                if not item_section_seen and not self._next_line_has_retail_pricing(lines, index):
                    diagnostics["rows"].append(self._retail_row_diag(index, line, "ignored_header_description_candidate", reason="before_item_section_without_pricing_neighbor"))
                    continue
                if pending:
                    if self._can_attach_description_line(pending, line, median_gap):
                        pending["lineIndexes"].append(index)
                        pending["lines"].append(line)
                        pending["text"] = _compact_text(f"{pending['text']} {text}")
                        diagnostics["rows"].append(self._retail_row_diag(index, line, "continued_description", parent=f"pending-{pending['lineIndexes'][0]}"))
                    else:
                        diagnostics["pendingRows"].append(self._pending_diagnostic(pending, "superseded_by_new_description"))
                        pending = {"lineIndexes": [index], "lines": [line], "text": text, "x": line.x, "y": line.y}
                        diagnostics["rows"].append(self._retail_row_diag(index, line, "pending_description"))
                else:
                    pending = {"lineIndexes": [index], "lines": [line], "text": text, "x": line.x, "y": line.y}
                    diagnostics["rows"].append(self._retail_row_diag(index, line, "pending_description"))
                continue

            diagnostics["rows"].append(self._retail_row_diag(index, line, "ignored"))

        if pending:
            diagnostics["pendingRows"].append(self._pending_diagnostic(pending, "no_following_pricing_line"))

        diagnostics["visualization"] = self._row_stitching_visualization(diagnostics["rows"])
        return self._dedupe_aligned_items(items), diagnostics

    def extract_aligned_items(self, lines: list[ReconstructedLine]) -> tuple[list[dict[str, Any]], dict[str, Any]]:
        diagnostics: dict[str, Any] = {
            "schemaVersion": "receipt-aligned-table-reconstruction-v1",
            "strategy": "ocr_box_alignment",
            "rows": [],
            "rejectedRows": [],
            "columnAnchors": {},
        }
        boxed_lines = [(index, line) for index, line in enumerate(lines) if line.boxes]
        if not boxed_lines:
            diagnostics["reason"] = "no_ocr_boxes"
            return [], diagnostics

        amount_centers = [
            box.x + box.width / 2
            for _, line in boxed_lines
            for box in line.boxes
            if self._is_money_token(box.text)
        ]
        if not amount_centers:
            diagnostics["reason"] = "no_money_column"
            return [], diagnostics
        amount_anchor = self._median(amount_centers)
        left_edges = [box.x for _, line in boxed_lines for box in line.boxes if box.text.strip()]
        right_edges = [box.x + box.width for _, line in boxed_lines for box in line.boxes if box.text.strip()]
        page_left = min(left_edges) if left_edges else 0.0
        page_right = max(right_edges) if right_edges else amount_anchor
        diagnostics["columnAnchors"] = {
            "pageLeft": round(page_left, 2),
            "amountCenter": round(amount_anchor, 2),
            "pageRight": round(page_right, 2),
        }

        items: list[dict[str, Any]] = []
        in_item_table = False
        for line_index, line in boxed_lines:
            text = _compact_text(line.text)
            upper = text.upper()
            if self._is_table_header(upper):
                in_item_table = True
                diagnostics["rows"].append({"lineIndex": line_index, "text": text, "role": "table_header"})
                continue
            if self._is_totals_or_payment_row(upper):
                if in_item_table:
                    diagnostics["rows"].append({"lineIndex": line_index, "text": text, "role": "table_boundary"})
                in_item_table = False
                continue
            row = self._aligned_item_row(line_index, line, amount_anchor, page_left, page_right, in_item_table)
            if row.get("item"):
                items.append(row["item"])
                diagnostics["rows"].append(row["diagnostic"])
                in_item_table = True
            elif row.get("diagnostic"):
                diagnostics["rejectedRows"].append(row["diagnostic"])
        return self._dedupe_aligned_items(items), diagnostics

    def reconstruct(self, lines: list[ReconstructedLine], items: list[dict[str, Any]], facts: dict[str, str]) -> list[dict[str, Any]]:
        tables: list[dict[str, Any]] = []
        aligned_items, alignment = self.extract_aligned_items(lines)
        if items:
            tables.append({
                "id": "items-table",
                "kind": "items",
                "headers": ["qty", "name", "unitPrice", "amount"],
                "confidence": round(sum(line.confidence for line in lines) / max(len(lines), 1), 3),
                "reconstruction": alignment,
                "rows": [
                    {
                        "lineIndex": self._find_line_index(lines, item.get("name", ""), item.get("amount", "")),
                        "name": item.get("name", ""),
                        "qty": item.get("qty") or item.get("count") or "1",
                        "unitPrice": self._unit_price(item.get("qty") or item.get("count") or "1", item.get("amount") or item.get("price") or ""),
                        "amount": item.get("amount") or item.get("price") or "",
                        "confidence": round(float(item.get("confidence", item.get("weight", 1.0)) or 1.0), 3),
                    }
                    for item in items
                ],
            })
        elif aligned_items:
            tables.append({
                "id": "items-table",
                "kind": "items",
                "headers": ["qty", "name", "unitPrice", "amount"],
                "confidence": round(sum(float(item.get("confidence", item.get("weight", 0.0)) or 0.0) for item in aligned_items) / max(len(aligned_items), 1), 3),
                "reconstruction": alignment,
                "rows": [
                    {
                        "lineIndex": item.get("lineIndex"),
                        "name": item.get("name", ""),
                        "qty": item.get("qty") or item.get("count") or "1",
                        "unitPrice": self._unit_price(item.get("qty") or item.get("count") or "1", item.get("amount") or item.get("price") or ""),
                        "amount": item.get("amount") or item.get("price") or "",
                        "confidence": round(float(item.get("confidence", item.get("weight", 1.0)) or 1.0), 3),
                    }
                    for item in aligned_items
                ],
            })
        totals = [{"label": key, "amount": value} for key, value in facts.items() if value]
        if totals:
            tables.append({
                "id": "totals-table",
                "kind": "totals",
                "headers": ["label", "amount"],
                "confidence": 0.9,
                "rows": totals,
            })
        return tables

    def _retail_pricing_payload(self, text: str) -> dict[str, Any] | None:
        normalized = text.replace("$", "").replace(",", ".")
        match = self.RETAIL_PRICE_PATTERN.search(normalized)
        if not match:
            return None
        amounts = re.findall(r"\d{1,5}(?:[.,]\d{2})\b", normalized)
        if not amounts:
            return None
        qty = match.group("qty").replace(",", ".")
        unit_price = match.group("unit").replace(",", ".")
        trailing_amounts = re.findall(r"\d{1,5}(?:[.,]\d{2})\b", normalized[match.end():])
        if trailing_amounts:
            extended = trailing_amounts[-1].replace(",", ".")
        else:
            extended = f"{float(qty) * float(unit_price):.2f}"
        arithmetic_delta = abs((float(qty) * float(unit_price)) - float(extended))
        return {
            "qty": qty,
            "unitPrice": unit_price,
            "extendedPrice": extended,
            "amount": extended,
            "pattern": match.group(0),
            "arithmeticDelta": round(arithmetic_delta, 3),
            "arithmeticValid": arithmetic_delta <= max(0.03, float(extended) * 0.01),
        }

    def _merged_retail_item(
        self,
        pending: dict[str, Any],
        pricing_line: ReconstructedLine,
        pricing_index: int,
        pricing: dict[str, Any],
        item_id: int,
    ) -> dict[str, Any]:
        description_lines = pending.get("lines") or []
        all_lines = [*description_lines, pricing_line]
        line_indexes = [*pending.get("lineIndexes", []), pricing_index]
        raw_description = str(pending.get("text") or "")
        sku_match = re.search(r"\b(?P<sku>\d{8,16})\b", raw_description)
        sku = sku_match.group("sku") if sku_match else ""
        name = self._clean_retail_description_name(raw_description)
        arithmetic_bonus = 0.16 if pricing["arithmeticValid"] else -0.18
        geometry_bonus = 0.10 if description_lines and self._pricing_line_aligned(pending, pricing_line) else 0.02
        confidence = min(0.99, max(0.55, (sum(line.confidence for line in all_lines) / max(len(all_lines), 1)) * 0.72 + arithmetic_bonus + geometry_bonus))
        left = min((line.x for line in all_lines), default=0.0)
        top = min((line.y for line in all_lines), default=0.0)
        right = max((line.x + line.width for line in all_lines), default=0.0)
        bottom = max((line.y + line.height for line in all_lines), default=0.0)
        return {
            "id": item_id,
            "name": name,
            "qty": pricing["qty"],
            "count": pricing["qty"],
            "unitPrice": pricing["unitPrice"],
            "extendedPrice": pricing["extendedPrice"],
            **({"sku": sku} if sku else {}),
            "amount": pricing["extendedPrice"],
            "price": pricing["extendedPrice"],
            "weight": round(confidence, 3),
            "confidence": round(confidence, 3),
            "lineIndex": line_indexes[0] if line_indexes else pricing_index,
            "lineIndexes": line_indexes,
            "descriptionLineIndexes": pending.get("lineIndexes", []),
            "pricingLineIndex": pricing_index,
            "source": "retail_multiline_row_assembly",
            "bbox": {
                "x": round(left, 2),
                "y": round(top, 2),
                "width": round(max(0.0, right - left), 2),
                "height": round(max(0.0, bottom - top), 2),
            },
            "confidenceTrace": {
                "source": "retail_multiline_row_assembly",
                "descriptionLines": pending.get("lineIndexes", []),
                "pricingLine": pricing_index,
                "pricingPattern": pricing["pattern"],
                "geometry": {
                    "verticalProximity": True,
                    "pricingIndentedOrAligned": self._pricing_line_aligned(pending, pricing_line),
                },
                "arithmetic": {
                    "qty": pricing["qty"],
                    "unitPrice": pricing["unitPrice"],
                    "extendedPrice": pricing["extendedPrice"],
                    "calculatedExtendedPrice": f"{float(pricing['qty']) * float(pricing['unitPrice']):.2f}",
                    "delta": pricing["arithmeticDelta"],
                    "valid": pricing["arithmeticValid"],
                },
            },
        }

    def _inline_name_from_pricing_text(self, text: str) -> str:
        before = self.RETAIL_PRICE_PATTERN.split(text.replace("$", ""))[0] if self.RETAIL_PRICE_PATTERN.search(text.replace("$", "")) else ""
        before = re.sub(r"\b(?:REG|SALE|WAS|NOW|PRICE)\b\s*\d{1,5}(?:[.,]\d{2})?", "", before, flags=re.IGNORECASE)
        return self._clean_aligned_name(before)

    def _clean_retail_description_name(self, value: str) -> str:
        cleaned = re.sub(r"\b\d{8,16}\b(?:\W*\d{1,2})?(?:\W*[A-Za-z]{1,3})?", "", _compact_text(value)).strip(" -_:;")
        return self._clean_aligned_name(cleaned)

    def _retail_description_candidate(self, text: str) -> bool:
        upper = _compact_text(text).upper()
        if self._is_totals_or_payment_row(upper) or self._is_table_header(upper):
            return False
        if re.search(r"\b(?:YOU\s+SAVED|PURCHASE\s+SUMMARY|ACCOUNT\s+NUMBER|APPROVAL|APPLICATION|AID|TVR|TSI)\b", upper):
            return False
        if self._is_retail_item_section_marker(upper) or self._looks_like_header_metadata_line(upper):
            return False
        if self._retail_pricing_payload(text):
            return False
        if re.search(r"\d{1,5}(?:[.,]\d{2}|\s+\d{2})\b", text):
            return False
        return self._valid_item_name(text)

    def _is_retail_item_section_marker(self, upper: str) -> bool:
        return bool(re.search(r"\b(?:ITEM\s+INFORMATION|TEM\s+INFORMATION|ITEMS?|DESCRIPTION|MERCHANDISE)\b", upper)) and not re.search(r"\d{1,5}(?:[.,]\d{2})", upper)

    def _looks_like_header_metadata_line(self, upper: str) -> bool:
        return bool(
            re.search(r"\b(?:ORDER|ORD|SALE|STORE|REGISTER|REG\s*#|CASHIER|TRANS|TRANSACTION|PHONE|TEL)\b", upper)
            or re.search(r"(?:\(\d{3}\)|\b\d{3})[-\s)]+\d{3}[-\s]+\d{4}\b", upper)
            or re.search(r"\b\d{1,6}\s+[A-Z0-9 .'-]*(?:ST|STREET|AVE|AVENUE|RD|ROAD|LN|LANE|NORTH|SOUTH|EAST|WEST|PLYMOUTH|MN)\b", upper)
            or re.search(r"\b\d{1,2}/\d{1,2}/\d{2,4}\b", upper)
            or bool(len(re.sub(r"\D", "", upper)) >= 10 and not re.search(r"[A-Z]{3,}", upper))
        )

    def _next_line_has_retail_pricing(self, lines: list[ReconstructedLine], index: int) -> bool:
        for next_line in lines[index + 1: min(len(lines), index + 3)]:
            if self._retail_pricing_payload(next_line.text):
                return True
        return False

    def _looks_like_modifier_line(self, text: str) -> bool:
        upper = _compact_text(text).upper()
        if self._retail_description_candidate(text):
            return False
        return bool(re.search(r"\b(?:REG|SALE|WAS|NOW|DISC|DISCOUNT|COUPON|COLOR|SIZE|STYLE|SKU)\b", upper)) and not self._is_totals_or_payment_row(upper)

    def _can_attach_pricing_line(self, pending: dict[str, Any], pricing_line: ReconstructedLine, median_gap: float) -> bool:
        previous = (pending.get("lines") or [])[-1] if pending.get("lines") else None
        if previous is None:
            return False
        vertical_gap = pricing_line.y - previous.y
        if vertical_gap < -2:
            return False
        if vertical_gap > max(42.0, median_gap * 2.6):
            return False
        return pricing_line.x >= previous.x - 18 or abs(pricing_line.x - previous.x) <= 36

    def _can_attach_description_line(self, pending: dict[str, Any], line: ReconstructedLine, median_gap: float) -> bool:
        previous = (pending.get("lines") or [])[-1] if pending.get("lines") else None
        if previous is None:
            return False
        vertical_gap = line.y - previous.y
        return 0 <= vertical_gap <= max(34.0, median_gap * 2.2) and abs(line.x - previous.x) <= 60

    def _pricing_line_aligned(self, pending: dict[str, Any], pricing_line: ReconstructedLine) -> bool:
        previous = (pending.get("lines") or [])[-1] if pending.get("lines") else None
        if previous is None:
            return False
        return pricing_line.x >= previous.x - 18 or abs(pricing_line.x - previous.x) <= 36

    def _median_vertical_gap(self, lines: list[ReconstructedLine]) -> float:
        positions = sorted(line.y for line in lines)
        gaps = [positions[index + 1] - positions[index] for index in range(len(positions) - 1) if positions[index + 1] >= positions[index]]
        gaps = [gap for gap in gaps if gap > 0]
        return self._median(gaps) or 16.0

    def _line_vertical_gap(self, previous_index: int, current_index: int, lines: list[ReconstructedLine]) -> float:
        if previous_index < 0 or current_index < 0 or previous_index >= len(lines) or current_index >= len(lines):
            return 999.0
        return lines[current_index].y - lines[previous_index].y

    def _retail_row_diag(self, index: int, line: ReconstructedLine, role: str, parent: Any = None, reason: str = "") -> dict[str, Any]:
        diagnostic = {
            "lineIndex": index,
            "text": line.text,
            "role": role,
            "bbox": {"x": round(line.x, 2), "y": round(line.y, 2), "width": round(line.width, 2), "height": round(line.height, 2)},
        }
        if parent is not None:
            diagnostic["parent"] = parent
        if reason:
            diagnostic["reason"] = reason
        return diagnostic

    def _pending_diagnostic(self, pending: dict[str, Any], reason: str) -> dict[str, Any]:
        return {
            "lineIndexes": pending.get("lineIndexes", []),
            "text": pending.get("text", ""),
            "reason": reason,
        }

    def _merged_row_trace(self, item: dict[str, Any], pricing: dict[str, Any]) -> dict[str, Any]:
        return {
            "itemId": item["id"],
            "name": item["name"],
            "descriptionLineIndexes": item.get("descriptionLineIndexes", []),
            "pricingLineIndex": item.get("pricingLineIndex"),
            "qty": pricing["qty"],
            "unitPrice": pricing["unitPrice"],
            "extendedPrice": pricing["extendedPrice"],
            "arithmeticValid": pricing["arithmeticValid"],
        }

    def _add_row_graph(self, graph: dict[str, Any], item: dict[str, Any]) -> None:
        item_node = f"item-{item['id']}"
        graph["nodes"].append({"id": item_node, "type": "item", "name": item.get("name", "")})
        for line_index in item.get("descriptionLineIndexes", []):
            line_node = f"line-{line_index}"
            graph["nodes"].append({"id": line_node, "type": "description_line"})
            graph["edges"].append({"from": item_node, "to": line_node, "type": "HAS_DESCRIPTION_LINE"})
        pricing_node = f"line-{item.get('pricingLineIndex')}"
        graph["nodes"].append({"id": pricing_node, "type": "pricing_line"})
        graph["edges"].append({"from": item_node, "to": pricing_node, "type": "HAS_PRICING_LINE"})

    def _row_stitching_visualization(self, rows: list[dict[str, Any]]) -> list[str]:
        output = []
        for row in rows:
            parent = f" -> {row['parent']}" if row.get("parent") is not None else ""
            output.append(f"{row.get('lineIndex')}: {row.get('role')}{parent} | {row.get('text')}")
        return output[:120]

    def _find_line_index(self, lines: list[ReconstructedLine], name: str, amount: str) -> int | None:
        name_key = re.sub(r"[^A-Z0-9]+", "", str(name or "").upper())
        amount_variants = {str(amount or ""), str(amount or "").replace(".", " "), str(amount or "").replace(".", ",")}
        for index, line in enumerate(lines):
            line_key = re.sub(r"[^A-Z0-9]+", "", line.text.upper())
            if name_key and name_key in line_key and any(variant and variant in line.text for variant in amount_variants):
                return index
        return None

    def _unit_price(self, qty: Any, amount: Any) -> str:
        try:
            quantity = float(str(qty or "1").replace(",", "."))
            total = float(str(amount or "").replace(",", "."))
        except ValueError:
            return str(amount or "")
        if quantity <= 0:
            return str(amount or "")
        return f"{total / quantity:.2f}"

    def _aligned_item_row(
        self,
        line_index: int,
        line: ReconstructedLine,
        amount_anchor: float,
        page_left: float,
        page_right: float,
        in_item_table: bool,
    ) -> dict[str, Any]:
        ordered = sorted(line.boxes, key=lambda box: box.x)
        money_boxes = [box for box in ordered if self._is_money_token(box.text)]
        text = _compact_text(line.text)
        if not money_boxes:
            return {"diagnostic": {"lineIndex": line_index, "text": text, "role": "rejected", "reason": "missing_price_column"}}
        amount_box = max(money_boxes, key=lambda box: (abs((box.x + box.width / 2) - amount_anchor) <= 55, box.x))
        amount_center = amount_box.x + amount_box.width / 2
        right_aligned_price = amount_center >= amount_anchor - 65 or amount_box.x >= page_left + (page_right - page_left) * 0.56
        name_boxes = [
            box for box in ordered
            if box is not amount_box
            and (box.x + box.width) <= amount_box.x + 4
            and not self._is_money_token(box.text)
            and not self._is_noise_token(box.text)
        ]
        qty_box = self._quantity_box(name_boxes)
        if qty_box:
            name_boxes = [box for box in name_boxes if box is not qty_box]
        name = _compact_text(" ".join(box.text for box in name_boxes if re.search(r"[A-Za-z]", box.text)))
        name = self._clean_aligned_name(name)
        amount = _amount(amount_box.text)
        reasons = []
        if not right_aligned_price:
            reasons.append("price_not_right_aligned")
        if not name:
            reasons.append("orphan_monetary_value")
        if self._is_totals_or_payment_row(text.upper()):
            reasons.append("totals_payment_footer_row")
        if name and not self._valid_item_name(name):
            reasons.append("invalid_item_name")
        if reasons:
            return {
                "diagnostic": {
                    "lineIndex": line_index,
                    "text": text,
                    "role": "rejected",
                    "reason": ",".join(reasons),
                    "amount": amount,
                    "amountColumnX": round(amount_center, 2),
                    "inItemTable": in_item_table,
                }
            }
        qty = _compact_text(qty_box.text if qty_box else "") or self._qty_from_name(name) or "1"
        if qty_box:
            name = self._clean_aligned_name(re.sub(rf"^\s*{re.escape(qty_box.text)}\s+", "", name))
        confidence = min(0.98, max(0.58, line.confidence * 0.72 + (0.16 if right_aligned_price else 0) + (0.1 if qty_box else 0)))
        item = {
            "name": name,
            "qty": qty,
            "count": qty,
            "amount": amount,
            "price": amount,
            "weight": round(confidence, 3),
            "confidence": round(confidence, 3),
            "lineIndex": line_index,
            "bbox": {
                "x": round(line.x, 2),
                "y": round(line.y, 2),
                "width": round(line.width, 2),
                "height": round(line.height, 2),
            },
            "confidenceTrace": {
                "source": "aligned_ocr_table",
                "rightAlignedPrice": right_aligned_price,
                "quantityColumn": bool(qty_box),
                "amountColumnX": round(amount_center, 2),
            },
        }
        return {
            "item": item,
            "diagnostic": {
                "lineIndex": line_index,
                "text": text,
                "role": "item",
                "name": name,
                "qty": qty,
                "amount": amount,
                "amountColumnX": round(amount_center, 2),
                "confidence": round(confidence, 3),
            },
        }

    def _is_table_header(self, upper: str) -> bool:
        return bool(re.search(r"\b(?:QTY|QUANTITY)\b", upper) and re.search(r"\b(?:PRICE|AMOUNT|TOTAL)\b", upper))

    def _is_money_token(self, value: str) -> bool:
        return bool(re.fullmatch(r"\$?\s*-?\d{1,5}(?:[.,]\d{2}|\s+\d{2})\s*[A-Z]?", _compact_text(value), flags=re.IGNORECASE))

    def _is_noise_token(self, value: str) -> bool:
        upper = _compact_text(value).upper()
        return upper in {"$", "NF", "N", "F", "T", "EA", "@"}

    def _is_totals_or_payment_row(self, upper: str) -> bool:
        return bool(re.search(r"\b(?:SUB\s*TOTAL|SUBTOTAL|TOTAL|TAX|TIP|BALANCE|CHANGE|USD|VISA|MASTERCARD|AMEX|DISCOVER|CASH|CREDIT|DEBIT|AUTH|APPROVED|THANK|SURVEY|FEEDBACK)\b", upper))

    def _quantity_box(self, boxes: list[OCRBox]) -> OCRBox | None:
        for box in boxes[:2]:
            if re.fullmatch(r"\d{1,3}(?:[.,]\d+)?", _compact_text(box.text)):
                return box
        return None

    def _valid_item_name(self, name: str) -> bool:
        upper = _compact_text(name).upper()
        return len(upper) >= 3 and bool(re.search(r"[A-Z]{3,}", upper)) and not self._is_totals_or_payment_row(upper)

    def _clean_aligned_name(self, name: str) -> str:
        cleaned = re.sub(r"\b(?:NF|N F|TAX|EA)\b$", "", _compact_text(name), flags=re.IGNORECASE)
        cleaned = re.sub(r"\s+", " ", cleaned).strip(" -_:;")
        return cleaned

    def _qty_from_name(self, name: str) -> str:
        match = re.match(r"^(?P<qty>\d{1,3}(?:[.,]\d+)?)\s+(?P<name>[A-Za-z].*)$", _compact_text(name))
        return match.group("qty").replace(",", ".") if match else ""

    def _dedupe_aligned_items(self, items: list[dict[str, Any]]) -> list[dict[str, Any]]:
        output = []
        seen = set()
        for item in items:
            key = f"{re.sub(r'[^A-Z0-9]+', '', str(item.get('name', '')).upper())}:{item.get('amount')}:{item.get('qty')}"
            if key in seen:
                continue
            seen.add(key)
            output.append({**item, "id": len(output) + 1})
        return output

    def _median(self, values: list[float]) -> float:
        if not values:
            return 0.0
        ordered = sorted(values)
        return ordered[len(ordered) // 2]


class ReceiptGraphBuilder:
    def build(self, merchant: str, items: list[dict[str, Any]], facts: dict[str, str], blocks: list[SemanticBlock]) -> dict[str, Any]:
        nodes: list[dict[str, Any]] = [
            {"id": "receipt", "type": "Receipt", "properties": {"documentType": "receipt"}},
        ]
        edges: list[dict[str, str]] = []
        if merchant:
            nodes.append({"id": "merchant", "type": "Merchant", "properties": {"name": merchant}})
            edges.append({"from": "receipt", "to": "merchant", "type": "PURCHASED_AT"})
        for key, value in facts.items():
            if value:
                node_id = f"fact-{key}"
                nodes.append({"id": node_id, "type": "ReceiptFact", "properties": {"name": key, "value": value}})
                edges.append({"from": "receipt", "to": node_id, "type": "HAS_FACT"})
        for index, item in enumerate(items):
            node_id = f"item-{index + 1}"
            nodes.append({
                "id": node_id,
                "type": "ReceiptItem",
                "properties": {
                    "name": item.get("name", ""),
                    "qty": item.get("qty") or item.get("count") or "1",
                    "amount": item.get("amount") or item.get("price") or "",
                },
            })
            edges.append({"from": "receipt", "to": node_id, "type": "HAS_ITEM"})
        for block in blocks:
            nodes.append({"id": block.id, "type": "SemanticBlock", "properties": {"kind": block.kind, "confidence": round(block.confidence, 3)}})
            edges.append({"from": "receipt", "to": block.id, "type": "HAS_BLOCK"})
        return {"nodes": nodes, "edges": edges}


class ReceiptLayoutAnalyzer:
    def summarize(
        self,
        lines: list[ReconstructedLine],
        regions: list[OCRRegion],
        blocks: list[SemanticBlock],
        tables: list[dict[str, Any]],
        graph: dict[str, Any],
        warnings: list[str],
    ) -> dict[str, Any]:
        avg_confidence = sum(line.confidence for line in lines) / max(len(lines), 1) if lines else 0.0
        indicators = self._quality_indicators(lines, regions, warnings)
        return {
            "schemaVersion": "receipt-layout-v1",
            "quality": {
                "averageOcrConfidence": round(avg_confidence, 3),
                "lineCount": len(lines),
                "regionCount": len(regions),
                "warnings": warnings,
                "indicators": indicators,
            },
            "regions": [region.to_dict() for region in regions],
            "semanticBlocks": [block.to_dict() for block in blocks],
            "tables": tables,
            "graph": graph,
        }

    def _quality_indicators(self, lines: list[ReconstructedLine], regions: list[OCRRegion], warnings: list[str]) -> dict[str, bool]:
        low_confidence_ratio = sum(1 for line in lines if line.confidence < 0.68) / max(len(lines), 1) if lines else 1.0
        y_positions = [line.y for line in lines if line.y]
        large_vertical_gaps = 0
        if len(y_positions) > 2:
            ordered = sorted(y_positions)
            gaps = [ordered[index + 1] - ordered[index] for index in range(len(ordered) - 1)]
            median_gap = sorted(gaps)[len(gaps) // 2] if gaps else 0
            large_vertical_gaps = sum(1 for gap in gaps if median_gap and gap > median_gap * 3)
        return {
            "likelyBlurry": low_confidence_ratio > 0.32,
            "likelyFolded": large_vertical_gaps >= 2 or any("item_sum_does_not_match_subtotal" == warning for warning in warnings),
            "likelyShadowed": any(region.confidence < 0.62 and region.height > 40 for region in regions),
        }


class ReceiptValidationEngine:
    def validate(self, items: list[dict[str, Any]], facts: dict[str, str], structured: dict[str, Any] | None = None) -> dict[str, Any]:
        structured = structured or {}
        subtotal = _numeric(facts.get("subtotal") or structured.get("subtotal") or structured.get("subTotal"))
        total = _numeric(facts.get("total") or structured.get("total"))
        tax = _numeric(facts.get("tax") or structured.get("tax"))
        item_sum = sum(_numeric(item.get("amount")) for item in items)
        warnings: list[str] = []
        if subtotal and item_sum and abs(item_sum - subtotal) > max(0.25, subtotal * 0.03):
            warnings.append("item_sum_does_not_match_subtotal")
        if subtotal and total and total + 0.01 < subtotal:
            warnings.append("total_less_than_subtotal")
        if subtotal and total and tax and abs((subtotal + tax) - total) > max(0.35, total * 0.04):
            warnings.append("subtotal_tax_total_mismatch")
        return {
            "itemSum": f"{item_sum:.2f}" if item_sum else "0",
            "subtotalDelta": round(abs(item_sum - subtotal), 2) if subtotal and item_sum else None,
            "warnings": warnings,
            "valid": not warnings,
        }


class ReceiptConfidenceEngine:
    def score(self, lines: list[ReconstructedLine], items: list[dict[str, Any]], validation: dict[str, Any], merchant: str) -> dict[str, Any]:
        line_conf = sum(line.confidence for line in lines) / max(len(lines), 1) if lines else 0.0
        item_score = min(1.0, len(items) / 4) if items else 0.0
        merchant_score = 1.0 if merchant else 0.0
        validation_score = 1.0 if validation.get("valid") else 0.62
        overall = max(0.0, min(1.0, (line_conf * 0.28) + (item_score * 0.28) + (merchant_score * 0.18) + (validation_score * 0.26)))
        return {
            "overall": round(overall, 3),
            "ocr": round(line_conf, 3),
            "items": round(item_score, 3),
            "merchant": round(merchant_score, 3),
            "validation": round(validation_score, 3),
        }


class ReceiptRetryPlanner:
    def plan(self, confidence: dict[str, Any], validation: dict[str, Any]) -> list[dict[str, Any]]:
        retries: list[dict[str, Any]] = []
        if confidence.get("ocr", 1) < 0.72:
            retries.append({"stage": "ocr", "strategy": "opencv_preprocess_high_contrast", "reason": "low_ocr_confidence"})
            retries.append({"stage": "ocr", "strategy": "deskew_and_adaptive_threshold", "reason": "low_ocr_confidence"})
        if validation.get("warnings"):
            retries.append({"stage": "ai", "strategy": "llama_validation_retry", "reason": ",".join(validation["warnings"])})
        if confidence.get("items", 1) < 0.35:
            retries.append({"stage": "layout", "strategy": "line_reconstruction_with_bounding_boxes", "reason": "few_items_detected"})
        return retries[:5]


class ReceiptIntelligencePipeline:
    def __init__(self) -> None:
        self.reconstructor = ReceiptLineReconstructor()
        self.duplicates = ReceiptDuplicateSuppressor()
        self.merchants = MerchantNormalizer()
        self.parser = ReceiptSemanticParser()
        self.clusterer = ReceiptSpatialClusterer()
        self.blocks = ReceiptSemanticBlockBuilder()
        self.tables = ReceiptTableReconstructor()
        self.graph = ReceiptGraphBuilder()
        self.layout = ReceiptLayoutAnalyzer()
        self.validator = ReceiptValidationEngine()
        self.confidence = ReceiptConfidenceEngine()
        self.retry = ReceiptRetryPlanner()
        self.entities = ReceiptEntityExtractionEngine()
        self.sections = ReceiptSectionExtractionEngine()
        self.ontology = ReceiptOntologyEngine()

    def analyze(
        self,
        raw_text: str,
        lines: list[str] | None = None,
        parser_json: dict[str, Any] | None = None,
        ocr_variants: list[dict[str, Any]] | None = None,
        ocr_blocks: list[dict[str, Any]] | None = None,
    ) -> ParsedReceiptCandidate:
        reconstructed = self.reconstructor.reconstruct(raw_text, lines, ocr_blocks)
        for variant in ocr_variants or []:
            if isinstance(variant, dict) and isinstance(variant.get("boxes"), list):
                reconstructed.extend(self.reconstructor.reconstruct("", variant.get("lines") or [], variant.get("boxes")))
        reconstructed = self.duplicates.suppress(reconstructed)
        normalized_text = "\n".join(line.text for line in reconstructed)
        reconstructed_text_lines = [line.text for line in reconstructed]
        section_extraction = self.sections.extract(
            raw_text=normalized_text or raw_text,
            lines=reconstructed_text_lines,
            ocr_blocks=ocr_blocks,
        )
        entity_result = self.entities.extract(raw_text=normalized_text or raw_text, lines=[line.text for line in reconstructed], ocr_blocks=ocr_blocks)
        parser_json = parser_json or {}
        parsed_items, parsed_facts = self.parser.parse(reconstructed)
        parser_items = self._items_from_parser_json(parser_json)
        retail_items, retail_row_reconstruction = self.tables.extract_retail_multiline_items(reconstructed)
        aligned_items, aligned_table_reconstruction = self.tables.extract_aligned_items(reconstructed)
        section_items = section_extraction.get("items", []) if isinstance(section_extraction, dict) else []
        section_total_fields = (section_extraction.get("totals", {}) or {}).get("fields", {}) if isinstance(section_extraction, dict) else {}
        section_payment_fields = (section_extraction.get("payment", {}) or {}).get("fields", {}) if isinstance(section_extraction, dict) else {}
        facts = {
            **parsed_facts,
            **{key: value for key, value in section_total_fields.items() if value},
        }
        items = self._select_best_item_source(
            section_items=section_items,
            retail_items=retail_items,
            aligned_items=aligned_items,
            parsed_items=parsed_items,
            parser_items=parser_items,
            facts=facts,
            parser_json=parser_json,
        )
        entity_fields = entity_result.get("fields", {})
        temporal_entities = self._temporal_entities(reconstructed)
        entity_result.setdefault("debug", {})["temporalEntities"] = temporal_entities
        date_candidate = temporal_entities.get("transactionDate") or temporal_entities.get("orderDate")
        if date_candidate and (
            not entity_fields.get("date")
            or (self._temporal_value_has_time(date_candidate.get("value", "")) and not self._temporal_value_has_time(entity_fields.get("date", "")))
        ):
            entity_fields["date"] = date_candidate["value"]
            entity_fields["purchaseDate"] = date_candidate["value"]
            entity_result.setdefault("confidence", {})["date"] = date_candidate["confidence"]
            entity_result.setdefault("debug", {})["purchaseDateCandidate"] = date_candidate
        for source_key, target_key in (
            ("paymentMethod", "paymentMethod"),
            ("cardUsed", "cardUsed"),
            ("cardLast4", "cardLast4"),
            ("approvalCode", "approvalCode"),
        ):
            if section_payment_fields.get(source_key) and not entity_fields.get(target_key):
                entity_fields[target_key] = section_payment_fields[source_key]
        if section_payment_fields.get("charge"):
            facts["charge"] = section_payment_fields["charge"]
        tax_relationship = (section_extraction.get("totals", {}) or {}).get("taxRelationship", {}) if isinstance(section_extraction, dict) else {}
        if tax_relationship.get("taxPercent"):
            facts["taxPercent"] = tax_relationship["taxPercent"]
        if tax_relationship.get("taxPercent") and tax_relationship.get("taxAmount"):
            facts["taxAmount"] = tax_relationship["taxAmount"]
        parser_merchant_candidate = str(parser_json.get("company") or parser_json.get("storeName") or "")
        entity_merchant_candidate = str(entity_fields.get("merchant") or "")
        logo_candidates = self._logo_merchant_candidates(parser_json)
        logo_merchant_candidate = str(logo_candidates[0].get("merchant") or "") if logo_candidates else ""
        merchant_candidate = (
            parser_merchant_candidate
            if self.merchants._looks_like_header_merchant(parser_merchant_candidate)
            else logo_merchant_candidate or entity_merchant_candidate or parser_merchant_candidate
        )
        merchant_resolution_text = "\n".join([
            *[str(candidate.get("merchant") or "") for candidate in logo_candidates if candidate.get("merchant")],
            normalized_text or raw_text,
        ])
        merchant_resolution = self.merchants.resolve(
            merchant_resolution_text,
            merchant_candidate,
        )
        if logo_candidates and merchant_resolution.get("merchant"):
            merchant_resolution.setdefault("visualIdentityCandidates", logo_candidates)
            matched_logo = self._matching_logo_candidate(merchant_resolution["merchant"], logo_candidates)
            if matched_logo:
                merchant_resolution["confidence"] = round(max(
                    float(merchant_resolution.get("confidence") or 0.0),
                    float(matched_logo.get("confidence") or 0.0),
                ), 3)
                merchant_resolution["source"] = "visual_logo_crop"
                merchant_resolution.setdefault("evidence", []).extend(matched_logo.get("evidence") or [])
        entity_merchant_confidence = float((entity_result.get("confidence", {}) or {}).get("merchant") or 0.0)
        if entity_merchant_candidate and merchant_resolution.get("merchant") == entity_merchant_candidate and entity_merchant_confidence:
            merchant_resolution["confidence"] = round(max(float(merchant_resolution.get("confidence") or 0.0), entity_merchant_confidence), 3)
            merchant_resolution.setdefault("evidence", []).append({
                "type": "visual_hierarchy_merchant",
                "value": entity_merchant_candidate,
                "confidence": entity_merchant_confidence,
            })
        merchant = merchant_resolution["merchant"]
        validation = self.validator.validate(items, facts, parser_json)
        confidence = self.confidence.score(reconstructed, items, validation, merchant)
        confidence["merchant"] = round(float(merchant_resolution.get("confidence") or 0.0), 3)
        retry_plan = self.retry.plan(confidence, validation)
        regions = self.clusterer.cluster(reconstructed)
        semantic_blocks = self._state_aligned_semantic_blocks(
            self.blocks.build(reconstructed, regions),
            reconstructed,
            section_extraction,
        )
        tables = self.tables.reconstruct(reconstructed, items, facts)
        if tables and aligned_table_reconstruction.get("schemaVersion"):
            tables[0].setdefault("reconstruction", aligned_table_reconstruction)
            tables[0]["reconstruction"]["retailRowAssembly"] = retail_row_reconstruction
        ontology = self.ontology.build(
            lines=reconstructed,
            items=items,
            facts=facts,
            entity_result=entity_result,
            section_extraction=section_extraction,
            merchant_resolution=merchant_resolution,
            duplicate_diagnostics=self.duplicates.last_diagnostics,
        )
        graph = self.graph.build(merchant, items, facts, semantic_blocks)
        graph["ontology"] = ontology.get("entityGraph", {})
        layout_json = self.layout.summarize(
            reconstructed,
            regions,
            semantic_blocks,
            tables,
            graph,
            validation["warnings"],
        )
        layout_json["sectionExtraction"] = section_extraction
        layout_json["alignedTableReconstruction"] = aligned_table_reconstruction
        layout_json["retailRowReconstruction"] = retail_row_reconstruction
        layout_json["stateMachine"] = section_extraction.get("documentStateMachine", {})
        layout_json["ontology"] = ontology
        if logo_candidates:
            layout_json["visualIdentity"] = {
                "schemaVersion": "receipt-visual-identity-v1",
                "candidates": logo_candidates,
            }
        return ParsedReceiptCandidate(
            merchant=merchant,
            merchant_trace=merchant_resolution,
            lines=reconstructed,
            items=items,
            facts=facts,
            regions=regions,
            semantic_blocks=semantic_blocks,
            tables=tables,
            graph=graph,
            layout_json=layout_json,
            warnings=validation["warnings"],
            confidence=confidence,
            retry_plan=retry_plan,
            entities=entity_result,
            section_extraction=section_extraction,
            ontology=ontology,
        )

    def _purchase_date_candidate(self, lines: list[ReconstructedLine]) -> dict[str, Any] | None:
        temporal = self._temporal_entities(lines)
        return temporal.get("transactionDate") or temporal.get("orderDate")

    def _temporal_value_has_time(self, value: Any) -> bool:
        return bool(re.search(r"\b\d{1,2}:\d{2}(?::\d{2})?\b", str(value or "")))

    def _temporal_entities(self, lines: list[ReconstructedLine]) -> dict[str, Any]:
        candidates: list[dict[str, Any]] = []
        for line_index, line in enumerate(lines):
            text = _compact_text(line.text)
            if not text:
                continue
            upper = text.upper()
            if any(token in upper for token in ("RETURN POLICY", "POLICY", "THRU", "EXPIRES", "EXPIRATION", "VALID UNTIL")):
                continue
            candidates.extend(self._temporal_candidates_for_line(text, upper, line, line_index))
        candidates.sort(key=lambda item: item["confidence"], reverse=True)
        selected_transaction = next((candidate for candidate in candidates if candidate["kind"] == "transactionDate"), None)
        selected_order = next((candidate for candidate in candidates if candidate["kind"] == "orderDate"), None)
        selected_payment = next((candidate for candidate in candidates if candidate["kind"] == "paymentTime"), None)
        selected_print = next((candidate for candidate in candidates if candidate["kind"] == "printTime"), None)
        selected_transaction_time = self._time_from_temporal_value(selected_transaction)
        return {
            "schemaVersion": "receipt-temporal-entities-v1",
            "transactionDate": selected_transaction,
            "transactionTime": selected_transaction_time,
            "orderDate": selected_order,
            "paymentTime": selected_payment,
            "printTime": selected_print,
            "candidates": candidates[:20],
        }

    def _temporal_candidates_for_line(
        self,
        text: str,
        upper: str,
        line: ReconstructedLine,
        line_index: int,
    ) -> list[dict[str, Any]]:
        candidates: list[dict[str, Any]] = []
        numeric_pattern = re.compile(
            r"\b(?P<month>\d{1,2})[/-](?P<day>\d{1,2})[/-](?P<year>\d{2,4})"
            r"(?:\s+(?P<time>\d{1,2}:\d{2}(?::\d{2})?)\s*(?P<meridiem>[AP]\.?M\.?|[AP])?)?",
            flags=re.IGNORECASE,
        )
        day_month_pattern = re.compile(
            r"\b(?P<day>\d{1,2})[-\s](?P<month>JAN|FEB|MAR|APR|MAY|JUN|JUL|AUG|SEP|SEPT|OCT|NOV|DEC)[A-Z]*[-\s](?P<year>\d{2,4})"
            r"(?:\s+(?P<time>\d{1,2}:\d{2}(?::\d{2})?)\s*(?P<meridiem>[AP]\.?M\.?|[AP])?)?",
            flags=re.IGNORECASE,
        )
        month_day_pattern = re.compile(
            r"\b(?P<month>JAN|FEB|MAR|APR|MAY|JUN|JUL|AUG|SEP|SEPT|OCT|NOV|DEC)[A-Z]*\s+(?P<day>\d{1,2}),?\s+(?P<year>\d{2,4})"
            r"(?:\s+(?P<time>\d{1,2}:\d{2}(?::\d{2})?)\s*(?P<meridiem>[AP]\.?M\.?|[AP])?)?",
            flags=re.IGNORECASE,
        )
        for match in numeric_pattern.finditer(text):
            value = self._normalize_numeric_temporal_match(match)
            if value:
                candidates.append(self._temporal_candidate(value, text, upper, line, line_index, "numeric_date_pattern"))
        for match in day_month_pattern.finditer(text):
            value = self._normalize_named_month_temporal_match(match, day_first=True)
            if value:
                candidates.append(self._temporal_candidate(value, text, upper, line, line_index, "dd_mon_yyyy_pattern"))
        for match in month_day_pattern.finditer(text):
            value = self._normalize_named_month_temporal_match(match, day_first=False)
            if value:
                candidates.append(self._temporal_candidate(value, text, upper, line, line_index, "mon_dd_yyyy_pattern"))
        time_only = re.search(r"\b(?P<time>\d{1,2}:\d{2}(?::\d{2})?)\s*(?P<meridiem>[AP]\.?M\.?|[AP])\b", text, flags=re.IGNORECASE)
        if time_only and any(token in upper for token in ("PAYMENT", "PAID", "CHIP", "AUTH", "CARD")):
            value = self._normalize_time(time_only.group("time"), time_only.group("meridiem"))
            if value:
                candidates.append({
                    "kind": "paymentTime",
                    "value": value,
                    "confidence": round(min(0.86, 0.68 + line.confidence * 0.12), 3),
                    "source": "receipt.payment_time_regex",
                    "line": text,
                    "lineIndex": line_index,
                    "reasons": ["payment_time_context"],
                })
        return candidates

    def _temporal_candidate(
        self,
        value: str,
        text: str,
        upper: str,
        line: ReconstructedLine,
        line_index: int,
        pattern_reason: str,
    ) -> dict[str, Any]:
        score = 0.62 + min(0.14, line.confidence * 0.14)
        reasons = [pattern_reason]
        kind = "transactionDate"
        has_transaction_context = any(token in upper for token in ("SALE", "SALES", "TRANS", "TRN", "TRANSACTION", "INVOICE", "RECEIPT", "IRARNSH", "TRAUSH", "ORDER"))
        has_payment_context = any(token in upper for token in ("PAYMENT", "PAID", "CHIP", "AUTH", "TERMINAL", "AID", "CARD", "REF", "VISA", "MASTERCARD", "AMEX", "DISCOVER", "CREDIT", "DEBIT"))
        if has_transaction_context:
            score += 0.14
            reasons.append("transaction_context")
        if any(token in upper for token in ("ORDER", "INVOICE")):
            kind = "orderDate"
        if any(token in upper for token in ("PRINT", "REPRINT", "DUPLICATE")):
            kind = "printTime"
            reasons.append("print_context")
        if has_payment_context and not has_transaction_context and kind == "transactionDate":
            payment_value = self._time_from_temporal_text(value, text)
            if payment_value:
                return {
                    "kind": "paymentTime",
                    "value": payment_value,
                    "confidence": round(max(0.55, min(0.9, score + 0.06)), 3),
                    "source": "receipt.payment_temporal_context",
                    "line": text,
                    "lineIndex": line_index,
                    "reasons": [*reasons, "payment_context"],
                }
        elif has_payment_context:
            score -= 0.04
            reasons.append("payment_context_secondary")
        if line.y <= 28:
            score += 0.04
            reasons.append("upper_receipt_position")
        return {
            "kind": kind,
            "value": value,
            "confidence": round(max(0.45, min(0.94, score)), 3),
            "source": "receipt.temporal_entity_regex",
            "line": text,
            "lineIndex": line_index,
            "reasons": reasons,
        }

    def _normalize_numeric_temporal_match(self, match: re.Match[str]) -> str:
        month = self._normalize_date_number(match.group("month"), 12)
        day = self._normalize_date_number(match.group("day"), 31)
        year = self._normalize_receipt_year(match.group("year"))
        if not month or not day or not year:
            return ""
        time_value = self._normalize_time(match.group("time") or "", match.group("meridiem") or "")
        return f"{month}/{day}/{year}{f' {time_value}' if time_value else ''}"

    def _normalize_named_month_temporal_match(self, match: re.Match[str], day_first: bool) -> str:
        month_token = str(match.group("month") or "").upper()[:4]
        month = MONTH_ABBREVIATIONS.get(month_token) or MONTH_ABBREVIATIONS.get(month_token[:3], "")
        day = self._normalize_date_number(match.group("day"), 31)
        year = self._normalize_receipt_year(match.group("year"))
        if not month or not day or not year:
            return ""
        time_value = self._normalize_time(match.group("time") or "", match.group("meridiem") or "")
        return f"{month}/{day}/{year}{f' {time_value}' if time_value else ''}"

    def _normalize_time(self, time_raw: str, meridiem_raw: str = "") -> str:
        time_raw = _compact_text(time_raw)
        if not time_raw:
            return ""
        match = re.fullmatch(r"(?P<hour>\d{1,2}):(?P<minute>\d{2})(?::(?P<second>\d{2}))?", time_raw)
        if not match:
            return ""
        hour = int(match.group("hour"))
        minute = int(match.group("minute"))
        second = match.group("second")
        if hour > 23 or minute > 59 or (second and int(second) > 59):
            return ""
        meridiem = re.sub(r"[^AP]", "", str(meridiem_raw or "").upper())
        suffix = f" {meridiem}M" if meridiem in {"A", "P"} else ""
        return f"{hour:02d}:{minute:02d}{f':{second}' if second else ''}{suffix}"

    def _time_from_temporal_value(self, candidate: dict[str, Any] | None) -> dict[str, Any] | None:
        if not isinstance(candidate, dict):
            return None
        value = str(candidate.get("value") or "")
        time_value = self._time_from_temporal_text(value, value)
        if not time_value:
            return None
        return {
            "kind": "transactionTime",
            "value": time_value,
            "confidence": candidate.get("confidence", 0.0),
            "source": candidate.get("source", "receipt.temporal_entity_regex"),
            "line": candidate.get("line", ""),
            "lineIndex": candidate.get("lineIndex"),
            "reasons": [*(candidate.get("reasons") or []), "derived_from_transaction_timestamp"],
        }

    def _time_from_temporal_text(self, normalized_value: str, source_text: str) -> str:
        for value in (normalized_value, source_text):
            match = re.search(r"\b(?P<time>\d{1,2}:\d{2}(?::\d{2})?)\s*(?P<meridiem>[AP]\.?M\.?|[AP])?\b", str(value or ""), flags=re.IGNORECASE)
            if match:
                return self._normalize_time(match.group("time"), match.group("meridiem") or "")
        return ""

    def _normalize_purchase_date_match(self, match: re.Match[str]) -> str:
        month_raw, day_raw, year_raw, time_raw = match.groups()
        month = self._normalize_date_number(month_raw, 12)
        day = self._normalize_date_number(day_raw, 31)
        year = self._normalize_receipt_year(year_raw)
        if not month or not day or not year:
            return ""
        return f"{month}/{day}/{year}{f' {time_raw}' if time_raw else ''}"

    def _normalize_date_number(self, value: str, max_value: int) -> str:
        digits = re.sub(r"\D", "", str(value or ""))
        if not digits:
            return ""
        number = int(digits)
        if 1 <= number <= max_value:
            return f"{number:02d}"
        if len(digits) == 2 and digits[0] == "9":
            corrected = int(f"1{digits[1]}")
            if 1 <= corrected <= max_value:
                return f"{corrected:02d}"
        if len(digits) == 2 and digits[0] in {"6", "8"}:
            corrected = int(f"0{digits[1]}")
            if 1 <= corrected <= max_value:
                return f"{corrected:02d}"
        return ""

    def _normalize_receipt_year(self, value: str) -> str:
        digits = re.sub(r"\D", "", str(value or ""))
        if len(digits) == 2:
            return f"20{digits}"
        if len(digits) == 4 and 1990 <= int(digits) <= 2100:
            return digits
        return ""

    def _logo_merchant_candidates(self, parser_json: dict[str, Any]) -> list[dict[str, Any]]:
        raw_candidates = parser_json.get("logoCandidates") if isinstance(parser_json, dict) else []
        if not isinstance(raw_candidates, list):
            return []
        candidates: list[dict[str, Any]] = []
        for raw in raw_candidates:
            if not isinstance(raw, dict):
                continue
            merchant = _compact_text(raw.get("merchant") or raw.get("value") or raw.get("text") or "")
            if not merchant:
                continue
            if not self.merchants._looks_like_header_merchant(merchant):
                continue
            if self.merchants._looks_like_generic_business_fragment(merchant):
                continue
            candidates.append({
                "merchant": merchant,
                "confidence": round(float(raw.get("confidence") or 0.62), 3),
                "source": raw.get("source") or "logo_header_crop",
                "crop": raw.get("crop") or {},
                "evidence": raw.get("evidence") or [{"type": "visual_logo_crop", "value": merchant}],
            })
        candidates.sort(key=lambda item: item["confidence"], reverse=True)
        return candidates[:5]

    def _matching_logo_candidate(self, merchant: str, candidates: list[dict[str, Any]]) -> dict[str, Any] | None:
        target = re.sub(r"[^A-Z0-9]+", "", str(merchant or "").upper())
        if not target:
            return None
        for candidate in candidates:
            value = re.sub(r"[^A-Z0-9]+", "", str(candidate.get("merchant") or "").upper())
            if value and (target == value or target in value or value in target):
                return candidate
        return None

    def _items_from_parser_json(self, parser_json: dict[str, Any]) -> list[dict[str, Any]]:
        sources: list[Any] = []
        if isinstance(parser_json.get("items"), list):
            sources.append(parser_json.get("items"))
        document_understanding = parser_json.get("documentUnderstanding")
        if isinstance(document_understanding, dict) and isinstance(document_understanding.get("items"), list):
            sources.append(document_understanding.get("items"))
        items: list[dict[str, Any]] = []
        seen: set[str] = set()
        for source in sources:
            for raw in source or []:
                if not isinstance(raw, dict):
                    continue
                name = _compact_text(raw.get("name") or raw.get("description") or raw.get("text") or "")
                amount = self._amount_text(raw.get("amount") or raw.get("price") or raw.get("total") or "")
                if not name or not amount:
                    continue
                qty = _compact_text(raw.get("qty") or raw.get("count") or raw.get("quantity") or "1") or "1"
                if self._looks_like_non_item_parser_row(name, qty, amount):
                    continue
                key = f"{name.upper()}:{amount}"
                if key in seen:
                    continue
                seen.add(key)
                items.append({
                    "name": name,
                    "qty": qty,
                    "count": qty,
                    "amount": amount,
                    "price": amount,
                    "confidence": float(raw.get("confidence", raw.get("weight", 0.72)) or 0.72),
                })
        return items

    def _looks_like_non_item_parser_row(self, name: str, qty: str, amount: str) -> bool:
        upper = _compact_text(name).upper()
        if re.search(r"\b(?:INVOICE|EXP\.?\s*DATE|APPROVED|AUTH(?:ORIZATION)?|AID|TVR|TSI|RRN|ENTRY\s+METHOD)\b", upper):
            return True
        if self.tables._is_totals_or_payment_row(upper):
            return True
        numeric_qty = self._any_numeric(qty)
        numeric_amount = self._any_numeric(amount)
        if numeric_qty > 999:
            return True
        if numeric_amount > 10000 and not re.search(r"[A-Z]{3,}", upper):
            return True
        return False

    def _any_numeric(self, value: Any) -> float:
        match = re.search(r"-?\d+(?:[.,]\d+)?", str(value or ""))
        return float(match.group(0).replace(",", ".")) if match else 0.0

    def _select_best_item_source(
        self,
        section_items: list[dict[str, Any]],
        retail_items: list[dict[str, Any]],
        aligned_items: list[dict[str, Any]],
        parsed_items: list[dict[str, Any]],
        parser_items: list[dict[str, Any]],
        facts: dict[str, str],
        parser_json: dict[str, Any],
    ) -> list[dict[str, Any]]:
        candidates = [
            ("section", section_items),
            ("retail_multiline", retail_items),
            ("aligned_table", aligned_items),
            ("parser", parsed_items),
            ("external", parser_items),
        ]
        scored = [
            (self._item_source_score(items, facts, parser_json, source), source, items)
            for source, items in candidates
            if items
        ]
        if not scored:
            return []
        scored.sort(key=lambda entry: entry[0], reverse=True)
        return scored[0][2]

    def _item_source_score(self, items: list[dict[str, Any]], facts: dict[str, str], parser_json: dict[str, Any], source: str = "") -> float:
        validation = self.validator.validate(items, facts, parser_json)
        subtotal = _numeric(facts.get("subtotal") or parser_json.get("subtotal") or parser_json.get("subTotal"))
        total = _numeric(facts.get("total") or parser_json.get("total"))
        target = subtotal or total
        item_sum = sum(_numeric(item.get("amount")) for item in items)
        delta = abs(item_sum - target) if target and item_sum else 999.0
        confidence = sum(float(item.get("confidence", item.get("weight", 0.0)) or 0.0) for item in items) / max(len(items), 1)
        score = confidence + min(len(items), 4) * 0.08
        if source == "retail_multiline":
            arithmetic_valid = sum(
                1 for item in items
                if ((item.get("confidenceTrace") or {}).get("arithmetic") or {}).get("valid")
            )
            description_links = sum(1 for item in items if item.get("descriptionLineIndexes") and item.get("pricingLineIndex") is not None)
            score += 0.42 + min(0.4, arithmetic_valid * 0.12) + min(0.35, description_links * 0.14)
        if validation.get("valid"):
            score += 1.0
        if target and item_sum:
            score -= min(2.5, delta / max(target, 1.0) * 8.0)
        if validation.get("warnings"):
            score -= len(validation["warnings"]) * 0.6
        return score

    def _amount_text(self, value: Any) -> str:
        match = re.search(r"-?\d{1,7}(?:[.,]\d{2})", str(value or "").replace(",", "."))
        return match.group(0).replace(",", ".") if match else ""

    def _state_aligned_semantic_blocks(
        self,
        blocks: list[SemanticBlock],
        lines: list[ReconstructedLine],
        section_extraction: dict[str, Any],
    ) -> list[SemanticBlock]:
        state_machine = (section_extraction or {}).get("documentStateMachine", {}) or {}
        line_states = state_machine.get("lineStates", []) or []
        if not line_states:
            return blocks
        kind_by_state = {
            "HEADER": "merchant",
            "ITEMS": "items",
            "TOTALS": "totals",
            "PAYMENT": "payment",
            "FOOTER": "footer",
        }
        output: list[SemanticBlock] = []
        current_state = ""
        current_indexes: list[int] = []
        current_lines: list[str] = []
        confidence_values: list[float] = []
        for entry in line_states:
            state = entry.get("state") or "HEADER"
            line_index = entry.get("lineIndex")
            if not isinstance(line_index, int) or line_index < 0 or line_index >= len(lines):
                continue
            if current_state and state != current_state:
                output.append(self._semantic_block_from_state(current_state, current_indexes, current_lines, confidence_values, kind_by_state))
                current_indexes = []
                current_lines = []
                confidence_values = []
            current_state = state
            current_indexes.append(line_index)
            current_lines.append(lines[line_index].text)
            confidence_values.append(float(entry.get("confidence", lines[line_index].confidence) or 0.0))
        if current_indexes:
            output.append(self._semantic_block_from_state(current_state, current_indexes, current_lines, confidence_values, kind_by_state))
        return output or blocks

    def _semantic_block_from_state(
        self,
        state: str,
        line_indexes: list[int],
        lines: list[str],
        confidence_values: list[float],
        kind_by_state: dict[str, str],
    ) -> SemanticBlock:
        confidence = sum(confidence_values) / max(len(confidence_values), 1)
        return SemanticBlock(
            id=f"state-block-{len(line_indexes)}-{line_indexes[0] if line_indexes else 0}-{state.lower()}",
            kind=kind_by_state.get(state, "unknown"),
            text="\n".join(lines),
            confidence=confidence,
            line_indexes=line_indexes,
            region_ids=[],
        )

    def to_structured_json(
        self,
        raw_text: str,
        lines: list[str] | None = None,
        parser_json: dict[str, Any] | None = None,
        ocr_variants: list[dict[str, Any]] | None = None,
        ocr_blocks: list[dict[str, Any]] | None = None,
        ocr_engine: str | None = None,
    ) -> dict[str, Any]:
        candidate = self.analyze(
            raw_text=raw_text,
            lines=lines,
            parser_json=parser_json,
            ocr_variants=ocr_variants,
            ocr_blocks=ocr_blocks,
        )
        validation = self.validator.validate(candidate.items, candidate.facts, parser_json or {})
        entity_fields = candidate.entities.get("fields", {}) if isinstance(candidate.entities, dict) else {}
        temporal_entities = (candidate.entities.get("debug", {}) if isinstance(candidate.entities, dict) else {}).get("temporalEntities", {})
        tax_relationship = (candidate.section_extraction.get("totals", {}) or {}).get("taxRelationship", {}) if isinstance(candidate.section_extraction, dict) else {}
        card_last4 = entity_fields.get("cardLast4") or entity_fields.get("lastFour") or ""
        return {
            "schemaVersion": "receipt-semantic-v1",
            "documentType": "receipt",
            "ocrEngine": ocr_engine or "",
            "merchant": candidate.merchant,
            "storeName": candidate.merchant,
            "merchantConfidenceTrace": candidate.merchant_trace,
            "address": entity_fields.get("address", ""),
            "storeAddress": entity_fields.get("storeAddress", ""),
            "phone": entity_fields.get("phone", ""),
            "date": entity_fields.get("date", ""),
            "purchaseDate": entity_fields.get("purchaseDate", entity_fields.get("date", "")),
            "transactionDate": (temporal_entities.get("transactionDate") or {}).get("value", entity_fields.get("date", "")),
            "transactionTime": (temporal_entities.get("transactionTime") or {}).get("value", ""),
            "orderDate": (temporal_entities.get("orderDate") or {}).get("value", ""),
            "paymentTime": (temporal_entities.get("paymentTime") or {}).get("value", ""),
            "printTime": (temporal_entities.get("printTime") or {}).get("value", ""),
            "temporalEntities": temporal_entities,
            "paymentMethod": entity_fields.get("paymentMethod", ""),
            "cardType": entity_fields.get("cardType", ""),
            "cardUsed": entity_fields.get("cardUsed", ""),
            "lastFour": card_last4,
            "cardLast4": card_last4,
            "approvalCode": entity_fields.get("approvalCode", ""),
            "paymentCard": {
                "brand": entity_fields.get("cardUsed", ""),
                "last4": card_last4,
                "approvalCode": entity_fields.get("approvalCode", ""),
            },
            "items": [
                {
                    "id": item.get("id", index + 1),
                    "name": item.get("name", ""),
                    "qty": str(item.get("qty") or item.get("count") or "1"),
                    "count": str(item.get("count") or item.get("qty") or "1"),
                    "amount": str(item.get("amount") or item.get("price") or ""),
                    "price": str(item.get("price") or item.get("amount") or ""),
                    "unitPrice": str(item.get("unitPrice") or ""),
                    "extendedPrice": str(item.get("extendedPrice") or item.get("amount") or item.get("price") or ""),
                    "sku": str(item.get("sku") or ""),
                    "confidence": round(float(item.get("weight", 1.0) or 1.0), 3),
                    "lineIndexes": item.get("lineIndexes", []),
                    "confidenceTrace": item.get("confidenceTrace", {}),
                }
                for index, item in enumerate(candidate.items)
            ],
            "facts": {
                "subtotal": candidate.facts.get("subtotal", ""),
                "tax": candidate.facts.get("tax", ""),
                "tip": candidate.facts.get("tip", ""),
                "total": candidate.facts.get("total", ""),
                **({"taxPercent": candidate.facts.get("taxPercent", "")} if candidate.facts.get("taxPercent") else {}),
                **({"taxAmount": candidate.facts.get("taxAmount", "")} if candidate.facts.get("taxAmount") else {}),
            },
            "taxPercent": tax_relationship.get("taxPercent", ""),
            "taxAmount": tax_relationship.get("taxAmount", ""),
            "taxRelationship": tax_relationship,
            "validation": validation,
            "confidence": candidate.confidence,
            "retryPlan": candidate.retry_plan,
            "warnings": candidate.warnings,
            "reconstructedLines": [
                {
                    "index": index,
                    "text": line.text,
                    "confidence": round(line.confidence, 3),
                    "page": line.page,
                    "bbox": {
                        "x": round(line.x, 2),
                        "y": round(line.y, 2),
                        "width": round(line.width, 2),
                        "height": round(line.height, 2),
                    },
                }
                for index, line in enumerate(candidate.lines)
            ],
            "layout": candidate.layout_json,
            "sectionExtraction": candidate.section_extraction,
            "documentStateMachine": candidate.section_extraction.get("documentStateMachine", {}),
            "documentOntology": candidate.ontology,
            "confidenceTrace": {
                "merchant": candidate.merchant_trace,
                "items": [
                    {
                        "name": item.get("name", ""),
                        "amount": item.get("amount", ""),
                        "confidence": round(float(item.get("confidence", item.get("weight", 0.0)) or 0.0), 3),
                        "trace": item.get("confidenceTrace", {}),
                    }
                    for item in candidate.items
                ],
                "sections": candidate.section_extraction.get("confidence", {}),
                "ontology": candidate.ontology.get("confidence", {}),
                "ocr": candidate.confidence.get("ocr", 0.0),
                "arithmetic": candidate.section_extraction.get("validation", {}).get("arithmeticChecks", []),
                "semantic": candidate.confidence,
            },
            "receiptEntities": candidate.entities,
            "semanticBlocks": [block.to_dict() for block in candidate.semantic_blocks],
            "tables": candidate.tables,
            "tableGraph": candidate.section_extraction.get("tableGraph", {}),
            "graph": candidate.graph,
        }
