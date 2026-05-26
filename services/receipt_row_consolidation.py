from __future__ import annotations

import itertools
import logging
import re
from dataclasses import dataclass, field
from typing import Any

try:
    from rapidfuzz import fuzz
except Exception:  # pragma: no cover - exercised only when dependency is unavailable.
    fuzz = None

from services.receipt_intelligence import MerchantNormalizer
from services.receipt_entity_extraction import ReceiptEntityExtractionEngine
from services.receipt_section_engine import ReceiptSectionExtractionEngine


logger = logging.getLogger(__name__)

RECEIPT_TOTAL_TERMS = (
    "SUBTOTAL", "SUB TOTAL", "TOTAL", "TAX", "TIP", "CHANGE", "BALANCE", "AMOUNT",
    "PAYMENT", "CASH", "CREDIT", "DEBIT", "VISA", "MASTERCARD", "AMEX", "DISCOVER",
    "AUTH", "APPROVED", "TERMINAL", "TRANS", "TRAN", "TRANSACTION", "CARD", "AID",
    "TRAN TYPE", "SIGNATURE", "CVM", "TVR", "TSI", "REF",
)

RECEIPT_FOOTER_TERMS = (
    "THANK", "SURVEY", "FEEDBACK", "RETURN POLICY", "COME AGAIN", "SAVINGS",
    "ITEM COUNT", "SOLD ITEM", "STORE", "PHARMACY", "ROAD", "STREET", "PLYMOUTH",
    "BARCODE", "COUPON", "REWARD", "YOU SAVED", "TOTAL DISCOUNTS",
)

RECEIPT_LEGAL_PROMO_TERMS = (
    "SWEEPSTAKES", "NO PURCHASE", "VOID WHERE", "PROHIBITED", "OFFICIAL RULES",
    "FRESH THYME GIFT", "GIFT CARD", "ENTER TO WIN", "SURVEY", "PROVIDE SPECIFIC",
    "PURCHASE RECEIPT", "GOOD LUCK",
)

RECEIPT_DEPARTMENT_TERMS = ("DAIRY", "DATINY", "GROCERY", "PRODUCE")

PRODUCT_STOPWORDS = {
    "REG", "TRN", "CSHR", "STR", "ROAD", "NORTH", "STORE", "PHARMACY", "EA",
}

RECEIPT_LEVEL_CANONICAL_TERMS = (
    "TOTAL", "SUBTOTAL", "TAX", "TIP", "CHARGE", "PAYMENT", "CHANGE", "BALANCE",
    "VISA", "MASTERCARD", "AMEX", "DISCOVER", "AUTH", "CARD", "CASH",
)
RECEIPT_LEVEL_OCR_MUTATIONS = {
    "GATT", "HARGE", "T0TAL", "TOTAI", "TQTAL", "SUBT0TAL", "CHARGF", "CHAR6E",
}


@dataclass
class ReceiptSection:
    kind: str
    start: int
    end: int
    confidence: float = 0.0
    bbox: dict[str, float] | None = None


@dataclass
class CandidateRow:
    source: str
    name: str
    amount: str
    qty: str = "1"
    confidence: float = 0.5
    bbox: dict[str, float] | None = None
    raw: dict[str, Any] = field(default_factory=dict)
    section: str = "unknown"
    reasons: list[str] = field(default_factory=list)
    line_index: int | None = None

    @property
    def amount_value(self) -> float:
        return _numeric_amount(self.amount)

    @property
    def y(self) -> float | None:
        if isinstance(self.bbox, dict):
            y = self.bbox.get("y", self.bbox.get("top"))
            try:
                return float(y)
            except (TypeError, ValueError):
                return None
        if isinstance(self.raw, dict):
            y = self.raw.get("y")
            try:
                return float(y)
            except (TypeError, ValueError):
                return None
        return None


def _compact(value: Any) -> str:
    return re.sub(r"\s+", " ", str(value or "")).strip()


def _amount(value: Any) -> str:
    text = re.sub(r"(?<=\d):(?=\d{2}\b)", ".", str(value or "")).replace("$", "").replace(",", ".")
    match = re.search(r"-?\d{1,6}(?:\.\d{2})(?=\b|[A-Z])", text, flags=re.IGNORECASE)
    if match:
        return match.group(0)
    match = re.search(r"-?\d{1,6}\b", text)
    return match.group(0) if match else ""


def _numeric_amount(value: Any) -> float:
    parsed = _amount(value)
    try:
        return float(parsed) if parsed else 0.0
    except ValueError:
        return 0.0


def _canonical_name(value: str) -> str:
    text = _compact(value).upper()
    text = re.sub(r"<[^>]+>", " ", text)
    text = re.sub(r"[\[\]{}()\"']", " ", text)
    text = re.sub(r"[^A-Z0-9&./ -]+", " ", text)
    text = re.sub(r"\b\d{5,}\b", " ", text)
    tokens = []
    for token in text.split():
        normalized = re.sub(r"[^A-Z0-9]", "", token)
        if not normalized:
            continue
        if normalized in PRODUCT_STOPWORDS:
            continue
        if normalized.isdigit():
            continue
        tokens.append(normalized)
    return " ".join(tokens)


def _similarity(left: str, right: str) -> float:
    left_key = _canonical_name(left)
    right_key = _canonical_name(right)
    if not left_key or not right_key:
        return 0.0
    if fuzz is not None:
        return float(fuzz.token_set_ratio(left_key, right_key))
    left_tokens = set(left_key.split())
    right_tokens = set(right_key.split())
    if not left_tokens or not right_tokens:
        return 0.0
    return 100.0 * len(left_tokens & right_tokens) / len(left_tokens | right_tokens)


class ReceiptSectionSegmenter:
    def segment(self, lines: list[str], boxes: list[dict[str, Any]] | None = None) -> list[ReceiptSection]:
        if boxes:
            return self._from_boxes(boxes)
        if not lines:
            return []
        sections: list[ReceiptSection] = []
        current_kind = self._classify_line(lines[0], 0)
        start = 0
        for index, line in enumerate(lines[1:], start=1):
            kind = self._classify_line(line, index)
            if kind != current_kind:
                sections.append(ReceiptSection(current_kind, start, index - 1, confidence=0.7))
                start = index
                current_kind = kind
        sections.append(ReceiptSection(current_kind, start, len(lines) - 1, confidence=0.7))
        return self._coalesce(sections)

    def locate_text(self, text: str, lines: list[str], sections: list[ReceiptSection]) -> str:
        key = _canonical_name(text)
        if not key:
            return "unknown"
        for index, line in enumerate(lines):
            if key and key in _canonical_name(line):
                for section in sections:
                    if section.start <= index <= section.end:
                        return section.kind
        return "unknown"

    def _from_boxes(self, boxes: list[dict[str, Any]]) -> list[ReceiptSection]:
        ordered = sorted(
            [box for box in boxes if isinstance(box, dict) and _compact(box.get("text") or box.get("value"))],
            key=lambda box: float(box.get("y", (box.get("bbox") or {}).get("y", 0)) or 0),
        )
        lines = [_compact(box.get("text") or box.get("value")) for box in ordered]
        return self.segment(lines)

    def _classify_line(self, line: str, index: int) -> str:
        upper = _compact(line).upper()
        if index <= 4 and re.search(r"[A-Z]{3,}", upper) and not re.search(r"\d{1,6}(?:[.,]\d{2})", upper):
            return "header"
        if any(term in upper for term in RECEIPT_TOTAL_TERMS):
            return "totals"
        if any(term in upper for term in RECEIPT_FOOTER_TERMS):
            return "footer"
        if re.search(r"[A-Z]{3,}", upper) and re.search(r"\d{1,6}(?:[.,]\d{2})", upper):
            return "items"
        return "unknown"

    def _coalesce(self, sections: list[ReceiptSection]) -> list[ReceiptSection]:
        if not sections:
            return []
        output = [sections[0]]
        for section in sections[1:]:
            previous = output[-1]
            if previous.kind == section.kind:
                previous.end = section.end
                previous.confidence = max(previous.confidence, section.confidence)
            else:
                output.append(section)
        return output


