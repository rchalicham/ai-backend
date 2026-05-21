from __future__ import annotations

import hashlib
import re
from collections import Counter
from dataclasses import dataclass, field
from typing import Any

from services.receipt_entity_extraction import ReceiptEntityExtractionEngine

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
    def suppress(self, lines: list[ReconstructedLine]) -> list[ReconstructedLine]:
        seen: dict[str, ReconstructedLine] = {}
        output: list[ReconstructedLine] = []
        subtotal_seen = False
        for line in lines:
            text = _compact_text(line.text)
            if not text:
                continue
            upper = text.upper()
            if subtotal_seen and self._looks_like_item_line(text):
                signature = _line_signature(text)
                if signature in seen:
                    continue
            if re.search(r"\bSUB\s*TOTAL\b|\bSUBTOTAL\b", upper):
                subtotal_seen = True
            signature = _line_signature(text)
            current = seen.get(signature)
            if current and current.confidence >= line.confidence:
                continue
            if current and current in output:
                output.remove(current)
            seen[signature] = line
            output.append(line)
        return output

    def _looks_like_item_line(self, text: str) -> bool:
        upper = text.upper()
        return bool(re.search(r"[A-Za-z]{3,}", text) and re.search(r"\d{1,5}(?:[., ]\d{2})\b", text)) and not any(term in upper for term in RECEIPT_LEVEL_TERMS)