class ReceiptCandidateExtractor:
    def extract(
        self,
        donut: dict[str, Any],
        lines: list[str],
        sections: list[ReceiptSection],
        segmenter: ReceiptSectionSegmenter,
        section_items: list[dict[str, Any]] | None = None,
        ocr_blocks: list[dict[str, Any]] | None = None,
    ) -> list[CandidateRow]:
        candidates: list[CandidateRow] = []
        for index, item in enumerate(donut.get("items") or []):
            if not isinstance(item, dict):
                continue
            row = CandidateRow(
                source="donut.items",
                name=_compact(item.get("name") or item.get("description") or item.get("item")),
                amount=_amount(item.get("amount") or item.get("price") or item.get("total")),
                qty=self._qty(item.get("qty") or item.get("count") or item.get("quantity")),
                confidence=float(item.get("confidence") or donut.get("confidence") or 0.55),
                bbox=item.get("bbox") if isinstance(item.get("bbox"), dict) else None,
                raw=item,
                line_index=item.get("lineIndex") if isinstance(item.get("lineIndex"), int) else None,
            )
            row.section = segmenter.locate_text(row.name, lines, sections)
            candidates.append(row)

        raw = donut.get("raw") if isinstance(donut.get("raw"), dict) else {}
        self._extract_menu(raw, candidates, lines, sections, segmenter)
        self._extract_section_items(section_items or [], candidates)
        self._extract_ocr_box_rows(ocr_blocks or [], candidates, lines, sections)
        pending_description: tuple[str, int] | None = None
        for index, line in enumerate(lines):
            match = self._line_item_match(line)
            if not match:
                pending = self._pending_description(line)
                if pending:
                    pending_description = (pending, index)
                continue
            if pending_description and (self._amount_only_or_noise_price_line(line) or self._weighted_price_line(line)):
                match = {"name": pending_description[0], "amount": match["amount"]}
                pending_description = None
            else:
                pending_description = None
            section = next((section.kind for section in sections if section.start <= index <= section.end), "unknown")
            candidates.append(CandidateRow(
                source="ocr.line",
                name=_compact(match["name"]),
                amount=_amount(match["amount"]),
                confidence=0.64 if section == "items" else 0.42,
                raw={"line": line, "lineIndex": index},
                section=section,
                line_index=index,
            ))
        return candidates

    def _pending_description(self, line: str) -> str:
        text = _compact(line)
        upper = text.upper()
        if any(term in upper for term in RECEIPT_TOTAL_TERMS + RECEIPT_FOOTER_TERMS + RECEIPT_LEGAL_PROMO_TERMS):
            return ""
        if re.search(r"\d{1,6}(?:[.,]\d{2})", text):
            return ""
        cleaned = self._clean_ocr_item_name(text)
        alpha = len(re.findall(r"[A-Za-z]", cleaned))
        if alpha >= 5 and not re.search(r"\b(?:APPROVED|PURCHASE|AMOUNT|TRAN|VISA|AID)\b", cleaned, flags=re.IGNORECASE):
            return cleaned
        return ""

    def _amount_only_or_noise_price_line(self, line: str) -> bool:
        text = _compact(line)
        return bool(re.fullmatch(r"[^A-Za-z]{0,12}\d{1,6}(?:[.,]\d{2})[^A-Za-z]{0,12}", text))

    def _weighted_price_line(self, line: str) -> bool:
        return bool(re.search(r"\b\d+(?:[.,]\d+)?\s*(?:LB|LBS)\s*@", _compact(line).upper()))

    def _line_item_match(self, line: str) -> dict[str, str] | None:
        text = _compact(line)
        upper = text.upper()
        if any(term in upper for term in RECEIPT_LEGAL_PROMO_TERMS):
            return None
        if any(term in upper for term in RECEIPT_TOTAL_TERMS + RECEIPT_FOOTER_TERMS):
            return None
        if any(term in upper for term in ("APPROVED", "AUTH", "TRAN ", "TRAN:", "AMOUNT:", "AID:", "VISA RESP", "XXXXXXXX")):
            return None
        if re.search(r"\b[A-Z]{2}\s+\d{5}(?:-\d{4})?\b", upper) or any(term in upper for term in (" DR", " DRIVE", " ST ", " STREET", " ROAD", " AVE", " AVENUE")):
            return None
        amounts = list(re.finditer(r"-?\d{1,6}(?:[.,:]\d{2})", text))
        if not amounts:
            amounts = list(re.finditer(r"\b\d{4,5}\b", text))
        if len(amounts) > 1 and not re.search(r"\b\d+(?:[.,]\d+)?\s*(?:LB|LBS)\s*@", upper):
            return None
        if not amounts:
            return None
        amount_match = amounts[-1]
        trailing = text[amount_match.end():].strip()
        if re.search(r"\d{2,}", trailing):
            return None
        name = text[:amount_match.start()].strip(" -:|\\/*'\"“”[](){}")
        if re.search(r"\b\d+(?:[.,]\d+)?\s*(?:LB|LBS)\s*@", upper):
            previous_name = self._pending_description(text)
            if previous_name:
                name = previous_name
        name = self._clean_ocr_item_name(name)
        if len(re.findall(r"[A-Za-z]", name)) < 3 and not re.search(r"\bO\s*/?\s*N\b", name, flags=re.IGNORECASE):
            return None
        return {"name": name, "amount": self._normalize_ocr_line_amount(amount_match.group(0))}

    def _normalize_ocr_line_amount(self, value: str) -> str:
        text = re.sub(r"(?<=\d):(?=\d{2}\b)", ".", str(value or "")).replace(",", ".")
        if "." in text:
            return text
        if re.fullmatch(r"\d{4,5}", text):
            whole = text[:-2]
            cents = text[-2:]
            if len(text) == 5:
                whole = text[:2]
            return f"{int(whole)}.{cents}"
        return text

    def _clean_ocr_item_name(self, name: str) -> str:
        cleaned = _compact(name)
        cleaned = re.sub(r"^[^A-Za-z]+", "", cleaned)
        cleaned = re.sub(r"^(?:O|0)\s*[-:]\s*(?=[A-Z]{2,})", "", cleaned, flags=re.IGNORECASE)
        sku_match = re.match(r"^.{0,24}?\b\d{4,}\s+(.+)$", cleaned)
        if sku_match:
            cleaned = sku_match.group(1)
        cleaned = self._strip_leading_ocr_noise_tokens(cleaned)
        cleaned = re.sub(r"^(?:(?:[A-Za-z]{1,2}|[A-Za-z]?[}\\]\\\\/|]+)\\s+){0,5}\\d{4,}\\s+", "", cleaned)
        cleaned = re.sub(r"^(?:E\+?|F\]?|S\]?|ST\}:|CF|\*)\s+", "", cleaned, flags=re.IGNORECASE)
        cleaned = re.sub(r"^(?:\d{4,}|0{4,}\d*)\s+", "", cleaned)
        cleaned = re.sub(r"^(?:/\)?\d{4,}\s*)+", "", cleaned)
        cleaned = re.sub(r"^[A-Z]?\s*\d{4,}\s+", "", cleaned)
        cleaned = re.sub(r"\s*[=|\\/]+\s*$", "", cleaned)
        return _compact(cleaned)

    def _strip_leading_ocr_noise_tokens(self, value: str) -> str:
        tokens = _compact(value).split()
        noisy = {"E", "E+", "EY", "EL", "HE", "SH", "OE", "SA", "F", "CF", "O", "0"}
        while tokens:
            normalized = re.sub(r"[^A-Z+]", "", tokens[0].upper())
            if normalized in noisy or re.fullmatch(r"\d{3,}", tokens[0]):
                tokens.pop(0)
                continue
            break
        return " ".join(tokens)

    def _extract_ocr_box_rows(
        self,
        boxes: list[dict[str, Any]],
        candidates: list[CandidateRow],
        lines: list[str],
        sections: list[ReceiptSection],
    ) -> None:
        normalized_boxes = []
        for box in boxes:
            if not isinstance(box, dict):
                continue
            text = _compact(box.get("text") or box.get("value"))
            if not text:
                continue
            bbox = box.get("bbox") if isinstance(box.get("bbox"), dict) else {}
            try:
                x = float(box.get("x", bbox.get("x", bbox.get("left", 0))) or 0)
                y = float(box.get("y", bbox.get("y", bbox.get("top", 0))) or 0)
                width = float(box.get("width", bbox.get("width", bbox.get("w", 0))) or 0)
                height = float(box.get("height", bbox.get("height", bbox.get("h", 12))) or 12)
                confidence = float(box.get("confidence", box.get("conf", 0.62)) or 0.62)
            except (TypeError, ValueError):
                continue
            normalized_boxes.append({
                "text": text,
                "x": x,
                "y": y,
                "width": width,
                "height": height,
                "confidence": confidence,
                "raw": box,
            })
        if not normalized_boxes:
            return
        normalized_boxes.sort(key=lambda item: (item["y"], item["x"]))
        rows: list[list[dict[str, Any]]] = []
        for box in normalized_boxes:
            target = None
            for row in rows:
                row_y = sum(item["y"] for item in row) / max(len(row), 1)
                row_height = max(item["height"] for item in row)
                if abs(row_y - box["y"]) <= max(10.0, row_height * 0.72):
                    target = row
                    break
            if target is None:
                rows.append([box])
            else:
                target.append(box)
        for row_index, row in enumerate(rows):
            ordered = sorted(row, key=lambda item: item["x"])
            text = _compact(" ".join(item["text"] for item in ordered))
            match = self._line_item_match(text)
            if not match:
                continue
            y_values = [item["y"] for item in ordered]
            x_values = [item["x"] for item in ordered]
            right_values = [item["x"] + item["width"] for item in ordered]
            bottom_values = [item["y"] + item["height"] for item in ordered]
            line_index = self._nearest_line_index(text, lines)
            section = next((section.kind for section in sections if line_index is not None and section.start <= line_index <= section.end), "items")
            candidates.append(CandidateRow(
                source="ocr.box.row",
                name=_compact(match["name"]),
                amount=_amount(match["amount"]),
                confidence=sum(item["confidence"] for item in ordered) / max(len(ordered), 1),
                bbox={
                    "x": min(x_values),
                    "y": min(y_values),
                    "width": max(right_values) - min(x_values),
                    "height": max(bottom_values) - min(y_values),
                },
                raw={"line": text, "boxCount": len(ordered), "rowIndex": row_index},
                section=section,
                line_index=line_index,
            ))

    def _nearest_line_index(self, text: str, lines: list[str]) -> int | None:
        key = _canonical_name(text)
        if not key:
            return None
        best_index = None
        best_score = 0.0
        for index, line in enumerate(lines):
            score = _similarity(key, line)
            if score > best_score:
                best_score = score
                best_index = index
        return best_index if best_score >= 78 else None

    def _extract_section_items(self, items: list[dict[str, Any]], candidates: list[CandidateRow]) -> None:
        for item in items:
            if not isinstance(item, dict):
                continue
            candidates.append(CandidateRow(
                source="section.items",
                name=self._clean_ocr_item_name(item.get("name") or item.get("description") or item.get("item")),
                amount=_amount(item.get("amount") or item.get("price") or item.get("total")),
                qty=self._qty(item.get("qty") or item.get("count") or item.get("quantity")),
                confidence=float(item.get("confidence") or 0.68),
                raw=item,
                section="items",
            ))

    def _extract_menu(
        self,
        raw: dict[str, Any],
        candidates: list[CandidateRow],
        lines: list[str],
        sections: list[ReceiptSection],
        segmenter: ReceiptSectionSegmenter,
    ) -> None:
        menu = raw.get("menu") or raw.get("items") or []
        if isinstance(menu, dict):
            menu = [menu]
        if not isinstance(menu, list):
            return
        for item in menu:
            if not isinstance(item, dict):
                continue
            name = item.get("nm") or item.get("name") or item.get("description") or item.get("item")
            amount = item.get("price") or item.get("amount") or item.get("totalprice") or item.get("subtotal")
            if isinstance(name, list):
                name = " ".join(str(part) for part in name)
            if isinstance(amount, dict):
                amount = amount.get("text") or amount.get("value") or amount.get("price")
            row = CandidateRow(
                source="donut.raw.menu",
                name=_compact(name),
                amount=_amount(amount),
                qty=self._qty(item.get("cnt") or item.get("qty") or item.get("quantity")),
                confidence=0.58,
                bbox=item.get("bbox") if isinstance(item.get("bbox"), dict) else None,
                raw=item,
            )
            row.section = segmenter.locate_text(row.name, lines, sections)
            candidates.append(row)

    def _qty(self, value: Any) -> str:
        match = re.search(r"\d+(?:[.,]\d+)?", str(value or ""))
        if not match:
            return "1"
        qty = match.group(0).replace(",", ".")
        try:
            return qty if float(qty) > 0 else "1"
        except ValueError:
            return "1"


class ReceiptRowValidator:
    def validate(self, row: CandidateRow, facts: dict[str, str]) -> tuple[bool, list[str], float]:
        reasons: list[str] = []
        name = _compact(row.name)
        canonical = _canonical_name(name)
        upper = name.upper()
        if row.confidence < 0.42:
            reasons.append("low_source_confidence")
        if not row.amount or row.amount_value <= 0:
            reasons.append("missing_or_zero_amount")
        short_retail_code = bool(re.search(r"\bO\s*/?\s*N\b", upper))
        if not short_retail_code and (len(canonical) < 3 or not re.search(r"[A-Z]{3,}", canonical)):
            reasons.append("invalid_product_name")
        if any(term in upper for term in RECEIPT_TOTAL_TERMS):
            reasons.append("receipt_level_term")
        if re.fullmatch(r"(?:TRAN\s+)?TYPE:?\s+SALE", upper) or canonical == "TYPE SALE":
            reasons.append("receipt_level_term")
        if any(term in upper for term in ("YOU SAVED", "TOTAL DISCOUNTS", "SAVINGS TODAY")):
            reasons.append("discount_summary_row")
        if self._near_receipt_level_term(canonical):
            reasons.append("ocr_mutation_of_receipt_level_term")
        if any(term in upper for term in RECEIPT_FOOTER_TERMS) and len(canonical.split()) > 4:
            reasons.append("footer_or_address_text")
        if self._survey_or_barcode_row(upper):
            reasons.append("survey_or_barcode_numeric_row")
        if any(token in upper for token in ("REG#", "TRN#", "CSHR", "STR#", "PHARMACY:", "STORE:", "TRAN TYPE", "SIGNATURE REQUIRED", "CVM:", "TVR", "TSI")):
            reasons.append("terminal_or_store_metadata")
        if re.search(r"\[|\]|<S_", name, flags=re.IGNORECASE):
            reasons.append("serialized_or_tagged_text")
        alpha = len(re.findall(r"[A-Za-z]", name))
        non_space = len(re.sub(r"\s+", "", name))
        if non_space and alpha / non_space < 0.45:
            reasons.append("low_alpha_ratio")
        if row.section in {"totals", "payment", "footer"}:
            reasons.append(f"excluded_section_{row.section}")
        receipt_amounts = {_amount(value) for value in facts.values() if _amount(value)}
        if row.amount in receipt_amounts and len(canonical.split()) <= 2 and row.confidence < 0.75:
            reasons.append("weak_name_matches_receipt_total")
        if not short_retail_code and len(canonical.split()) == 1 and len(canonical) <= 5:
            reasons.append("short_single_token_product_name")
        tokens = canonical.split()
        if len(tokens) >= 2 and all(len(token) <= 3 for token in tokens):
            reasons.append("weak_short_ocr_noise")
        score = self.score(row, reasons)
        hard_rejects = {
            "receipt_level_term",
            "ocr_mutation_of_receipt_level_term",
            "footer_or_address_text",
            "serialized_or_tagged_text",
            "terminal_or_store_metadata",
            "invalid_product_name",
            "missing_or_zero_amount",
            "survey_or_barcode_numeric_row",
            "low_source_confidence",
            "discount_summary_row",
            "weak_short_ocr_noise",
        }
        if "weak_name_matches_receipt_total" in reasons and "short_single_token_product_name" in reasons:
            hard_rejects.add("weak_name_matches_receipt_total")
        long_single_token_product = len(canonical.split()) == 1 and len(canonical) >= 8 and re.search(r"[A-Z]{4,}", canonical)
        return (
            (score >= 0.52 or (long_single_token_product and score >= 0.47) or (short_retail_code and score >= 0.25))
            and not any(reason.startswith("excluded_section") for reason in reasons)
            and not any(reason in hard_rejects for reason in reasons)
        ), reasons, score

    def score(self, row: CandidateRow, reasons: list[str]) -> float:
        canonical = _canonical_name(row.name)
        token_count = len(canonical.split())
        score = min(0.35, row.confidence * 0.28)
        score += 0.22 if row.amount_value > 0 else 0
        score += min(0.2, token_count * 0.06)
        score += 0.12 if row.section == "items" else 0
        score += 0.08 if any(len(token) >= 4 for token in canonical.split()) else 0
        score -= 0.16 * len(set(reasons))
        return round(max(0.0, min(1.0, score)), 3)

    def _near_receipt_level_term(self, canonical: str) -> bool:
        first = canonical.split()[0] if canonical.split() else ""
        if len(first) < 4:
            return False
        if first in RECEIPT_LEVEL_OCR_MUTATIONS:
            return True
        if fuzz is not None:
            return any(fuzz.ratio(first, term) >= 72 for term in RECEIPT_LEVEL_CANONICAL_TERMS)
        return first in RECEIPT_LEVEL_CANONICAL_TERMS or any(self._one_edit_apart(first, term) for term in RECEIPT_LEVEL_CANONICAL_TERMS)

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

    def _survey_or_barcode_row(self, upper: str) -> bool:
        if any(token in upper for token in ("SURVEY", "BARCODE", "COUPON", "REWARD", "RECEIPT ID")):
            return True
        digits = re.sub(r"\D", "", upper)
        return len(digits) >= 8 and not re.search(r"\d{1,6}[.,]\d{2}", upper)