class MerchantNormalizer:
    PHARMACY_TERMS = ("PHARMACY", "PHARMA", "DRUG", "RX", "PRESCRIPTION")
    KNOWN = {
        "LOWES": ("LOWE'S HOME CENTERS, LLC", ("HOME CENTER", "HOME CENTERS", "PENT COP", "HOME CENFERS")),
        "LOWE'S": ("LOWE'S HOME CENTERS, LLC", ("HOME CENTER", "HOME CENTERS", "PENT COP", "HOME CENFERS")),
        "KADAI INDIAN KITCHEN": ("KADAI INDIAN KITCHEN", ("INDIAN", "KITCHEN")),
        "FRESHTHYME": ("Fresh Thyme Market", ("FRESH THYME", "FRESH THYME MARKET")),
        "FRESH THYME": ("Fresh Thyme Market", ("FRESHTHYME", "FRESH THYME MARKET")),
        "THE HOME DEPOT": ("Home Depot", ("HOMEDEPOT",)),
        "HOME DEPOT": ("Home Depot", ("HOMEDEPOT",)),
        "TARGET": ("Target", ("TGT",)),
        "WALMART": ("Walmart", ("WAL MART", "WAL-MART")),
        "COSTCO": ("Costco", ("WHOLESALE",)),
        "CVS/PHARMACY": ("CVS Pharmacy", ("CVS PHARMACY", "CVS", "C V S", "CV5", "CYS", "CVS PHARMA", "PHARMACY", "PHARMA", "4140 ROAD 101", "478-4612", "978-4612")),
        "CVS PHARMACY": ("CVS Pharmacy", ("CVS/PHARMACY", "CVS", "C V S", "CV5", "CYS", "CVS PHARMA", "PHARMACY", "PHARMA", "4140 ROAD 101", "478-4612", "978-4612")),
        "CVS": ("CVS Pharmacy", ("CVS/PHARMACY", "CVS PHARMACY", "C V S", "CV5", "CYS", "PHARMACY", "PHARMA", "4140 ROAD 101", "478-4612", "978-4612")),
    }
    DOMAIN_MERCHANTS = {
        "FRESHTHYME.COM": "Fresh Thyme Market",
        "FRESHTHYME": "Fresh Thyme Market",
        "WALMART.COM": "Walmart",
        "TARGET.COM": "Target",
        "HOMEDEPOT.COM": "Home Depot",
        "LOWES.COM": "LOWE'S HOME CENTERS, LLC",
        "CVS.COM": "CVS Pharmacy",
    }
    HIGH_CONFIDENCE_THRESHOLD = 0.82
    LOW_CONFIDENCE_PRESERVE_THRESHOLD = 0.72
    RECEIPT_NOISE = re.compile(
        r"\b(?:REG|TRN|CSHR|STR|STORE|SUBTOTAL|TOTAL|TAX|VISA|CREDIT|DEBIT|APPROVED|AUTH|REF|AID|TERMINAL|"
        r"CHANGE|RETURN|POLICY|RECEIPT|DATE|PHARMACY\s*:\s*\d|NO SIGNATURE)\b",
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
            "merchant": _compact_text(candidate),
            "confidence": 0.0,
            "source": "empty",
            "rawMerchant": raw_merchant,
            "selectedCandidate": top,
            "evidence": [],
            "rejectedCandidates": rejected,
            "preservedRawOcr": False,
        }

    def _raw_ocr_merchant(self, raw_text: str, candidate: str = "") -> str:
        if _compact_text(candidate) and not self.RECEIPT_NOISE.search(candidate):
            return self._title_preserving_acronyms(_compact_text(candidate))
        first_lines = [_compact_text(line) for line in raw_text.splitlines()[:8] if _compact_text(line)]
        for line in first_lines:
            domain = self._domain_merchant_from_line(line)
            if domain:
                return domain
            if self._looks_like_header_merchant(line):
                return self._title_preserving_acronyms(line)
        return ""

    def candidates(self, raw_text: str, candidate: str = "") -> list[dict[str, Any]]:
        combined = _compact_text(f"{candidate}\n{raw_text}")
        upper_combined = combined.upper()
        raw_upper = _compact_text(raw_text).upper()
        generated_candidates = self.generate_candidates(raw_text, candidate)
        text_candidates = [item["text"] for item in generated_candidates]
        scored: list[dict[str, Any]] = []
        for domain, merchant in self._domain_evidence(upper_combined):
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
        for match in re.finditer(r"\b(?:WWW\.)?([A-Z0-9][A-Z0-9-]{2,35})\.(COM|NET|ORG)\b", upper_combined):
            domain = f"{match.group(1)}.{match.group(2)}"
            merchant = self.DOMAIN_MERCHANTS.get(domain) or self.DOMAIN_MERCHANTS.get(match.group(1))
            if merchant:
                found.append((domain, merchant))
        return found

    def _domain_merchant_from_line(self, line: str) -> str:
        for domain, merchant in self._domain_evidence(line.upper()):
            return merchant
        return ""

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
        recovered: list[str] = []
        upper = "\n".join(lines[:12]).upper()
        canonical = self._canonical(upper)
        if re.search(r"\bC\s*V\s*S\b|\bC[VU][S5]\b", canonical) and any(term in canonical for term in self.PHARMACY_TERMS):
            recovered.append("CVS Pharmacy")
        if any(term in canonical for term in self.PHARMACY_TERMS) and "ROAD 101" in canonical:
            recovered.append("CVS Pharmacy")
        return recovered

    def _address_phone_score(self, merchant: str, combined: str, reasons: list[str], evidence: list[dict[str, Any]]) -> float:
        if merchant == "CVS Pharmacy" and re.search(r"\b4140\s+ROAD\s+101\b", combined) and re.search(r"\bPLY(?:MOUTH|NQUTH)\b", combined):
            reasons.append("address:4140 ROAD 101 PLYMOUTH")
            evidence.append({"type": "address_match", "value": "4140 ROAD 101 PLYMOUTH", "weight": 0.86, "confidence": 0.9})
            return 0.9
        if merchant == "CVS Pharmacy" and re.search(r"\b(?:478|978)[-.\s]?4612\b", combined):
            reasons.append("phone:pharmacy-store")
            evidence.append({"type": "phone_match", "value": "478/978-4612", "weight": 0.84, "confidence": 0.84})
            return 0.84
        if merchant == "CVS Pharmacy" and re.search(r"\b4140\s+ROAD\s+101\b", combined) and any(term in combined for term in self.PHARMACY_TERMS):
            reasons.append("address:pharmacy+4140 ROAD 101")
            evidence.append({"type": "address_match", "value": "pharmacy+4140 ROAD 101", "weight": 0.82, "confidence": 0.88})
            return 0.88
        return 0.0

    def _semantic_store_score(self, merchant: str, combined: str, reasons: list[str], evidence: list[dict[str, Any]]) -> float:
        if merchant == "CVS Pharmacy":
            has_cvs_like = self._similarity("CVS", combined[:160]) >= 72 or re.search(r"\bC\s*V\s*S\b|\bC[VU][S5]\b", combined)
            has_pharmacy = any(term in combined for term in self.PHARMACY_TERMS) or "PHARHACY" in combined or "PHARNACY" in combined
            if has_cvs_like and has_pharmacy:
                reasons.append("semantic:cvs+pharmacy")
                evidence.append({"type": "semantic_validation", "value": "cvs+pharmacy", "weight": 0.65, "confidence": 0.92})
                return 0.92
            if has_pharmacy and "ROAD 101" in combined:
                reasons.append("semantic:pharmacy+known_address")
                evidence.append({"type": "semantic_validation", "value": "pharmacy+known_address", "weight": 0.62, "confidence": 0.86})
                return 0.86
        return 0.0

    def _partial_ocr_score(self, merchant: str, windows: list[dict[str, Any]], combined: str, reasons: list[str], evidence: list[dict[str, Any]]) -> float:
        if merchant != "CVS Pharmacy":
            return 0.0
        canonical_windows = " ".join(self._canonical(item["text"]) for item in windows[:12])
        has_cvs_fragment = bool(re.search(r"\bC\s*V\s*S\b|\bCVS\b|\bCV5\b|\bCYS\b", canonical_windows))
        has_store_type = any(term in canonical_windows or term in combined for term in self.PHARMACY_TERMS)
        if has_cvs_fragment and has_store_type:
            reasons.append("partial_ocr:cvs_fragment+store_type")
            evidence.append({"type": "logo_or_header_ocr", "value": "cvs_fragment+store_type", "weight": 0.74, "confidence": 0.9})
            return 0.9
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
            "CV5": "CVS",
            "CYS": "CVS",
            "C V S": "CVS",
            "PLYNQUTH": "PLYMOUTH",
        }
        for wrong, right in replacements.items():
            text = text.replace(wrong, right)
        return re.sub(r"[^A-Z0-9 ]+", " ", text)

    def _looks_like_header_merchant(self, line: str) -> bool:
        upper = line.upper()
        return (
            bool(re.search(r"[A-Za-z]{3,}", line))
            and not re.search(r"\d{4,}", line)
            and not self.RECEIPT_NOISE.search(upper)
        )

    def _title_preserving_acronyms(self, value: str) -> str:
        words = []
        for word in value.split():
            words.append(word if word.isupper() and len(word) <= 4 else word.title())
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

    def reconstruct(self, lines: list[ReconstructedLine], items: list[dict[str, Any]], facts: dict[str, str]) -> list[dict[str, Any]]:
        tables: list[dict[str, Any]] = []
        if items:
            tables.append({
                "id": "items-table",
                "kind": "items",
                "headers": ["name", "qty", "amount"],
                "confidence": round(sum(line.confidence for line in lines) / max(len(lines), 1), 3),
                "rows": [
                    {
                        "lineIndex": self._find_line_index(lines, item.get("name", ""), item.get("amount", "")),
                        "name": item.get("name", ""),
                        "qty": item.get("qty") or item.get("count") or "1",
                        "amount": item.get("amount") or item.get("price") or "",
                        "confidence": round(float(item.get("weight", 1.0) or 1.0), 3),
                    }
                    for item in items
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

    def _find_line_index(self, lines: list[ReconstructedLine], name: str, amount: str) -> int | None:
        name_key = re.sub(r"[^A-Z0-9]+", "", str(name or "").upper())
        amount_variants = {str(amount or ""), str(amount or "").replace(".", " "), str(amount or "").replace(".", ",")}
        for index, line in enumerate(lines):
            line_key = re.sub(r"[^A-Z0-9]+", "", line.text.upper())
            if name_key and name_key in line_key and any(variant and variant in line.text for variant in amount_variants):
                return index
        return None


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
        entity_result = self.entities.extract(raw_text=normalized_text or raw_text, lines=[line.text for line in reconstructed], ocr_blocks=ocr_blocks)
        items, facts = self.parser.parse(reconstructed)
        parser_json = parser_json or {}
        entity_fields = entity_result.get("fields", {})
        merchant_resolution = self.merchants.resolve(
            normalized_text or raw_text,
            str(entity_fields.get("merchant") or parser_json.get("company") or parser_json.get("storeName") or ""),
        )
        merchant = merchant_resolution["merchant"]
        validation = self.validator.validate(items, facts, parser_json)
        confidence = self.confidence.score(reconstructed, items, validation, merchant)
        retry_plan = self.retry.plan(confidence, validation)
        regions = self.clusterer.cluster(reconstructed)
        semantic_blocks = self.blocks.build(reconstructed, regions)
        tables = self.tables.reconstruct(reconstructed, items, facts)
        graph = self.graph.build(merchant, items, facts, semantic_blocks)
        layout_json = self.layout.summarize(
            reconstructed,
            regions,
            semantic_blocks,
            tables,
            graph,
            validation["warnings"],
        )
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
            "paymentMethod": entity_fields.get("paymentMethod", ""),
            "cardType": entity_fields.get("cardType", ""),
            "cardUsed": entity_fields.get("cardUsed", ""),
            "lastFour": entity_fields.get("lastFour", ""),
            "cardLast4": entity_fields.get("cardLast4", ""),
            "approvalCode": entity_fields.get("approvalCode", ""),
            "paymentCard": {
                "brand": entity_fields.get("cardUsed", ""),
                "last4": entity_fields.get("cardLast4", ""),
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
                    "confidence": round(float(item.get("weight", 1.0) or 1.0), 3),
                }
                for index, item in enumerate(candidate.items)
            ],
            "facts": {
                "subtotal": candidate.facts.get("subtotal", ""),
                "tax": candidate.facts.get("tax", ""),
                "tip": candidate.facts.get("tip", ""),
                "total": candidate.facts.get("total", ""),
            },
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
            "receiptEntities": candidate.entities,
            "semanticBlocks": [block.to_dict() for block in candidate.semantic_blocks],
            "tables": candidate.tables,
            "graph": candidate.graph,
        }