class ReceiptDuplicateClusterer:
    def cluster(self, rows: list[CandidateRow]) -> list[list[CandidateRow]]:
        clusters: list[list[CandidateRow]] = []
        for row in rows:
            target = None
            for cluster in clusters:
                representative = cluster[0]
                same_price = abs(representative.amount_value - row.amount_value) <= 0.01
                if same_price and row.source == "ocr.line" and row.line_index is not None:
                    existing_ocr_lines = [
                        member.line_index for member in cluster
                        if member.source == "ocr.line" and member.line_index is not None
                    ]
                    if any(line_index != row.line_index for line_index in existing_ocr_lines):
                        continue
                similarity = _similarity(representative.name, row.name)
                nearby_y = self._nearby_y(representative, row)
                overlapping_tokens = self._overlapping_product_tokens(representative.name, row.name)
                similar = similarity >= 82 or (nearby_y and similarity >= 58) or (nearby_y and overlapping_tokens >= 2)
                if same_price and similar:
                    target = cluster
                    break
            if target is None:
                clusters.append([row])
            else:
                target.append(row)
        return clusters

    def consolidate(self, cluster: list[CandidateRow], validator: ReceiptRowValidator, facts: dict[str, str]) -> dict[str, Any]:
        best = max(cluster, key=lambda row: (validator.score(row, row.reasons), len(_canonical_name(row.name)), row.confidence))
        qty = best.qty or "1"
        confidence = min(0.98, validator.score(best, best.reasons) + min(0.18, 0.04 * (len(cluster) - 1)))
        return {
            "name": self._clean_name(best.name),
            "qty": qty,
            "count": qty,
            "amount": f"{best.amount_value:.2f}",
            "price": f"{best.amount_value:.2f}",
            "confidence": round(confidence, 3),
            "sourceRows": len(cluster),
            "sources": sorted({row.source for row in cluster}),
            "rowConfidenceTrace": self._cluster_trace(best, cluster, validator),
        }

    def duplicate_diagnostics(self, clusters: list[list[CandidateRow]], validator: ReceiptRowValidator) -> list[dict[str, Any]]:
        diagnostics = []
        for cluster_index, cluster in enumerate(clusters):
            if len(cluster) <= 1:
                continue
            best = max(cluster, key=lambda row: (validator.score(row, row.reasons), len(_canonical_name(row.name)), row.confidence))
            diagnostics.append({
                "clusterIndex": cluster_index,
                "selected": self._candidate_trace(best, validator),
                "duplicates": [self._candidate_trace(row, validator) for row in cluster if row is not best],
                "reason": "same_price_similar_text_or_nearby_y",
            })
        return diagnostics

    def _nearby_y(self, left: CandidateRow, right: CandidateRow) -> bool:
        if left.line_index is not None and right.line_index is not None and abs(left.line_index - right.line_index) <= 1:
            return True
        if left.y is None or right.y is None:
            return False
        return abs(left.y - right.y) <= 22

    def _overlapping_product_tokens(self, left: str, right: str) -> int:
        left_tokens = {token for token in _canonical_name(left).split() if len(token) >= 3}
        right_tokens = {token for token in _canonical_name(right).split() if len(token) >= 3}
        return len(left_tokens & right_tokens)

    def _candidate_trace(self, row: CandidateRow, validator: ReceiptRowValidator) -> dict[str, Any]:
        return {
            "source": row.source,
            "name": row.name,
            "canonicalName": _canonical_name(row.name),
            "amount": row.amount,
            "qty": row.qty,
            "section": row.section,
            "sourceConfidence": round(float(row.confidence or 0), 3),
            "validatorScore": validator.score(row, row.reasons),
            "bbox": row.bbox or {},
            "lineIndex": row.line_index,
            "reasons": row.reasons,
        }

    def _cluster_trace(self, best: CandidateRow, cluster: list[CandidateRow], validator: ReceiptRowValidator) -> dict[str, Any]:
        return {
            "selected": self._candidate_trace(best, validator),
            "clusterSize": len(cluster),
            "alternates": [self._candidate_trace(row, validator) for row in cluster if row is not best],
        }

    def _clean_name(self, value: str) -> str:
        text = _compact(value)
        text = re.sub(r"<[^>]+>", " ", text)
        text = re.sub(r"[\[\]{}\"']", " ", text)
        text = self._strip_leading_ocr_noise_tokens(text)
        text = re.sub(r"\b\d{5,}\b", " ", text)
        text = self._strip_leading_ocr_noise_tokens(text)
        text = re.sub(r"\s+", " ", text).strip(" -_:;,")
        return text

    def _strip_leading_ocr_noise_tokens(self, value: str) -> str:
        tokens = _compact(value).split()
        noisy = {"E", "E+", "EY", "EL", "HE", "SH", "OE", "SA", "F", "CF"}
        while tokens:
            normalized = re.sub(r"[^A-Z+]", "", tokens[0].upper())
            if normalized in noisy or re.fullmatch(r"\d{3,}", tokens[0]):
                tokens.pop(0)
                continue
            break
        return " ".join(tokens)


class ReceiptSubtotalReconciler:
    def reconcile(self, items: list[dict[str, Any]], facts: dict[str, str]) -> tuple[list[dict[str, Any]], dict[str, Any]]:
        subtotal = _numeric_amount(facts.get("subtotal"))
        total = _numeric_amount(facts.get("total"))
        target = subtotal or total
        item_sum = sum(self._item_amount_value(item) for item in items)
        diagnostics = {
            "itemSum": f"{item_sum:.2f}" if item_sum else "0",
            "target": f"{target:.2f}" if target else "",
            "matched": False,
            "warnings": [],
            "itemCountTarget": int(facts.get("itemCount") or 0) if str(facts.get("itemCount") or "").isdigit() else None,
            "itemCountActual": len(items),
        }
        if diagnostics["itemCountTarget"] is not None and diagnostics["itemCountActual"] != diagnostics["itemCountTarget"]:
            diagnostics["warnings"].append("item_count_does_not_match_receipt_count")
            selected_by_count = self._best_count_subset(items, diagnostics["itemCountTarget"], target)
            if selected_by_count:
                items = selected_by_count
                item_sum = sum(self._item_amount_value(item) for item in items)
                diagnostics["itemSum"] = f"{item_sum:.2f}" if item_sum else "0"
                diagnostics["itemCountActual"] = len(items)
                diagnostics["warnings"].append("item_count_subset_reconciled")
        if not items or not target:
            return items, diagnostics
        if abs(item_sum - target) <= max(0.25, target * 0.03):
            diagnostics["matched"] = True
            return items, diagnostics
        selected = self._best_subset(items, target)
        if selected:
            selected_sum = sum(self._item_amount_value(item) for item in selected)
            if abs(selected_sum - target) < abs(item_sum - target):
                diagnostics["itemSum"] = f"{selected_sum:.2f}"
                diagnostics["matched"] = abs(selected_sum - target) <= max(0.25, target * 0.03)
                diagnostics["warnings"].append("subtotal_subset_reconciled")
                return selected, diagnostics
        diagnostics["warnings"].append("item_sum_does_not_match_receipt_total")
        return items, diagnostics

    def _best_count_subset(self, items: list[dict[str, Any]], target_count: int, target_total: float) -> list[dict[str, Any]]:
        if target_count <= 0 or len(items) <= target_count or len(items) > 20:
            return []
        ranked = sorted(items, key=lambda item: float(item.get("confidence") or 0), reverse=True)
        if not target_total:
            return ranked[:target_count]
        best_subset: list[dict[str, Any]] = []
        best_delta = float("inf")
        for subset in itertools.combinations(ranked, target_count):
            total = sum(self._item_amount_value(item) for item in subset)
            delta = abs(total - target_total)
            if delta < best_delta:
                best_delta = delta
                best_subset = list(subset)
        return best_subset if best_subset else []

    def _best_subset(self, items: list[dict[str, Any]], target: float) -> list[dict[str, Any]]:
        if len(items) > 16:
            return []
        best_delta = target
        best_subset: list[dict[str, Any]] = []
        for size in range(1, len(items) + 1):
            for subset in itertools.combinations(items, size):
                total = sum(self._item_amount_value(item) for item in subset)
                delta = abs(total - target)
                if delta < best_delta:
                    best_delta = delta
                    best_subset = list(subset)
        return best_subset if best_subset and best_delta <= max(0.5, target * 0.08) else []

    def _item_amount_value(self, item: dict[str, Any]) -> float:
        return _numeric_amount(item.get("netAmount") or item.get("amount") or item.get("price"))


class ReceiptRowConsolidationPipeline:
    def __init__(self) -> None:
        self.segmenter = ReceiptSectionSegmenter()
        self.extractor = ReceiptCandidateExtractor()
        self.validator = ReceiptRowValidator()
        self.clusterer = ReceiptDuplicateClusterer()
        self.reconciler = ReceiptSubtotalReconciler()
        self.merchants = MerchantNormalizer()
        self.section_engine = ReceiptSectionExtractionEngine()
        self.entity_engine = ReceiptEntityExtractionEngine()

    def normalize(
        self,
        donut: dict[str, Any],
        raw_text: str = "",
        lines: list[str] | None = None,
        ocr_blocks: list[dict[str, Any]] | None = None,
        parser_json: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        parser_json = parser_json or {}
        source_lines = [line for line in (lines or []) if str(line).strip()]
        if not source_lines and raw_text:
            source_lines = [line for line in raw_text.splitlines() if line.strip()]
        sections = self.segmenter.segment(source_lines, ocr_blocks)
        facts = self._facts(donut, parser_json)
        if not facts.get("itemCount"):
            facts["itemCount"] = self._infer_item_count("\n".join(source_lines) or raw_text)
        section_result = self.section_engine.extract(raw_text=raw_text, lines=source_lines, ocr_blocks=ocr_blocks)
        self._merge_section_facts(facts, section_result)
        entity_result = self.entity_engine.extract(raw_text=raw_text, lines=source_lines, ocr_blocks=ocr_blocks)
        self._merge_entity_facts(facts, entity_result)
        self._merge_line_total_facts(facts, source_lines)
        self._sanitize_temporal_facts(facts, source_lines)
        self._sanitize_receipt_facts(facts)
        candidates = self.extractor.extract(
            donut,
            source_lines,
            sections,
            self.segmenter,
            section_items=section_result.get("items") if isinstance(section_result.get("items"), list) else [],
            ocr_blocks=ocr_blocks,
        )
        boundary_lock = self._section_boundary_lock(section_result)
        self._apply_boundary_lock(candidates, boundary_lock, source_lines)
        accepted: list[CandidateRow] = []
        rejected: list[dict[str, Any]] = []
        for row in candidates:
            valid, reasons, score = self.validator.validate(row, facts)
            row.reasons = reasons
            row.confidence = min(1.0, max(row.confidence, score))
            if valid:
                accepted.append(row)
            else:
                rejected.append({
                    "source": row.source,
                    "name": row.name,
                    "amount": row.amount,
                    "section": row.section,
                    "confidence": score,
                    "reasons": reasons,
                })
        clusters = self.clusterer.cluster(accepted)
        duplicate_clusters = self.clusterer.duplicate_diagnostics(clusters, self.validator)
        consolidated = [self.clusterer.consolidate(cluster, self.validator, facts) for cluster in clusters]
        self._apply_line_discounts(consolidated, source_lines)
        consolidated, reconciliation = self.reconciler.reconcile(consolidated, facts)
        self._reconcile_receipt_facts_with_items(facts, consolidated)
        consolidated = [{**item, "id": index + 1} for index, item in enumerate(consolidated)]
        merchant_resolution = self.merchants.resolve(
            "\n".join(source_lines) or raw_text,
            str(facts.get("merchant") or donut.get("merchant") or parser_json.get("company") or parser_json.get("storeName") or ""),
        )
        merchant = merchant_resolution["merchant"]
        confidence = self._overall_confidence(consolidated, reconciliation, merchant, candidates, rejected)
        retry_plan = self._retry_plan(consolidated, reconciliation, confidence)
        normalized = {
            **donut,
            "merchant": merchant,
            "date": facts.get("purchaseDate", "") or facts.get("date", ""),
            "purchaseDate": facts.get("purchaseDate", "") or facts.get("date", ""),
            "transactionTime": facts.get("transactionTime", ""),
            "paymentTime": facts.get("paymentTime", ""),
            "address": facts.get("address", ""),
            "storeAddress": facts.get("storeAddress", facts.get("address", "")),
            "phone": facts.get("phone", ""),
            "merchantConfidenceTrace": merchant_resolution,
            "items": consolidated,
            "subtotal": facts.get("subtotal", ""),
            "tax": facts.get("tax", ""),
            "tip": facts.get("tip", ""),
            "charge": facts.get("charge", ""),
            "total": facts.get("total", ""),
            "paymentMethod": facts.get("paymentMethod", ""),
            "cardType": facts.get("cardUsed", ""),
            "lastFour": facts.get("cardLast4", ""),
            "cardUsed": facts.get("cardUsed", ""),
            "cardLast4": facts.get("cardLast4", ""),
            "approvalCode": facts.get("approvalCode", ""),
            "paymentCard": {
                "brand": facts.get("cardUsed", ""),
                "last4": facts.get("cardLast4", ""),
                "approvalCode": facts.get("approvalCode", ""),
            },
            "confidence": confidence["overall"],
            "sectionExtraction": section_result,
            "receiptEntities": entity_result,
            "rowConsolidation": {
                "schemaVersion": "receipt-row-consolidation-v1",
                "candidateCount": len(candidates),
                "acceptedCandidateCount": len(accepted),
                "rejectedCandidateCount": len(rejected),
                "clusterCount": len(clusters),
                "duplicateClusterCount": len(duplicate_clusters),
                "sections": [section.__dict__ for section in sections],
                "boundaryLock": boundary_lock,
                "reconciliation": reconciliation,
                "confidence": confidence,
                "retryPlan": retry_plan,
                "rejectedRows": rejected[:80],
                "duplicateRows": duplicate_clusters[:80],
                "rowConfidenceTraces": [item.get("rowConfidenceTrace", {}) for item in consolidated[:120]],
                "rapidFuzzAvailable": fuzz is not None,
                "llamaValidation": {
                    "strategy": "receipt/document-understanding run_llama=true performs final semantic validation",
                    "required": confidence["overall"] < 0.74 or bool(reconciliation.get("warnings")),
                },
            },
        }
        logger.info(
            "Donut receipt rows consolidated candidates=%s accepted=%s items=%s confidence=%s warnings=%s",
            len(candidates),
            len(accepted),
            len(consolidated),
            confidence["overall"],
            reconciliation.get("warnings", []),
        )
        return normalized

    def _facts(self, donut: dict[str, Any], parser_json: dict[str, Any]) -> dict[str, str]:
        donut_card = donut.get("paymentCard") if isinstance(donut.get("paymentCard"), dict) else {}
        parser_card = parser_json.get("paymentCard") if isinstance(parser_json.get("paymentCard"), dict) else {}
        return {
            "subtotal": _amount(donut.get("subtotal") or parser_json.get("subtotal") or parser_json.get("subTotal")),
            "tax": _amount(donut.get("tax") or parser_json.get("tax")),
            "tip": _amount(donut.get("tip") or parser_json.get("tip")),
            "charge": _amount(donut.get("charge") or parser_json.get("charge")),
            "total": _amount(donut.get("total") or parser_json.get("total")),
            "paymentMethod": _compact(donut.get("paymentMethod") or parser_json.get("paymentMethod")),
            "cardUsed": _compact(donut.get("cardUsed") or donut_card.get("brand") or parser_json.get("cardUsed") or parser_card.get("brand")),
            "cardLast4": _compact(donut.get("cardLast4") or donut_card.get("last4") or parser_json.get("cardLast4") or parser_card.get("last4")),
            "approvalCode": _compact(donut.get("approvalCode") or parser_json.get("approvalCode")),
            "merchant": _compact(donut.get("merchant") or parser_json.get("company") or parser_json.get("storeName")),
            "date": _compact(donut.get("purchaseDate") or donut.get("date") or parser_json.get("purchaseDate") or parser_json.get("date")),
            "purchaseDate": _compact(donut.get("purchaseDate") or donut.get("date") or parser_json.get("purchaseDate") or parser_json.get("date")),
            "transactionTime": _compact(donut.get("transactionTime") or parser_json.get("transactionTime")),
            "paymentTime": _compact(donut.get("paymentTime") or parser_json.get("paymentTime")),
            "address": _compact(donut.get("address") or donut.get("storeAddress") or parser_json.get("address") or parser_json.get("storeAddress")),
            "storeAddress": _compact(donut.get("storeAddress") or donut.get("address") or parser_json.get("storeAddress") or parser_json.get("address")),
            "phone": _compact(donut.get("phone") or parser_json.get("phone")),
            "itemCount": self._item_count(donut, parser_json),
        }

    def _item_count(self, donut: dict[str, Any], parser_json: dict[str, Any]) -> str:
        values = [
            donut.get("itemCount"),
            donut.get("soldItemCount"),
            donut.get("item_count"),
            parser_json.get("itemCount"),
            parser_json.get("soldItemCount"),
            parser_json.get("item_count"),
        ]
        raw = donut.get("raw") if isinstance(donut.get("raw"), dict) else {}
        values.extend([raw.get("itemCount"), raw.get("soldItemCount"), raw.get("item_count")])
        for value in values:
            match = re.search(r"\b\d{1,3}\b", str(value or ""))
            if match:
                return match.group(0)
        return ""

    def _infer_item_count(self, raw_text: str) -> str:
        matches = re.findall(r"\b(?:ITEM\s+COUNT|SOLD\s+ITEMS?|ITEMS\s+SOLD)\D{0,12}(\d{1,3})\b", raw_text or "", flags=re.IGNORECASE)
        return matches[-1] if matches else ""

    def _merge_section_facts(self, facts: dict[str, str], section_result: dict[str, Any]) -> None:
        totals = section_result.get("totals", {}) if isinstance(section_result, dict) else {}
        total_fields = totals.get("fields", {}) if isinstance(totals, dict) else {}
        for key in ("subtotal", "tax", "tip", "charge", "total"):
            value = _amount(total_fields.get(key))
            if value:
                facts[key] = value
        payment = section_result.get("payment", {}) if isinstance(section_result, dict) else {}
        payment_fields = payment.get("fields", {}) if isinstance(payment, dict) else {}
        for key in ("paymentMethod", "cardUsed", "cardLast4", "approvalCode"):
            value = _compact(payment_fields.get(key))
            if value:
                facts[key] = value
        payment_charge = _amount(payment_fields.get("charge"))
        if payment_charge:
            facts["charge"] = payment_charge

    def _merge_entity_facts(self, facts: dict[str, str], entity_result: dict[str, Any]) -> None:
        fields = entity_result.get("fields", {}) if isinstance(entity_result, dict) else {}
        for key in ("merchant", "date", "purchaseDate", "transactionTime", "paymentTime", "address", "storeAddress", "phone", "paymentMethod", "cardUsed", "cardLast4", "approvalCode"):
            value = _compact(fields.get(key))
            if value:
                facts[key] = value
        header = entity_result.get("header", {}) if isinstance(entity_result, dict) else {}
        address_candidate = header.get("address", {}) if isinstance(header, dict) else {}
        if isinstance(address_candidate, dict) and not facts.get("address"):
            try:
                confidence = float(address_candidate.get("confidence") or 0)
            except (TypeError, ValueError):
                confidence = 0.0
            value = _compact(address_candidate.get("value"))
            if value and confidence >= 0.68:
                facts["address"] = value
                facts["storeAddress"] = value
        card_type = _compact(fields.get("cardType"))
        if card_type:
            facts["cardUsed"] = card_type
        last_four = _compact(fields.get("lastFour"))
        if last_four:
            facts["cardLast4"] = last_four

    def _merge_line_total_facts(self, facts: dict[str, str], lines: list[str]) -> None:
        inferred: dict[str, str] = {}
        payment_total = ""
        for line in lines:
            upper = _compact(line).upper()
            amounts = self._decimal_amounts(line)
            if not amounts:
                continue
            amount = amounts[-1]
            if "SUBTOTAL" in upper or "SUB TOTAL" in upper:
                inferred["subtotal"] = amount
            elif "TOTAL TAX" in upper or (re.search(r"\bTAX\b", upper) and "%" not in upper and "FSA" not in upper):
                inferred["tax"] = amount
            elif "HARGE" in upper or "CHARGE" in upper:
                inferred["charge"] = amount
            elif "GATT" in upper:
                inferred["total"] = amount
            elif re.search(r"\bTOTAL\b", upper) and "TAX" not in upper and "FSA" not in upper and "DISCOUNT" not in upper:
                inferred["total"] = amount
            elif re.search(r"\bAMOUNT\b", upper):
                payment_total = amount
        if payment_total and not inferred.get("total"):
            inferred["total"] = payment_total
        for key, value in inferred.items():
            current = _numeric_amount(facts.get(key))
            candidate = _numeric_amount(value)
            if candidate <= 0:
                continue
            if key in {"subtotal", "tax"} and candidate > 0:
                facts[key] = value
            elif key == "subtotal" and _numeric_amount(facts.get("total")) and candidate > _numeric_amount(facts.get("total")) * 1.4:
                facts[key] = value
            elif key == "total" and candidate > max(current, _numeric_amount(facts.get("subtotal"))):
                facts[key] = value
            elif not current or abs(candidate - current) > max(1.0, candidate * 0.25):
                facts[key] = value

    def _sanitize_temporal_facts(self, facts: dict[str, str], lines: list[str]) -> None:
        date_value = _compact(facts.get("purchaseDate") or facts.get("date"))
        if not date_value:
            return
        digits = re.sub(r"\D+", "", date_value)
        if not digits:
            return
        matching_lines = [
            _compact(line).upper()
            for line in lines
            if digits and digits in re.sub(r"\D+", "", str(line or ""))
        ]
        if matching_lines and all(any(term in line for term in ("RETURN", "POLICY", "THRU", "EXP", "EXPIRES")) for line in matching_lines):
            facts["date"] = ""
            facts["purchaseDate"] = ""

    def _decimal_amounts(self, line: str) -> list[str]:
        return [match.group(0).replace(",", ".").replace(":", ".") for match in re.finditer(r"\d{1,6}[.,:]\d{2}", str(line or ""))]

    def _sanitize_receipt_facts(self, facts: dict[str, str]) -> None:
        subtotal = _numeric_amount(facts.get("subtotal"))
        total = _numeric_amount(facts.get("total"))
        tax = _numeric_amount(facts.get("tax"))
        charge = _numeric_amount(facts.get("charge"))
        if total > 10000 and charge and charge < total * 0.1:
            logger.info("Replacing implausible receipt total with payment charge total=%s charge=%s", facts.get("total"), facts.get("charge"))
            facts["total"] = f"{charge:.2f}"
            total = charge
        if subtotal and total:
            inferred_total = subtotal + tax
            if tax and inferred_total > total and abs(inferred_total - total) > max(1.0, inferred_total * 0.1):
                logger.info(
                    "Replacing stale receipt total with subtotal-plus-tax subtotal=%s tax=%s total=%s",
                    facts.get("subtotal"),
                    facts.get("tax"),
                    facts.get("total"),
                )
                facts["total"] = f"{inferred_total:.2f}"
                total = inferred_total
            elif subtotal > max(total + tax + 0.5, total * 3):
                logger.info("Discarding implausible receipt subtotal subtotal=%s total=%s tax=%s", facts.get("subtotal"), facts.get("total"), facts.get("tax"))
                facts["subtotal"] = ""
            elif "." not in str(facts.get("subtotal", "")) and abs(subtotal - total) > max(0.5, total * 0.08):
                logger.info("Discarding no-cents subtotal that disagrees with total subtotal=%s total=%s", facts.get("subtotal"), facts.get("total"))
                facts["subtotal"] = ""

    def _reconcile_receipt_facts_with_items(self, facts: dict[str, str], items: list[dict[str, Any]]) -> None:
        item_sum = sum(_numeric_amount(item.get("netAmount") or item.get("amount") or item.get("price")) for item in items)
        if item_sum <= 0:
            return
        total = _numeric_amount(facts.get("total"))
        subtotal = _numeric_amount(facts.get("subtotal"))
        tax = _numeric_amount(facts.get("tax"))
        if total > 10000 and item_sum < total * 0.1:
            logger.info("Replacing implausible receipt total with item sum total=%s item_sum=%.2f", facts.get("total"), item_sum)
            facts["total"] = f"{item_sum:.2f}"
            total = item_sum
        if not total and not subtotal and not tax and len(items) <= 3:
            facts["total"] = f"{item_sum:.2f}"

    def _apply_line_discounts(self, items: list[dict[str, Any]], lines: list[str]) -> None:
        if not items or not lines:
            return
        line_items: list[tuple[int, dict[str, Any]]] = []
        for item in items:
            trace = item.get("rowConfidenceTrace", {}) if isinstance(item, dict) else {}
            selected = trace.get("selected", {}) if isinstance(trace, dict) else {}
            line_index = selected.get("lineIndex")
            if not isinstance(line_index, int):
                for alternate in trace.get("alternates", []) if isinstance(trace.get("alternates"), list) else []:
                    alternate_index = alternate.get("lineIndex") if isinstance(alternate, dict) else None
                    if isinstance(alternate_index, int):
                        line_index = alternate_index
                        break
            if isinstance(line_index, int):
                line_items.append((line_index, item))
        if not line_items:
            return
        line_items.sort(key=lambda entry: entry[0])
        for index, line in enumerate(lines):
            discount = self._standalone_discount_amount(line)
            if not discount:
                continue
            target = None
            for line_index, item in line_items:
                if line_index < index:
                    target = item
                else:
                    break
            if target is None:
                continue
            discount_value = _numeric_amount(discount)
            gross_value = _numeric_amount(target.get("amount") or target.get("price"))
            if discount_value <= 0 or gross_value <= 0:
                continue
            existing_discount = _numeric_amount(target.get("discount"))
            total_discount = existing_discount + discount_value
            target["grossAmount"] = f"{gross_value:.2f}"
            target["discount"] = f"{total_discount:.2f}"
            target["netAmount"] = f"{max(0.0, gross_value - total_discount):.2f}"
            adjustments = target.setdefault("adjustments", [])
            if isinstance(adjustments, list):
                adjustments.append({
                    "type": "discount",
                    "amount": f"{discount_value:.2f}",
                    "rawLine": line,
                    "lineIndex": index,
                    "appliesTo": "previous_item_line",
                })

    def _standalone_discount_amount(self, line: str) -> str:
        text = _compact(line)
        upper = text.upper()
        if not text or any(term in upper for term in RECEIPT_TOTAL_TERMS + RECEIPT_FOOTER_TERMS):
            return ""
        match = re.search(r"(?P<amount>\d{1,5}(?:[.,]\d{2})|\d{3,5})\s*[-–—]\s*$", text)
        if not match:
            return ""
        prefix = text[:match.start()].upper()
        if re.search(r"\d{14,}", prefix):
            return ""
        prefix = re.sub(r"\b\d{3,}\b", " ", prefix)
        prefix = re.sub(r"[/\\|()[\]{}<>%*#+=.,:;!?'\"]", " ", prefix)
        words = [word for word in prefix.split() if re.search(r"[A-Z]", word)]
        product_words = [
            word for word in words
            if word not in {"E", "EJ", "EL", "EY", "F", "CF", "OE", "SA", "ST", "X"}
        ]
        if product_words:
            return ""
        return match.group("amount").replace(",", ".")

    def _section_boundary_lock(self, section_result: dict[str, Any]) -> dict[str, Any]:
        debug = section_result.get("debug", {}) if isinstance(section_result, dict) else {}
        lock = debug.get("itemBoundaryLock", {}) if isinstance(debug, dict) else {}
        return lock if isinstance(lock, dict) else {}

    def _apply_boundary_lock(self, candidates: list[CandidateRow], lock: dict[str, Any], lines: list[str]) -> None:
        first_index = lock.get("firstLockedIndex")
        first_y = lock.get("firstLockedY")
        for row in candidates:
            line_index = row.raw.get("lineIndex") if isinstance(row.raw, dict) else None
            if isinstance(line_index, int) and self._inside_department_item_window(lines, line_index):
                row.section = "items"
                continue
            if first_index is not None and isinstance(line_index, int) and line_index >= int(first_index):
                row.section = "totals"
                row.reasons.append("boundary_locked_after_totals")
                continue
            bbox = row.bbox if isinstance(row.bbox, dict) else {}
            y = bbox.get("y", bbox.get("top"))
            if first_y is not None and y is not None:
                try:
                    if float(y) >= float(first_y):
                        row.section = "totals"
                        row.reasons.append("boundary_locked_by_y_position")
                except (TypeError, ValueError):
                    pass

    def _inside_department_item_window(self, lines: list[str], index: int) -> bool:
        if index < 0 or index >= len(lines):
            return False
        seen_department = False
        for cursor in range(index, -1, -1):
            upper = _compact(lines[cursor]).upper()
            if any(term in upper for term in RECEIPT_DEPARTMENT_TERMS):
                seen_department = True
                break
            if cursor != index and any(term in upper for term in ("BALANCE DUE", "TOTAL TAX", "TAX-CODE", "TOTAL DISCOUNTS", "ITEMS SOLD")):
                return False
        if not seen_department:
            return False
        upper_line = _compact(lines[index]).upper()
        if any(term in upper_line for term in ("BALANCE DUE", "TOTAL TAX", "TAX-CODE", "TOTAL DISCOUNTS", "CHANGE", "AUTH CODE", "AMERICAN EXPRESS")):
            return False
        for cursor in range(index + 1, min(len(lines), index + 8)):
            upper = _compact(lines[cursor]).upper()
            if any(term in upper for term in ("BALANCE DUE", "TOTAL TAX", "TAX-CODE", "TOTAL DISCOUNTS", "CHANGE")):
                return True
        return bool(re.search(r"[A-Z]{3,}", upper_line) and re.search(r"\d{1,5}(?:[.,]\d{2})", upper_line))

    def _overall_confidence(
        self,
        items: list[dict[str, Any]],
        reconciliation: dict[str, Any],
        merchant: str,
        candidates: list[CandidateRow],
        rejected: list[dict[str, Any]],
    ) -> dict[str, float]:
        item_score = min(1.0, sum(float(item.get("confidence") or 0) for item in items) / max(len(items), 1)) if items else 0.0
        validation_score = 1.0 if reconciliation.get("matched") else (0.7 if not reconciliation.get("target") else 0.46)
        merchant_score = 1.0 if merchant else 0.0
        rejection_penalty = min(0.24, len(rejected) / max(len(candidates), 1) * 0.24)
        overall = (item_score * 0.48) + (validation_score * 0.3) + (merchant_score * 0.14) + 0.08 - rejection_penalty
        return {
            "overall": round(max(0.0, min(1.0, overall)), 3),
            "items": round(item_score, 3),
            "validation": round(validation_score, 3),
            "merchant": round(merchant_score, 3),
        }

    def _retry_plan(self, items: list[dict[str, Any]], reconciliation: dict[str, Any], confidence: dict[str, float]) -> list[dict[str, str]]:
        retries: list[dict[str, str]] = []
        if not items:
            retries.append({"stage": "donut", "strategy": "retry_with_preprocessed_receipt_image", "reason": "no_valid_items"})
        if reconciliation.get("warnings"):
            retries.append({"stage": "semantic", "strategy": "llama_receipt_row_validation", "reason": ",".join(reconciliation["warnings"])})
        if confidence.get("overall", 0) < 0.7:
            retries.append({"stage": "ocr", "strategy": "paddle_or_tesseract_cross_check", "reason": "low_consolidated_confidence"})
        return retries[:5]
