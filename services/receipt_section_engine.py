from __future__ import annotations

import logging
import re
from itertools import combinations
from dataclasses import dataclass, field
from typing import Any

from services.receipt_visual_hierarchy import ReceiptVisualHierarchyEngine

try:
    from rapidfuzz import fuzz
except Exception:  # pragma: no cover - dependency is installed in production requirements.
    fuzz = None


logger = logging.getLogger(__name__)

TOTAL_KEYWORDS = (
    "SUBTOTAL", "SUB TOTAL", "TAX", "TOTAL", "BALANCE", "CHANGE", "TIP", "CHARGE", "AMOUNT",
)
CURRENCY_KEYWORDS = (
    "USD", "US DOLLAR", "DOLLARS", "CURRENCY", "TENDER",
)
PAYMENT_KEYWORDS = (
    "VISA", "MASTERCARD", "MASTER CARD", "AMEX", "AMERICAN EXPRESS", "DISCOVER",
    "CREDIT", "DEBIT", "CARD", "AUTH", "APPROVAL", "APPROVED", "AID", "ENTRY", "CHIP",
    "LAST FOUR", "LAST 4", "CARD LAST", "ENDING IN",
)
FOOTER_KEYWORDS = (
    "THANK", "SURVEY", "FEEDBACK", "RETURN POLICY", "COME AGAIN", "VISIT", "WWW.",
    "NO PURCHASE", "NO PURCHASE NECESSARY",
)
ITEM_EXCLUSION_KEYWORDS = TOTAL_KEYWORDS + PAYMENT_KEYWORDS + FOOTER_KEYWORDS + (
    *CURRENCY_KEYWORDS,
    "TERMINAL", "TRANS", "TRANSACTION", "CASHIER", "REGISTER", "RECEIPT",
    "BARCODE", "COUPON", "SAVINGS", "ITEM COUNT", "SOLD ITEM",
)
SECTION_LOCK_KINDS = {"totals", "payment", "footer"}
DOCUMENT_STATES = ("HEADER", "ITEMS", "TOTALS", "PAYMENT", "FOOTER")
RETAIL_ITEM_HINTS = (
    "EA", "PK", "PACK", "BAG", "BOX", "CAN", "BTL", "OZ", "LB", "GAL", "QT",
    "SKU", "UPC", "ITEM", "REG", "SALE", "DISC", "FOOD", "DRINK",
)


@dataclass
class ReceiptLineGeometry:
    text: str
    index: int
    x: float = 0.0
    y: float = 0.0
    width: float = 0.0
    height: float = 14.0
    confidence: float = 1.0
    page: int = 1

    @property
    def right(self) -> float:
        return self.x + self.width


@dataclass
class ReceiptRegion:
    kind: str
    lines: list[ReceiptLineGeometry] = field(default_factory=list)
    confidence: float = 0.0
    reasons: list[str] = field(default_factory=list)

    @property
    def start(self) -> int:
        return min((line.index for line in self.lines), default=0)

    @property
    def end(self) -> int:
        return max((line.index for line in self.lines), default=0)

    @property
    def text(self) -> str:
        return "\n".join(line.text for line in self.lines)

    def to_dict(self) -> dict[str, Any]:
        bounds = self.bounds
        return {
            "kind": self.kind,
            "start": self.start,
            "end": self.end,
            "confidence": round(self.confidence, 3),
            "reasons": self.reasons,
            "bbox": {
                "x": round(bounds["x"], 2),
                "y": round(bounds["y"], 2),
                "width": round(bounds["width"], 2),
                "height": round(bounds["height"], 2),
            },
            "lines": [
                {
                    "index": line.index,
                    "text": line.text,
                    "confidence": round(line.confidence, 3),
                    "bbox": {
                        "x": round(line.x, 2),
                        "y": round(line.y, 2),
                        "width": round(line.width, 2),
                        "height": round(line.height, 2),
                    },
                }
                for line in self.lines
            ],
        }

    @property
    def bounds(self) -> dict[str, float]:
        if not self.lines:
            return {"x": 0.0, "y": 0.0, "width": 0.0, "height": 0.0}
        left = min(line.x for line in self.lines)
        top = min(line.y for line in self.lines)
        right = max(line.right for line in self.lines)
        bottom = max(line.y + line.height for line in self.lines)
        return {
            "x": left,
            "y": top,
            "width": max(0.0, right - left),
            "height": max(0.0, bottom - top),
        }


def compact(value: Any) -> str:
    return re.sub(r"\s+", " ", str(value or "")).strip()


def amount(value: Any) -> str:
    text = str(value or "").replace("$", "").replace(",", ".")
    match = re.search(r"-?\d{1,7}(?:\.\d{2})(?=\b|[A-Z])", text, flags=re.IGNORECASE)
    if match:
        return match.group(0)
    match = re.search(r"(?<!\d)(-?\d{1,7})\D{1,4}(\d{2})(?!\d)", text)
    if match:
        return f"{match.group(1)}.{match.group(2)}"
    match = re.search(r"-?\d{1,7}\b", text)
    return match.group(0) if match else ""


def numeric(value: Any) -> float:
    parsed = amount(value)
    try:
        return float(parsed) if parsed else 0.0
    except ValueError:
        return 0.0


def one_edit_apart(left: str, right: str) -> bool:
    if abs(len(left) - len(right)) > 1:
        return False
    if len(left) == len(right):
        return sum(1 for a, b in zip(left, right) if a != b) <= 1
    short, long = (left, right) if len(left) < len(right) else (right, left)
    for index in range(len(long)):
        if long[:index] + long[index + 1:] == short:
            return True
    return False


def section_keyword_token(upper: str) -> str:
    tokens = [re.sub(r"[^A-Z]", "", token) for token in upper.split()]
    tokens = [token for token in tokens if token]
    if not tokens:
        return ""
    candidates = [tokens[0]]
    if len(tokens) >= 2:
        candidates.append(tokens[0] + tokens[1])
    if len(tokens) >= 3:
        candidates.append(tokens[0] + tokens[1] + tokens[2])
    return max(candidates, key=lambda token: len(token))


def token_is_near_section_keyword(token: str) -> bool:
    if token in {
        "GATT", "HARGE", "T0TAL", "TOTAI", "TQTAL", "SUBT0TAL", "CHARGF", "CHAR6E",
        "BAIANCE", "BAIANCEDUE",
    }:
        return True
    targets = (
        "TOTAL", "SUBTOTAL", "CHARGE", "PAYMENT", "CHANGE", "TAX", "VISA", "CARD", "AUTH",
        "BALANCE", "BALANCEDUE",
    )
    if fuzz is not None:
        return any(fuzz.ratio(token, target) >= 72 for target in targets)
    return token in targets or any(one_edit_apart(token, target) for target in targets)


class ReceiptGeometryBuilder:
    def from_inputs(self, raw_text: str = "", lines: list[str] | None = None, boxes: list[dict[str, Any]] | None = None) -> list[ReceiptLineGeometry]:
        box_lines = self._from_boxes(boxes or [])
        if box_lines:
            return box_lines
        source_lines = [compact(line) for line in (lines or []) if compact(line)]
        if not source_lines and raw_text:
            source_lines = [compact(line) for line in raw_text.splitlines() if compact(line)]
        return [
            ReceiptLineGeometry(
                text=line,
                index=index,
                x=0.0,
                y=float(index * 18),
                width=max(80.0, len(line) * 7.0),
                height=14.0,
                confidence=1.0,
            )
            for index, line in enumerate(source_lines)
        ]

    def _from_boxes(self, boxes: list[dict[str, Any]]) -> list[ReceiptLineGeometry]:
        parsed = [self._box(box) for box in boxes if isinstance(box, dict) and compact(box.get("text") or box.get("value"))]
        if not parsed:
            return []
        parsed.sort(key=lambda line: (line.page, line.y, line.x))
        median_height = sorted([line.height for line in parsed if line.height > 0])[len(parsed) // 2] if parsed else 14
        tolerance = max(8.0, median_height * 0.75)
        rows: list[list[ReceiptLineGeometry]] = []
        for line in parsed:
            center = line.y + line.height / 2
            target = next((row for row in rows if abs(self._row_center(row) - center) <= tolerance), None)
            if target is None:
                rows.append([line])
            else:
                target.append(line)
        output: list[ReceiptLineGeometry] = []
        for index, row in enumerate(rows):
            ordered = sorted(row, key=lambda item: item.x)
            text = compact(" ".join(item.text for item in ordered))
            left = min(item.x for item in ordered)
            top = min(item.y for item in ordered)
            right = max(item.right for item in ordered)
            bottom = max(item.y + item.height for item in ordered)
            confidence = sum(item.confidence for item in ordered) / max(len(ordered), 1)
            output.append(ReceiptLineGeometry(
                text=text,
                index=index,
                x=left,
                y=top,
                width=max(0.0, right - left),
                height=max(1.0, bottom - top),
                confidence=confidence,
                page=ordered[0].page,
            ))
        return sorted(output, key=lambda line: (line.page, line.y, line.x))

    def _box(self, payload: dict[str, Any]) -> ReceiptLineGeometry:
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
        return ReceiptLineGeometry(
            text=compact(payload.get("text") or payload.get("value")),
            index=0,
            x=float(payload.get("x", bbox.get("x", bbox.get("left", 0))) or 0),
            y=float(payload.get("y", bbox.get("y", bbox.get("top", 0))) or 0),
            width=float(payload.get("width", bbox.get("width", bbox.get("w", 0))) or 0),
            height=float(payload.get("height", bbox.get("height", bbox.get("h", 14))) or 14),
            confidence=float(payload.get("confidence", payload.get("conf", 1.0)) or 0),
            page=int(payload.get("page", payload.get("pageNumber", 1)) or 1),
        )

    def _row_center(self, row: list[ReceiptLineGeometry]) -> float:
        return sum(line.y + line.height / 2 for line in row) / max(len(row), 1)


class ReceiptRegionClassifier:
    def classify(self, lines: list[ReceiptLineGeometry]) -> list[ReceiptRegion]:
        if not lines:
            return []
        regions: list[ReceiptRegion] = []
        current_kind = self._classify_line(lines[0], lines, 0)[0]
        current_lines: list[ReceiptLineGeometry] = []
        reasons: list[str] = []
        for index, line in enumerate(lines):
            kind, line_reasons, confidence = self._classify_line(line, lines, index)
            if current_lines and kind != current_kind:
                regions.append(self._region(current_kind, current_lines, reasons))
                current_lines = []
                reasons = []
            current_kind = kind
            current_lines.append(line)
            reasons.extend(line_reasons)
        if current_lines:
            regions.append(self._region(current_kind, current_lines, reasons))
        return self._lock_boundaries(self._promote_contextual_regions(regions))

    def _classify_line(self, line: ReceiptLineGeometry, lines: list[ReceiptLineGeometry], index: int) -> tuple[str, list[str], float]:
        text = compact(line.text)
        upper = text.upper()
        reasons: list[str] = []
        amount_count = len(re.findall(r"\d{1,7}(?:[.,]\d{2})", text))
        right_aligned_amount = self._has_right_aligned_amount(line, lines)
        if any(keyword in upper for keyword in TOTAL_KEYWORDS):
            return "totals", ["total_keyword"], 0.9
        if any(keyword in upper for keyword in CURRENCY_KEYWORDS) and amount_count:
            return "totals", ["currency_total_keyword"], 0.82
        if any(keyword in upper for keyword in PAYMENT_KEYWORDS):
            return "payment", ["payment_keyword"], 0.9
        if any(keyword in upper for keyword in FOOTER_KEYWORDS):
            if index <= 2:
                return "header", ["header_policy_or_footer_text"], 0.62
            if self._is_footer_like_text_before_item_table(line, lines, index):
                return "header", ["pre_item_footer_like_text"], 0.58
            return "footer", ["footer_keyword"], 0.82
        if self._is_near_section_keyword(upper):
            return "totals", ["total_keyword"], 0.9
        if index <= 4 and re.search(r"[A-Z]{3,}", upper) and amount_count == 0:
            return "header", ["top_text_no_amount"], 0.8
        if re.search(r"[A-Z]{3,}", upper) and amount_count and right_aligned_amount:
            return "items", ["product_text_with_right_amount"], 0.78
        if re.search(r"[A-Z]{3,}", upper) and amount_count:
            return "items", ["product_text_with_amount"], 0.66
        return "unknown", reasons or ["low_signal"], 0.45

    def _is_footer_like_text_before_item_table(self, line: ReceiptLineGeometry, lines: list[ReceiptLineGeometry], index: int) -> bool:
        page_bottom = max((candidate.y + candidate.height for candidate in lines), default=0.0)
        if page_bottom and (line.y + line.height / 2) / page_bottom >= 0.55:
            return False
        lookahead = lines[index + 1: index + 18]
        product_rows = 0
        for candidate in lookahead:
            upper = compact(candidate.text).upper()
            if any(keyword in upper for keyword in TOTAL_KEYWORDS):
                break
            if re.search(r"[A-Z]{3,}", upper) and re.search(r"\d{1,7}(?:[.,]\d{2})", upper):
                product_rows += 1
            if product_rows >= 2:
                return True
        return False

    def _is_near_section_keyword(self, upper: str) -> bool:
        token = section_keyword_token(upper)
        if len(token) < 4:
            return False
        return token_is_near_section_keyword(token)

    def _has_right_aligned_amount(self, line: ReceiptLineGeometry, lines: list[ReceiptLineGeometry]) -> bool:
        if not re.search(r"\d{1,7}(?:[.,]\d{2})\s*[A-Z]?\s*$", line.text):
            return False
        max_right = max((candidate.right for candidate in lines), default=line.right)
        if max_right <= 0:
            return True
        return line.right >= max_right * 0.72

    def _region(self, kind: str, lines: list[ReceiptLineGeometry], reasons: list[str]) -> ReceiptRegion:
        confidence = sum(line.confidence for line in lines) / max(len(lines), 1)
        return ReceiptRegion(kind=kind, lines=lines.copy(), confidence=confidence, reasons=sorted(set(reasons))[:8])

    def _promote_contextual_regions(self, regions: list[ReceiptRegion]) -> list[ReceiptRegion]:
        seen_items = False
        previous: ReceiptRegion | None = None
        for region in regions:
            if region.kind == "items":
                seen_items = True
            if seen_items and region.kind == "unknown" and any(keyword in region.text.upper() for keyword in PAYMENT_KEYWORDS):
                region.kind = "payment"
                region.reasons.append("after_items_payment_context")
            if (
                previous
                and previous.kind == "payment"
                and region.kind == "unknown"
                and re.fullmatch(r"\D*\d{4}\D*", region.text.strip())
                and re.search(r"\bLAST\s*(?:FOUR|4)\b|\bCARD\s*LAST\b|\bENDING\s+IN\b", previous.text, flags=re.IGNORECASE)
            ):
                region.kind = "payment"
                region.reasons.append("last4_value_after_payment_label")
            previous = region
        return regions

    def _lock_boundaries(self, regions: list[ReceiptRegion]) -> list[ReceiptRegion]:
        locked = False
        for region in regions:
            if region.kind in SECTION_LOCK_KINDS:
                locked = True
                continue
            if locked and region.kind == "items":
                region.kind = "unknown"
                region.reasons.append("item_after_totals_boundary_suppressed")
        return regions


class TotalsParser:
    def parse(self, regions: list[ReceiptRegion]) -> dict[str, Any]:
        fields: dict[str, str] = {}
        candidates: list[dict[str, Any]] = []
        rejected: list[dict[str, Any]] = []
        for region in regions:
            if region.kind != "totals":
                continue
            for line in region.lines:
                label = self._label(line.text)
                value = self._right_aligned_amount(line, regions)
                if not label or not value:
                    rejected.append({"line": line.text, "reason": "missing_label_or_right_aligned_amount", "label": label})
                    continue
                candidate = {"label": label, "amount": value, "line": line.text, "confidence": self._confidence(label, line)}
                tax_percent = self._tax_percent(line.text) if label == "tax" else ""
                if tax_percent:
                    candidate["taxPercent"] = tax_percent
                    candidate["confidence"] = min(1.0, candidate["confidence"] + 0.05)
                candidates.append(candidate)
        candidates.extend(self._parse_split_total_rows(regions))
        for label in ("subtotal", "tip", "charge", "total", "change"):
            matches = [candidate for candidate in candidates if candidate["label"] == label]
            if matches:
                fields[label] = max(matches, key=lambda item: item["confidence"])["amount"]
        tax_matches = [candidate for candidate in candidates if candidate["label"] == "tax"]
        selected_tax = self._select_tax_candidate(tax_matches, fields)
        if selected_tax:
            fields["tax"] = selected_tax["amount"]
            if selected_tax.get("taxPercent"):
                fields["taxPercent"] = selected_tax["taxPercent"]
                fields["taxAmount"] = selected_tax["amount"]
        self._reconcile_impossible_tax_mapping(fields, tax_matches)
        tax_relationship = self._tax_relationship(fields, tax_matches)
        return {
            "fields": fields,
            "candidates": candidates,
            "rejected": rejected[:80],
            "taxRelationship": tax_relationship,
            "taxRelationshipDiagnostics": tax_relationship.get("diagnostics", []),
            "confidence": round(sum(item["confidence"] for item in candidates) / max(len(candidates), 1), 3) if candidates else 0.0,
        }

    def _label(self, text: str) -> str:
        upper = text.upper().replace("SUB TOTAL", "SUBTOTAL")
        compact_upper = re.sub(r"[^A-Z]+", "", upper)
        if "SUBTOTAL" in upper:
            return "subtotal"
        if re.search(r"\bTAX\b|1AX|IAX", upper):
            return "tax"
        if "TIP" in upper:
            return "tip"
        if "CHANGE" in upper:
            return "change"
        if "CHARGE" in upper or "AMOUNT" in upper:
            return "charge"
        if (
            "TOTAL" in upper
            or "BALANCE" in compact_upper
            or "BAIANCE" in compact_upper
            or compact_upper in {"USD", "USDOLLAR", "DOLLARS", "TENDER", "CURRENCY"}
        ):
            return "total"
        return ""

    def _confidence(self, label: str, line: ReceiptLineGeometry) -> float:
        score = 0.55 + min(0.25, line.confidence * 0.25)
        if label in {"subtotal", "tax", "total"}:
            score += 0.12
        if re.search(r"\d{1,7}(?:[.,]\d{2})\s*$", line.text):
            score += 0.08
        return min(1.0, score)

    def _right_aligned_amount(self, line: ReceiptLineGeometry, regions: list[ReceiptRegion]) -> str:
        match = re.search(r"(?P<amount>-?\d{1,7}(?:[.,]\d{2}))\s*[A-Z]?\s*$", line.text)
        if not match:
            return ""
        max_right = max((candidate.right for region in regions for candidate in region.lines), default=line.right)
        if line.x == 0:
            return match.group("amount").replace(",", ".")
        if max_right <= 0 or line.right >= max_right * 0.68:
            return match.group("amount").replace(",", ".")
        return ""

    def _parse_split_total_rows(self, regions: list[ReceiptRegion]) -> list[dict[str, Any]]:
        lines = [line for region in regions for line in region.lines if region.kind in {"totals", "unknown"}]
        candidates: list[dict[str, Any]] = []
        for index, line in enumerate(lines):
            label = self._label(line.text)
            if not label:
                continue
            for candidate in lines[index + 1: min(len(lines), index + 4)]:
                if re.fullmatch(r"\d{1,3}", compact(candidate.text)):
                    continue
                value = self._right_aligned_amount(candidate, regions)
                if value:
                    candidates.append({
                        "label": label,
                        "amount": value,
                        "line": f"{line.text} -> {candidate.text}",
                        "confidence": min(0.96, self._confidence(label, line) + 0.08),
                    })
                    break
                if self._label(candidate.text):
                    break
        return candidates

    def _tax_percent(self, text: str) -> str:
        match = re.search(r"(?P<percent>\d{1,2}(?:[.,]\d{1,4})?)\s*%", str(text or ""))
        return match.group("percent").replace(",", ".") if match else ""

    def _select_tax_candidate(self, matches: list[dict[str, Any]], fields: dict[str, str]) -> dict[str, Any] | None:
        if not matches:
            return None
        subtotal = numeric(fields.get("subtotal"))
        total = numeric(fields.get("total"))
        expected_tax = (total - subtotal) if subtotal and total and total >= subtotal else 0.0
        if expected_tax:
            return max(
                matches,
                key=lambda item: (
                    -min(abs(numeric(item.get("amount")) - expected_tax), expected_tax),
                    float(item.get("confidence", 0.0) or 0.0),
                ),
            )
        return max(matches, key=lambda item: item["confidence"])

    def _reconcile_impossible_tax_mapping(self, fields: dict[str, str], tax_matches: list[dict[str, Any]]) -> None:
        subtotal = numeric(fields.get("subtotal"))
        total = numeric(fields.get("total"))
        tip = numeric(fields.get("tip"))
        tax = numeric(fields.get("tax"))
        if not subtotal or not total or total < subtotal:
            return
        expected_tax = round(total - subtotal - tip, 2)
        if expected_tax < 0:
            return
        current_tax_is_total = tax and abs(tax - total) <= 0.01
        current_tax_breaks_arithmetic = tax and abs((subtotal + tax + tip) - total) > max(0.35, total * 0.04)
        no_candidate_matches_expected = not any(
            abs(numeric(candidate.get("amount")) - expected_tax) <= max(0.05, total * 0.001)
            for candidate in tax_matches
        )
        if expected_tax and (current_tax_is_total or current_tax_breaks_arithmetic) and no_candidate_matches_expected:
            fields["tax"] = f"{expected_tax:.2f}"
            fields["taxAmount"] = f"{expected_tax:.2f}"
            fields["taxInferredFromArithmetic"] = "true"
            fields["rejectedTaxCandidate"] = f"{tax:.2f}" if tax else ""

    def _tax_relationship(self, fields: dict[str, str], tax_matches: list[dict[str, Any]]) -> dict[str, Any]:
        subtotal = numeric(fields.get("subtotal"))
        total = numeric(fields.get("total"))
        tax = numeric(fields.get("tax"))
        percent = fields.get("taxPercent", "")
        expected_from_percent = 0.0
        if subtotal and percent:
            try:
                expected_from_percent = subtotal * float(percent) / 100.0
            except ValueError:
                expected_from_percent = 0.0
        expected_from_total = (total - subtotal) if subtotal and total and total >= subtotal else 0.0
        diagnostics = []
        for candidate in tax_matches:
            candidate_tax = numeric(candidate.get("amount"))
            diagnostics.append({
                "line": candidate.get("line", ""),
                "taxPercent": candidate.get("taxPercent", ""),
                "taxAmount": candidate.get("amount", ""),
                "confidence": candidate.get("confidence", 0),
                "deltaFromSubtotalRate": round(abs(candidate_tax - expected_from_percent), 2) if expected_from_percent else None,
                "deltaFromSubtotalTotal": round(abs(candidate_tax - expected_from_total), 2) if expected_from_total else None,
            })
        return {
            "schemaVersion": "receipt-tax-relationship-v1",
            "taxPercent": percent,
            "taxAmount": fields.get("tax", ""),
            "subtotal": fields.get("subtotal", ""),
            "total": fields.get("total", ""),
            "expectedFromPercent": f"{expected_from_percent:.2f}" if expected_from_percent else "",
            "expectedFromSubtotalTotal": f"{expected_from_total:.2f}" if expected_from_total else "",
            "inferredFromArithmetic": fields.get("taxInferredFromArithmetic") == "true",
            "rejectedTaxCandidate": fields.get("rejectedTaxCandidate", ""),
            "valid": not (
                expected_from_total
                and tax
                and abs(tax - expected_from_total) > max(0.25, expected_from_total * 0.08)
            ),
            "diagnostics": diagnostics,
        }


class PaymentParser:
    CARD_BRANDS = {
        "VISA": "VISA",
        "MASTERCARD": "MASTERCARD",
        "MASTER CARD": "MASTERCARD",
        "AMEX": "AMEX",
        "AMERICAN EXPRESS": "AMEX",
        "DISCOVER": "DISCOVER",
    }

    def parse(self, regions: list[ReceiptRegion]) -> dict[str, Any]:
        payment_lines = [line for region in regions if region.kind == "payment" for line in region.lines]
        fields = {
            "paymentMethod": "",
            "cardUsed": "",
            "cardLast4": "",
            "approvalCode": "",
            "charge": "",
        }
        candidates: list[dict[str, Any]] = []
        payment_text = " ".join(line.text for line in payment_lines)
        for index, line in enumerate(payment_lines):
            upper = line.text.upper()
            brand = self._brand(upper)
            last4 = self._last4(line.text) or self._last4_window(payment_lines, index)
            approval = self._approval(line.text)
            charge = self._charge(line.text) if any(token in upper for token in ("CHARGE", "AMOUNT", "VISA", "MASTERCARD", "AMEX", "DISCOVER")) else ""
            if brand:
                fields["paymentMethod"] = "card"
                fields["cardUsed"] = brand
            if last4:
                fields["cardLast4"] = last4
            if approval:
                fields["approvalCode"] = approval
            if charge:
                fields["charge"] = charge
            candidates.append({
                "line": line.text,
                "brand": brand,
                "last4": last4,
                "approvalCode": approval,
                "charge": charge,
                "confidence": round(min(1.0, 0.58 + line.confidence * 0.32), 3),
            })
        if not fields["cardLast4"]:
            fields["cardLast4"] = self._last4(payment_text)
        if not fields["paymentMethod"] and any("CASH" in line.text.upper() for line in payment_lines):
            fields["paymentMethod"] = "cash"
        return {
            "fields": fields,
            "candidates": candidates,
            "confidence": round(sum(item["confidence"] for item in candidates) / max(len(candidates), 1), 3) if candidates else 0.0,
        }

    def _brand(self, text: str) -> str:
        for token, brand in self.CARD_BRANDS.items():
            if token in text:
                return brand
        return ""

    def _last4(self, text: str) -> str:
        fuzzy = self._fuzzy_masked_last4(text)
        if fuzzy:
            return fuzzy
        patterns = [
            r"(?:X{2,}|\*{2,}|ENDING\s+IN|CARD\s*#?)\s*(\d{4})\b",
            r"\bLAST\s*(?:FOUR|4)\D{0,12}(\d{4})\b",
            r"\b(?:VISA|MASTERCARD|MASTER CARD|AMEX|DISCOVER)\D{0,12}(\d{4})\b",
            r"\b(\d{4})\s*$",
        ]
        for pattern in patterns:
            match = re.search(pattern, text, flags=re.IGNORECASE)
            if match:
                return match.group(1)
        return ""

    def _fuzzy_masked_last4(self, text: str) -> str:
        upper = str(text or "").upper()
        if not re.search(r"\b(?:VISA|MASTERCARD|MASTER CARD|AMEX|DISCOVER|CREDIT|DEBIT|CARD|ANEX|QHEX|EX)\b", upper):
            return ""
        if len(re.findall(r"[XK*]", upper)) < 6:
            return ""
        searchable = re.split(r"\b(?:AMOUNT|ANOUNT|ANGUNT|AUTH|RUTH|QAUTH|TOTAL|REF)\b", upper)[0]
        matches = re.findall(r"[A-Z0-9*?]{8,}", searchable)
        for token in reversed(matches):
            if len(re.findall(r"[XK*]", token)) < 6:
                continue
            tail = re.sub(r"[^A-Z0-9?]", "", token)[-4:]
            digits = self._normalize_masked_tail(tail)
            if len(digits) >= 4:
                return digits[-4:]
        return ""

    def _normalize_masked_tail(self, value: str) -> str:
        mapping = {
            "O": "0",
            "Q": "0",
            "D": "0",
            "B": "8",
            "H": "8",
            "G": "8",
            "S": "5",
            "?": "7",
        }
        output = []
        for char in re.sub(r"[^A-Z0-9?]", "", value.upper()):
            if char.isdigit():
                output.append(char)
            elif char in mapping:
                output.append(mapping[char])
        return "".join(output)

    def _last4_window(self, lines: list[Any], index: int) -> str:
        current = lines[index].text
        if not re.search(r"\bLAST\s*(?:FOUR|4)\b|\bCARD\s*LAST\b|\bENDING\s+IN\b|\b(?:VISA|MASTERCARD|MASTER CARD|AMEX|DISCOVER)\b", current, flags=re.IGNORECASE):
            return ""
        for line in lines[index: min(len(lines), index + 4)]:
            if re.search(r"\b(?:AUTH|APPROVAL|APPR|NOT\s+SET)\b", line.text, flags=re.IGNORECASE):
                continue
            match = re.search(r"\b(\d{4})\b", line.text)
            if match:
                return match.group(1)
        return ""

    def _approval(self, text: str) -> str:
        patterns = [
            r"\bAUTH\s*CODE[\s#:.-]*([A-Z0-9]{4,12})\b",
            r"\b(?:APPROVAL|APPR(?:OVED)?)[\s#:.-]*([A-Z0-9]{4,12})\b",
            r"\bAUTH[\s#:.-]+(?!CODE\b)([A-Z0-9]{4,12})\b",
        ]
        for pattern in patterns:
            match = re.search(pattern, text, flags=re.IGNORECASE)
            if match:
                return match.group(1)
        return ""

    def _charge(self, text: str) -> str:
        match = re.search(r"-?\d{1,7}(?:[.,]\d{2})(?=\b|[A-Z])", text, flags=re.IGNORECASE)
        return match.group(0).replace(",", ".") if match else ""


class ReceiptDocumentStateMachine:
    STATE_BY_REGION = {
        "header": "HEADER",
        "items": "ITEMS",
        "totals": "TOTALS",
        "payment": "PAYMENT",
        "footer": "FOOTER",
        "unknown": "HEADER",
    }
    PARSER_BY_STATE = {
        "HEADER": "header",
        "ITEMS": "items",
        "TOTALS": "totals",
        "PAYMENT": "payment",
        "FOOTER": "footer",
    }
    ALLOWED_TRANSITIONS = {
        "HEADER": {"HEADER", "ITEMS", "TOTALS", "PAYMENT", "FOOTER"},
        "ITEMS": {"ITEMS", "TOTALS", "PAYMENT", "FOOTER"},
        "TOTALS": {"TOTALS", "PAYMENT", "FOOTER"},
        "PAYMENT": {"PAYMENT", "FOOTER"},
        "FOOTER": {"FOOTER"},
    }

    def run(self, regions: list[ReceiptRegion]) -> dict[str, Any]:
        state = "HEADER"
        transitions: list[dict[str, Any]] = []
        line_states: list[dict[str, Any]] = []
        violations: list[dict[str, Any]] = []
        for region in regions:
            proposed = self.STATE_BY_REGION.get(region.kind, state)
            next_state = proposed if proposed in self.ALLOWED_TRANSITIONS.get(state, {state}) else state
            if proposed != next_state:
                violations.append({
                    "from": state,
                    "proposed": proposed,
                    "region": region.kind,
                    "start": region.start,
                    "end": region.end,
                    "reason": "illegal_backward_or_cross_parser_transition",
                })
            if next_state != state:
                transitions.append({
                    "from": state,
                    "to": next_state,
                    "region": region.kind,
                    "start": region.start,
                    "end": region.end,
                    "confidence": round(region.confidence, 3),
                    "reasons": region.reasons[:8],
                })
                state = next_state
            for line in region.lines:
                line_states.append({
                    "lineIndex": line.index,
                    "text": line.text,
                    "region": region.kind,
                    "state": state,
                    "activeParser": self.PARSER_BY_STATE[state],
                    "confidence": round(min(1.0, (line.confidence * 0.65) + (region.confidence * 0.35)), 3),
                    "bbox": {
                        "x": round(line.x, 2),
                        "y": round(line.y, 2),
                        "width": round(line.width, 2),
                        "height": round(line.height, 2),
                    },
                })
        state_counts = {state_name: sum(1 for row in line_states if row["state"] == state_name) for state_name in DOCUMENT_STATES}
        confidence = sum(row["confidence"] for row in line_states) / max(len(line_states), 1) if line_states else 0.0
        return {
            "schemaVersion": "receipt-state-machine-v1",
            "states": list(DOCUMENT_STATES),
            "lineStates": line_states,
            "transitions": transitions,
            "violations": violations,
            "stateLineCounts": state_counts,
            "confidence": round(confidence, 3),
        }


class SectionAwareItemParser:
    def parse(self, regions: list[ReceiptRegion]) -> list[dict[str, Any]]:
        return self.parse_with_diagnostics(regions)["items"]

    def parse_with_diagnostics(self, regions: list[ReceiptRegion]) -> dict[str, Any]:
        items: list[dict[str, Any]] = []
        rejected: list[dict[str, Any]] = []
        max_right = max((line.right for region in regions for line in region.lines), default=0.0)
        lock = self._boundary_lock(regions)
        for region in regions:
            if region.kind in SECTION_LOCK_KINDS:
                for line in region.lines:
                    reason = "locked_non_item_region"
                    if self._looks_like_survey_or_barcode(line.text.upper()):
                        reason += ",survey_or_barcode_numeric_row"
                    rejected.append(self._reject(line, reason, region.kind, lock))
                continue
            if region.kind != "items":
                for line in region.lines:
                    if self._looks_like_monetary_row(line.text):
                        reason = "non_item_region_monetary_row"
                        if self._after_item_boundary(line, lock):
                            reason += ",after_item_region_boundary"
                        if self._is_near_section_keyword(line.text.upper()):
                            reason += ",ocr_mutation_of_section_keyword"
                        rejected.append(self._reject(line, reason, region.kind, lock))
                continue
            for line in region.lines:
                if self._after_item_boundary(line, lock):
                    rejected.append(self._reject(line, "after_item_region_boundary", region.kind, lock))
                    continue
                parsed, reasons, score = self._parse_line(line, max_right)
                if parsed:
                    parsed["confidenceTrace"] = {
                        "score": score,
                        "reasons": reasons,
                        "rightAlignedAmount": self._has_right_aligned_amount(line, max_right),
                        "boundary": lock,
                    }
                    items.append(parsed)
                else:
                    rejected.append(self._reject(line, ",".join(reasons) or "invalid_item_row", region.kind, lock, score))
        split_items, split_rejected = self._parse_split_item_rows(regions, max_right, lock)
        existing_line_indexes = {item.get("lineIndex") for item in items}
        for item in split_items:
            if item.get("lineIndex") not in existing_line_indexes:
                items.append(item)
                existing_line_indexes.add(item.get("lineIndex"))
        rejected.extend(split_rejected)
        items = [{**item, "id": index + 1} for index, item in enumerate(items)]
        return {
            "items": items,
            "rejected": rejected[:120],
            "boundary": lock,
        }

    def _parse_split_item_rows(
        self,
        regions: list[ReceiptRegion],
        max_right: float,
        lock: dict[str, Any],
    ) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
        lines = [line for region in regions for line in region.lines if region.kind not in {"payment", "footer"}]
        region_by_index = {line.index: region.kind for region in regions for line in region.lines}
        items: list[dict[str, Any]] = []
        rejected: list[dict[str, Any]] = []
        used_price_indexes: set[int] = set()
        for position, line in enumerate(lines):
            name = self._clean_split_item_name(line.text)
            upper = name.upper()
            if not self._can_be_split_item_name(name):
                continue
            price_line = self._find_following_price_line(lines, position, used_price_indexes)
            if price_line is None:
                continue
            value = amount(price_line.text)
            qty, name = self._leading_quantity_and_name(name)
            score, score_reasons = self._plausibility_score(name, line, max_right)
            region = region_by_index.get(line.index, "unknown")
            if region in {"totals", "payment", "footer"}:
                score -= 0.22
                score_reasons.append("split_item_name_in_locked_region")
            if self._after_item_boundary(line, lock):
                score -= 0.16
                score_reasons.append("split_item_after_totals_boundary")
            if score < 0.36:
                rejected.append(self._reject(line, ",".join(sorted(set(score_reasons))) or "low_split_item_plausibility", region, lock, score))
                continue
            used_price_indexes.add(price_line.index)
            items.append({
                "name": name,
                "qty": self._split_quantity_between(lines, position, price_line.index) or qty,
                "count": self._split_quantity_between(lines, position, price_line.index) or qty,
                "amount": value,
                "price": value,
                "confidence": round(max(0.0, min(1.0, score + line.confidence * 0.12 + price_line.confidence * 0.1)), 3),
                "lineIndex": line.index,
                "bbox": {
                    "x": round(line.x, 2),
                    "y": round(line.y, 2),
                    "width": round(max(line.width, price_line.width), 2),
                    "height": round((price_line.y + price_line.height) - line.y, 2),
                },
                "confidenceTrace": {
                    "score": round(score, 3),
                    "reasons": sorted(set(["split_name_quantity_price_candidate", *score_reasons])),
                    "priceLineIndex": price_line.index,
                    "boundary": lock,
                },
            })
        return items, rejected

    def _can_be_split_item_name(self, value: str) -> bool:
        upper = compact(self._clean_split_item_name(value)).upper()
        if len(upper) < 3 or not re.search(r"[A-Z]{3,}", upper):
            return False
        if re.fullmatch(r"-?\$?\d{1,7}(?:[.,]\d{2})\s*[A-Z]?", upper, flags=re.IGNORECASE):
            return False
        if upper in {"QUANTITY", "QTY", "PRICE", "AMOUNT", "ITEM", "ITEMS"}:
            return False
        if any(keyword in upper for keyword in ITEM_EXCLUSION_KEYWORDS):
            return False
        if self._is_near_section_keyword(upper):
            return False
        return True

    def _clean_split_item_name(self, value: str) -> str:
        cleaned = compact(value).strip(" -_:;~")
        candidate = re.sub(r"^[^A-Za-z]{1,8}", "", cleaned).strip(" -_:;~")
        if candidate and re.search(r"[A-Za-z]{3,}", candidate):
            return candidate
        return cleaned

    def _find_following_price_line(
        self,
        lines: list[ReceiptLineGeometry],
        position: int,
        used_price_indexes: set[int],
    ) -> ReceiptLineGeometry | None:
        for candidate in lines[position + 1: min(len(lines), position + 4)]:
            if candidate.index in used_price_indexes:
                continue
            text = compact(candidate.text)
            upper = text.upper()
            if any(keyword in upper for keyword in TOTAL_KEYWORDS + PAYMENT_KEYWORDS + FOOTER_KEYWORDS):
                return None
            if self._is_near_section_keyword(upper):
                return None
            if re.fullmatch(r"\d{1,3}", text):
                continue
            if amount(text) and re.fullmatch(r"-?\$?\d{1,7}(?:[.,\s)\]]\s*\d{2})\s*[A-Z]?", text, flags=re.IGNORECASE):
                return candidate
            if self._can_be_split_item_name(text):
                return None
        return None

    def _split_quantity_between(self, lines: list[ReceiptLineGeometry], start_position: int, price_index: int) -> str:
        for candidate in lines[start_position + 1:]:
            if candidate.index == price_index:
                break
            text = compact(candidate.text)
            if re.fullmatch(r"\d{1,3}", text):
                return text
        return "1"

    def _parse_line(self, line: ReceiptLineGeometry, max_right: float) -> tuple[dict[str, Any] | None, list[str], float]:
        reasons: list[str] = []
        upper = line.text.upper()
        if any(keyword in upper for keyword in ITEM_EXCLUSION_KEYWORDS):
            reasons.append("section_keyword_in_item_candidate")
        if self._is_near_section_keyword(upper):
            reasons.append("ocr_mutation_of_section_keyword")
        if self._looks_like_survey_or_barcode(upper):
            reasons.append("survey_or_barcode_numeric_row")
        match = re.search(r"(?P<name>.+?)\s+(?P<amount>-?\$?\d{1,7}(?:[.,\s)\]]\s*\d{2}))\s*[A-Z]?$", line.text)
        if not match:
            reasons.append("missing_terminal_money_value")
            return None, reasons, 0.0
        if not self._has_right_aligned_amount(line, max_right):
            reasons.append("money_value_not_right_aligned")
        name = compact(match.group("name")).strip(" -_:;")
        value = amount(match.group("amount"))
        if len(name) < 3 or not re.search(r"[A-Za-z]{3,}", name) or not value:
            reasons.append("weak_product_text")
        qty_match = re.match(r"^(?P<qty>\d{1,3})\s+(?:EA\s+)?(?P<name>[A-Za-z].+)$", name, flags=re.IGNORECASE)
        qty = "1"
        if qty_match:
            qty = qty_match.group("qty")
            name = compact(qty_match.group("name"))
        inline_qty_match = re.match(
            r"^(?P<name>.+?)\s+(?P<qty>\d{1,3})\s*(?:@|X|x)\s*\d{1,7}(?:[.,]\d{2})$",
            name,
            flags=re.IGNORECASE,
        )
        if inline_qty_match:
            qty = inline_qty_match.group("qty")
            name = compact(inline_qty_match.group("name"))
        score, score_reasons = self._plausibility_score(name, line, max_right)
        reasons.extend(score_reasons)
        if reasons or score < 0.52:
            if score < 0.52:
                reasons.append("low_retail_item_plausibility")
            return None, sorted(set(reasons)), score
        return {
            "name": name,
            "qty": qty,
            "count": qty,
            "amount": value,
            "price": value,
            "confidence": round(min(1.0, score + line.confidence * 0.16), 3),
            "lineIndex": line.index,
            "bbox": {
                "x": round(line.x, 2),
                "y": round(line.y, 2),
                "width": round(line.width, 2),
                "height": round(line.height, 2),
            },
        }, sorted(set(score_reasons)), score

    def _leading_quantity_and_name(self, name: str) -> tuple[str, str]:
        match = re.match(r"^(?P<qty>\d{1,3})\s+(?P<name>[A-Za-z].+)$", compact(name), flags=re.IGNORECASE)
        if not match:
            return "1", compact(name)
        return match.group("qty"), compact(match.group("name"))

    def _boundary_lock(self, regions: list[ReceiptRegion]) -> dict[str, Any]:
        item_regions = [region for region in regions if region.kind == "items"]
        locked_regions = [region for region in regions if region.kind in SECTION_LOCK_KINDS]
        first_lock = min((region.start for region in locked_regions), default=None)
        first_lock_y = min((line.y for region in locked_regions for line in region.lines), default=None)
        if item_regions:
            item_start = min(line.y for region in item_regions for line in region.lines)
            item_end = max(line.y + line.height for region in item_regions for line in region.lines if first_lock is None or line.index < first_lock)
        else:
            item_start = None
            item_end = None
        return {
            "firstLockedIndex": first_lock,
            "firstLockedY": round(first_lock_y, 2) if first_lock_y is not None else None,
            "itemRegionY": {
                "top": round(item_start, 2) if item_start is not None else None,
                "bottom": round(item_end, 2) if item_end is not None else None,
            },
            "lockedKinds": sorted({region.kind for region in locked_regions}),
        }

    def _after_item_boundary(self, line: ReceiptLineGeometry, lock: dict[str, Any]) -> bool:
        first_index = lock.get("firstLockedIndex")
        first_y = lock.get("firstLockedY")
        if first_index is not None and line.index >= first_index:
            return True
        if first_y is not None and line.y >= float(first_y):
            return True
        return False

    def _has_right_aligned_amount(self, line: ReceiptLineGeometry, max_right: float) -> bool:
        if not re.search(r"\d{1,7}(?:[.,\s)\]]\s*\d{2})\s*[A-Z]?\s*$", line.text):
            return False
        if line.x == 0:
            return True
        return max_right <= 0 or line.right >= max_right * 0.68

    def _looks_like_monetary_row(self, text: str) -> bool:
        return bool(re.search(r"\d{1,7}(?:[.,\s)\]]\s*\d{2})\s*[A-Z]?\s*$", text))

    def _looks_like_survey_or_barcode(self, upper: str) -> bool:
        if any(token in upper for token in ("SURVEY", "BARCODE", "COUPON", "REWARD", "RECEIPT ID")):
            return True
        digits = re.sub(r"\D", "", upper)
        return len(digits) >= 8 and not re.search(r"\d{1,7}[.,]\d{2}", upper)

    def _is_near_section_keyword(self, upper: str) -> bool:
        token = section_keyword_token(upper)
        if len(token) < 4:
            return False
        return token_is_near_section_keyword(token)

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

    def _plausibility_score(self, name: str, line: ReceiptLineGeometry, max_right: float) -> tuple[float, list[str]]:
        reasons: list[str] = []
        upper = name.upper()
        tokens = [token for token in re.split(r"\s+", upper) if token]
        alpha_tokens = [token for token in tokens if re.search(r"[A-Z]{3,}", token)]
        score = 0.18
        if len(alpha_tokens) >= 1:
            score += 0.22
        if len(tokens) >= 2:
            score += 0.14
        if any(len(token) >= 5 for token in alpha_tokens):
            score += 0.12
        if any(hint in upper for hint in RETAIL_ITEM_HINTS):
            score += 0.12
        if self._has_right_aligned_amount(line, max_right):
            score += 0.16
        else:
            reasons.append("missing_right_aligned_price")
        if len(tokens) == 1 and len(tokens[0]) <= 5 and not any(hint in upper for hint in RETAIL_ITEM_HINTS):
            score -= 0.22
            reasons.append("short_single_token_product_name")
        if re.fullmatch(r"[A-Z]{1,4}\d{3,}|[0-9A-Z]{8,}", upper):
            score -= 0.3
            reasons.append("code_like_product_name")
        return round(max(0.0, min(1.0, score)), 3), reasons

    def _reject(self, line: ReceiptLineGeometry, reason: str, region: str, lock: dict[str, Any], score: float = 0.0) -> dict[str, Any]:
        return {
            "line": line.text,
            "lineIndex": line.index,
            "region": region,
            "reason": reason,
            "score": round(score, 3),
            "bbox": {
                "x": round(line.x, 2),
                "y": round(line.y, 2),
                "width": round(line.width, 2),
                "height": round(line.height, 2),
            },
            "boundary": lock,
        }


class ReceiptFinancialTableGraphEngine:
    """Reconstructs receipt item rows as a table graph using selected items and OCR geometry."""

    def reconstruct(
        self,
        regions: list[ReceiptRegion],
        selected_items: list[dict[str, Any]],
        item_result: dict[str, Any],
        totals: dict[str, Any],
        payment: dict[str, Any],
    ) -> dict[str, Any]:
        lines_by_index = {line.index: line for region in regions for line in region.lines}
        rows = [self._row(index, item, lines_by_index) for index, item in enumerate(selected_items)]
        nodes: list[dict[str, Any]] = []
        edges: list[dict[str, Any]] = []
        for row in rows:
            row_id = row["id"]
            nodes.append({
                "id": row_id,
                "type": "ITEM_ROW",
                "text": row["description"],
                "confidence": row["confidence"],
                "bbox": row["bbox"],
                "lineIndexes": row["lineIndexes"],
            })
            for column in ("quantity", "description", "unitPrice", "extendedPrice"):
                value = row.get(column, "")
                if value in ("", None):
                    continue
                node_id = f"{row_id}-{column}"
                nodes.append({
                    "id": node_id,
                    "type": column,
                    "value": value,
                    "confidence": row["confidence"],
                    "bbox": row["bbox"],
                })
                edges.append({"from": row_id, "to": node_id, "type": f"HAS_{column.upper()}"})
            if row["rowIndex"] > 0:
                edges.append({"from": rows[row["rowIndex"] - 1]["id"], "to": row_id, "type": "NEXT_TABLE_ROW"})
        totals_fields = totals.get("fields", {}) if isinstance(totals, dict) else {}
        for label in ("subtotal", "tax", "total", "charge"):
            value = totals_fields.get(label) or (payment.get("fields", {}) if isinstance(payment, dict) else {}).get(label)
            if value:
                node_id = f"receipt-{label}"
                nodes.append({"id": node_id, "type": "TOTAL_FIELD", "label": label, "value": value})
                if rows:
                    edges.append({"from": rows[-1]["id"], "to": node_id, "type": "ROLLS_UP_TO"})
        return {
            "schemaVersion": "receipt-table-graph-v1",
            "columns": [
                {"id": "quantity", "role": "quantity", "alignment": "left"},
                {"id": "description", "role": "item_description", "alignment": "left"},
                {"id": "unitPrice", "role": "unit_price", "alignment": "right"},
                {"id": "extendedPrice", "role": "line_total", "alignment": "right"},
            ],
            "rows": rows,
            "nodes": nodes,
            "edges": edges,
            "columnOverlays": self._column_overlays(regions, rows),
            "rowReconstructionVisualization": [
                {
                    "label": f"ROW {row['rowIndex'] + 1}",
                    "bbox": row["bbox"],
                    "lineIndexes": row["lineIndexes"],
                    "description": row["description"],
                    "amount": row["extendedPrice"],
                }
                for row in rows
            ],
            "diagnostics": {
                "candidateGraph": item_result.get("candidateGraph", {}),
                "duplicateClusters": item_result.get("duplicateClusters", []),
                "financialReconciliation": item_result.get("financialReconciliation", {}),
                "rejectedRows": item_result.get("rejected", [])[:80],
            },
        }

    def _row(self, index: int, item: dict[str, Any], lines_by_index: dict[int, ReceiptLineGeometry]) -> dict[str, Any]:
        qty = compact(item.get("qty") or item.get("count") or "1")
        extended = amount(item.get("amount") or item.get("price"))
        unit = self._unit_price(qty, extended)
        line_indexes = self._line_indexes(item)
        bbox = item.get("bbox") or self._bbox_for_lines([lines_by_index[line_index] for line_index in line_indexes if line_index in lines_by_index])
        return {
            "id": f"table-row-{index + 1}",
            "rowIndex": index,
            "quantity": qty or "1",
            "description": compact(item.get("name")),
            "unitPrice": unit,
            "extendedPrice": extended,
            "amount": extended,
            "confidence": round(float(item.get("confidence", item.get("weight", 0.0)) or 0.0), 3),
            "spatialConfidence": self._spatial_confidence(item, lines_by_index),
            "semanticConfidence": item.get("semanticProductScore", 0),
            "lineIndexes": line_indexes,
            "bbox": bbox,
            "relationships": {
                "quantityToAmount": "quantity_times_unit_price_equals_extended_price" if qty and unit and extended else "unresolved",
                "source": "selected_item_after_global_reconciliation",
            },
            "confidenceTrace": item.get("confidenceTrace", {}),
        }

    def _line_indexes(self, item: dict[str, Any]) -> list[int]:
        indexes: list[int] = []
        for value in (
            item.get("lineIndex"),
            (item.get("confidenceTrace") or {}).get("priceLineIndex"),
        ):
            if isinstance(value, int) and value not in indexes:
                indexes.append(value)
        return indexes

    def _unit_price(self, qty: str, extended: str) -> str:
        try:
            quantity = float(str(qty or "1").replace(",", "."))
            amount_value = float(extended)
        except (TypeError, ValueError):
            return extended
        if quantity <= 0:
            return extended
        return f"{amount_value / quantity:.2f}"

    def _bbox_for_lines(self, lines: list[ReceiptLineGeometry]) -> dict[str, float]:
        if not lines:
            return {}
        left = min(line.x for line in lines)
        top = min(line.y for line in lines)
        right = max(line.right for line in lines)
        bottom = max(line.y + line.height for line in lines)
        return {
            "x": round(left, 2),
            "y": round(top, 2),
            "width": round(right - left, 2),
            "height": round(bottom - top, 2),
        }

    def _spatial_confidence(self, item: dict[str, Any], lines_by_index: dict[int, ReceiptLineGeometry]) -> float:
        indexes = self._line_indexes(item)
        if not indexes:
            return 0.62
        lines = [lines_by_index[index] for index in indexes if index in lines_by_index]
        if not lines:
            return 0.62
        right_aligned = any(re.search(r"\d{1,7}(?:[.,]\d{2})\s*[A-Z]?\s*$", line.text) for line in lines)
        score = sum(line.confidence for line in lines) / max(len(lines), 1)
        if right_aligned:
            score += 0.08
        return round(min(1.0, score), 3)

    def _column_overlays(self, regions: list[ReceiptRegion], rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
        if not rows:
            return []
        item_lines = [line for region in regions if region.kind == "items" for line in region.lines]
        if not item_lines:
            return []
        left = min(line.x for line in item_lines)
        right = max(line.right for line in item_lines)
        top = min(line.y for line in item_lines)
        bottom = max(line.y + line.height for line in item_lines)
        width = max(1.0, right - left)
        return [
            {"column": "quantity", "bbox": {"x": round(left, 2), "y": round(top, 2), "width": round(width * 0.16, 2), "height": round(bottom - top, 2)}},
            {"column": "description", "bbox": {"x": round(left + width * 0.12, 2), "y": round(top, 2), "width": round(width * 0.58, 2), "height": round(bottom - top, 2)}},
            {"column": "amount", "bbox": {"x": round(left + width * 0.7, 2), "y": round(top, 2), "width": round(width * 0.3, 2), "height": round(bottom - top, 2)}},
        ]


class ReceiptSectionConfidenceEngine:
    def score(self, regions: list[ReceiptRegion], totals: dict[str, Any], payment: dict[str, Any], items: list[dict[str, Any]], validation: dict[str, Any] | None = None, state_machine: dict[str, Any] | None = None) -> dict[str, float]:
        region_score = min(1.0, len([region for region in regions if region.kind != "unknown"]) / max(len(regions), 1)) if regions else 0.0
        totals_score = totals.get("confidence", 0.0)
        payment_score = payment.get("confidence", 0.0)
        item_confidences = [float(item.get("confidence", item.get("weight", 0.0)) or 0.0) for item in items]
        items_score = sum(item_confidences) / max(len(item_confidences), 1) if item_confidences else 0.0
        ocr_score = sum(line.confidence for region in regions for line in region.lines) / max(sum(len(region.lines) for region in regions), 1) if regions else 0.0
        arithmetic_score = 1.0 if (validation or {}).get("valid") else 0.58
        semantic_score = ((state_machine or {}).get("confidence") or 0.0) * 0.42 + region_score * 0.28 + items_score * 0.3
        overall = (
            region_score * 0.18
            + totals_score * 0.18
            + payment_score * 0.1
            + items_score * 0.2
            + ocr_score * 0.16
            + arithmetic_score * 0.1
            + semantic_score * 0.08
        )
        return {
            "overall": round(overall, 3),
            "regions": round(region_score, 3),
            "totals": round(totals_score, 3),
            "payment": round(payment_score, 3),
            "items": round(items_score, 3),
            "ocr": round(ocr_score, 3),
            "arithmetic": round(arithmetic_score, 3),
            "semantic": round(semantic_score, 3),
            "merchant": 0.0,
        }


class ReceiptSectionValidationEngine:
    def validate(self, totals: dict[str, Any], payment: dict[str, Any], items: list[dict[str, Any]]) -> dict[str, Any]:
        fields = totals.get("fields", {})
        subtotal = numeric(fields.get("subtotal"))
        tax = numeric(fields.get("taxAmount") or fields.get("tax"))
        total = numeric(fields.get("total"))
        charge = numeric(payment.get("fields", {}).get("charge") or fields.get("charge"))
        item_sum = sum(numeric(item.get("amount")) for item in items)
        warnings: list[str] = []
        if subtotal and total and tax and abs((subtotal + tax) - total) > max(0.35, total * 0.04):
            warnings.append("subtotal_tax_total_mismatch")
        if total and charge and abs(total - charge) > max(0.25, total * 0.03):
            warnings.append("payment_charge_total_mismatch")
        if subtotal and item_sum and abs(item_sum - subtotal) > max(0.35, subtotal * 0.05):
            warnings.append("item_sum_subtotal_mismatch")
        arithmetic_checks = [
            {
                "name": "items_vs_subtotal",
                "left": round(item_sum, 2),
                "right": round(subtotal, 2),
                "delta": round(abs(item_sum - subtotal), 2) if subtotal and item_sum else None,
                "valid": not (subtotal and item_sum and abs(item_sum - subtotal) > max(0.35, subtotal * 0.05)),
            },
            {
                "name": "subtotal_plus_tax_vs_total",
                "left": round(subtotal + tax, 2) if subtotal or tax else None,
                "right": round(total, 2) if total else None,
                "delta": round(abs((subtotal + tax) - total), 2) if subtotal and total and tax else None,
                "valid": not (subtotal and total and tax and abs((subtotal + tax) - total) > max(0.35, total * 0.04)),
            },
            {
                "name": "payment_charge_vs_total",
                "left": round(charge, 2) if charge else None,
                "right": round(total, 2) if total else None,
                "delta": round(abs(total - charge), 2) if total and charge else None,
                "valid": not (total and charge and abs(total - charge) > max(0.25, total * 0.03)),
            },
        ]
        return {
            "itemSum": f"{item_sum:.2f}" if item_sum else "0",
            "warnings": warnings,
            "valid": not warnings,
            "arithmeticChecks": arithmetic_checks,
        }


class ReceiptSectionExtractionEngine:
    def __init__(self) -> None:
        self.geometry = ReceiptGeometryBuilder()
        self.classifier = ReceiptRegionClassifier()
        self.totals = TotalsParser()
        self.payment = PaymentParser()
        self.state_machine = ReceiptDocumentStateMachine()
        self.items = SectionAwareItemParser()
        self.confidence = ReceiptSectionConfidenceEngine()
        self.validation = ReceiptSectionValidationEngine()
        self.visual_hierarchy = ReceiptVisualHierarchyEngine()
        self.table_graph = ReceiptFinancialTableGraphEngine()

    def extract(
        self,
        raw_text: str = "",
        lines: list[str] | None = None,
        ocr_blocks: list[dict[str, Any]] | None = None,
    ) -> dict[str, Any]:
        geometry = self.geometry.from_inputs(raw_text=raw_text, lines=lines, boxes=ocr_blocks)
        visual_hierarchy = self.visual_hierarchy.analyze(geometry)
        regions = self.classifier.classify(geometry)
        state_machine = self.state_machine.run(regions)
        totals = self.totals.parse(regions)
        payment = self.payment.parse(regions)
        item_result = self.items.parse_with_diagnostics(regions)
        self._collapse_duplicate_item_candidates(item_result)
        cardinality = self._detect_item_cardinality(geometry)
        item_result["cardinality"] = cardinality
        self._rescue_global_item_candidates(item_result, geometry, totals, payment, cardinality)
        candidate_items = self._filter_financially_impossible_items(item_result, totals, payment)
        item_result["items"] = candidate_items
        items = self._reconcile_item_candidates(item_result, totals, payment, cardinality)
        validation = self.validation.validate(totals, payment, items)
        confidence = self.confidence.score(regions, totals, payment, items, validation, state_machine)
        table_graph = self.table_graph.reconstruct(regions, items, item_result, totals, payment)
        debug = self._debug(regions, item_result, totals, payment, validation, table_graph)
        layout_graph = self._layout_graph(regions, state_machine, item_result, totals, payment, visual_hierarchy, table_graph)
        logger.info(
            "Receipt sections extracted regions=%s items=%s rejected_items=%s totals=%s payment=%s warnings=%s boundary=%s",
            len(regions),
            len(items),
            len(item_result.get("rejected", [])),
            totals.get("fields", {}),
            payment.get("fields", {}),
            validation["warnings"],
            item_result.get("boundary", {}),
        )
        return {
            "schemaVersion": "receipt-sections-v1",
            "architecture": "enterprise-receipt-orchestration",
            "documentStateMachine": state_machine,
            "visualHierarchy": visual_hierarchy,
            "parserIsolation": {
                "itemsParserActiveOnlyIn": ["ITEMS"],
                "totalsParserActiveOnlyIn": ["TOTALS"],
                "paymentParserActiveOnlyIn": ["PAYMENT"],
                "footerIgnoredForItems": True,
                "hardBoundaries": sorted(SECTION_LOCK_KINDS),
            },
            "regions": [region.to_dict() for region in regions],
            "layoutGraph": layout_graph,
            "tableGraph": table_graph,
            "totals": totals,
            "payment": payment,
            "items": items,
            "itemCandidateGraph": item_result.get("candidateGraph", {}),
            "itemCardinality": cardinality,
            "financialReconciliation": item_result.get("financialReconciliation", {}),
            "confidence": confidence,
            "validation": validation,
            "debug": {**debug, "visualHierarchy": visual_hierarchy},
        }

    def _rescue_global_item_candidates(
        self,
        item_result: dict[str, Any],
        lines: list[ReceiptLineGeometry],
        totals: dict[str, Any],
        payment: dict[str, Any],
        cardinality: dict[str, Any],
    ) -> None:
        target = self._item_reconciliation_target(totals, payment)
        expected_count = cardinality.get("count") if isinstance(cardinality, dict) else None
        if not target and not expected_count:
            return
        existing = list(item_result.get("items", []))
        existing_sum = sum(numeric(item.get("amount") or item.get("price")) for item in existing)
        existing_count = len(existing)
        count_mismatch = bool(expected_count and existing_count != expected_count)
        total_mismatch = bool(target and abs(existing_sum - target) > max(0.35, target * 0.04))
        if existing and not count_mismatch and not total_mismatch:
            return
        max_right = max((line.right for line in lines), default=0.0)
        rescued: list[dict[str, Any]] = []
        rejected = item_result.setdefault("rejected", [])
        seen_keys = {
            self._item_candidate_key(item)
            for item in existing
            if self._item_candidate_key(item)
        }
        for line in lines:
            item, reasons, score = self._parse_global_item_candidate(line, max_right)
            if item:
                key = self._item_candidate_key(item)
                if key in seen_keys:
                    continue
                seen_keys.add(key)
                rescued.append(item)
            elif self.items._looks_like_monetary_row(line.text):
                rejected.append({
                    "line": line.text,
                    "lineIndex": line.index,
                    "region": "global_rescue",
                    "reason": ",".join(reasons) or "global_rescue_rejected",
                    "score": round(score, 3),
                    "boundary": item_result.get("boundary", {}),
                })
        if not rescued:
            return
        self._apply_cross_pass_support(rescued, lines)
        item_result["items"] = [*existing, *rescued]
        item_result.setdefault("globalRescueDiagnostics", []).append({
            "reason": "section_candidates_failed_financial_constraints",
            "targetTotal": f"{target:.2f}" if target else "",
            "expectedItemCount": expected_count,
            "existingCandidateCount": existing_count,
            "existingCandidateSum": f"{existing_sum:.2f}" if existing_sum else "0",
            "candidateCount": len(rescued),
        })
        self._collapse_duplicate_item_candidates(item_result)

    def _apply_cross_pass_support(self, items: list[dict[str, Any]], lines: list[ReceiptLineGeometry]) -> None:
        corpus = "\n".join(line.text.upper() for line in lines)
        for item in items:
            name = str(item.get("name") or "")
            tokens = [
                token
                for token in re.split(r"[^A-Z0-9]+", name.upper())
                if len(token) >= 3 and not token.isdigit()
            ]
            if not tokens:
                continue
            repeated = sum(1 for token in tokens if len(re.findall(rf"\b{re.escape(token)}\b", corpus)) >= 2)
            support = repeated / max(len(tokens), 1)
            item["confidence"] = round(min(1.0, float(item.get("confidence", 0.0) or 0.0) + support * 0.1), 3)
            item.setdefault("confidenceTrace", {}).setdefault("reasons", []).append("cross_pass_ocr_token_support")
            item["confidenceTrace"]["crossPassSupport"] = round(support, 3)

    def _item_candidate_key(self, item: dict[str, Any]) -> str:
        name = re.sub(r"[^A-Z0-9]+", " ", str(item.get("name") or "").upper()).strip()
        value = amount(item.get("amount") or item.get("price"))
        if not name or not value:
            return ""
        return f"{name}:{value}"

    def _parse_global_item_candidate(
        self,
        line: ReceiptLineGeometry,
        max_right: float,
    ) -> tuple[dict[str, Any] | None, list[str], float]:
        text = compact(line.text)
        upper = text.upper()
        reasons: list[str] = []
        if any(keyword in upper for keyword in ITEM_EXCLUSION_KEYWORDS):
            reasons.append("section_keyword_in_global_candidate")
        if self.items._is_near_section_keyword(upper):
            reasons.append("ocr_mutation_of_section_keyword")
        if self.items._looks_like_survey_or_barcode(upper):
            reasons.append("survey_or_barcode_numeric_row")
        match = re.search(
            r"(?P<name>.+?)\s+(?P<amount>-?\$?\d{1,7}(?:[.,\s)\]]\s*\d{2}))(?P<suffix>\s*(?:N\s*F|NF|F|TAX)?\s*)$",
            text,
            flags=re.IGNORECASE,
        )
        if not match:
            reasons.append("missing_terminal_money_value")
            return None, reasons, 0.0
        name = compact(match.group("name")).strip(" -_:;~")
        qty, name = self.items._leading_quantity_and_name(name)
        value = amount(match.group("amount"))
        if not name or not value:
            reasons.append("missing_name_or_amount")
        if len(name) < 3 or not re.search(r"[A-Za-z]{3,}", name):
            reasons.append("weak_product_text")
        score, score_reasons = self.items._plausibility_score(name, line, max_right)
        score_reasons = [reason for reason in score_reasons if reason != "missing_right_aligned_price"]
        reasons.extend(score_reasons)
        if reasons or score < 0.5:
            if score < 0.5:
                reasons.append("low_global_product_plausibility")
            return None, sorted(set(reasons)), score
        return {
            "name": name,
            "qty": qty,
            "count": qty,
            "amount": value,
            "price": value,
            "confidence": round(min(1.0, score + line.confidence * 0.12), 3),
            "lineIndex": line.index,
            "bbox": {
                "x": round(line.x, 2),
                "y": round(line.y, 2),
                "width": round(line.width, 2),
                "height": round(line.height, 2),
            },
            "confidenceTrace": {
                "score": round(score, 3),
                "reasons": sorted(set(["global_financial_constraint_rescue", *score_reasons])),
            },
        }, sorted(set(score_reasons)), score

    def _collapse_duplicate_item_candidates(self, item_result: dict[str, Any]) -> None:
        items = list(item_result.get("items", []))
        if len(items) < 2:
            return
        rejected = item_result.setdefault("rejected", [])
        used: set[int] = set()
        collapsed: list[dict[str, Any]] = []
        diagnostics: list[dict[str, Any]] = []
        for index, item in enumerate(items):
            if index in used:
                continue
            cluster = [index]
            for other_index in range(index + 1, len(items)):
                if other_index in used:
                    continue
                if self._same_item_candidate(item, items[other_index]):
                    cluster.append(other_index)
                    used.add(other_index)
            winner_index = max(cluster, key=lambda item_index: float(items[item_index].get("confidence", 0) or 0))
            winner = items[winner_index]
            collapsed.append(winner)
            if len(cluster) > 1:
                suppressed = [items[item_index] for item_index in cluster if item_index != winner_index]
                diagnostics.append({
                    "winner": winner,
                    "suppressed": suppressed,
                    "reason": "fuzzy_same_item_same_price_cluster",
                })
                for suppressed_item in suppressed:
                    rejected.append({
                        "line": suppressed_item.get("name", ""),
                        "lineIndex": suppressed_item.get("lineIndex"),
                        "region": "items",
                        "reason": "duplicate_item_candidate_suppressed",
                        "score": suppressed_item.get("confidence", 0),
                        "winner": winner.get("name", ""),
                        "boundary": item_result.get("boundary", {}),
                    })
        item_result["items"] = [{**item, "id": index + 1} for index, item in enumerate(collapsed)]
        item_result["duplicateClusters"] = diagnostics

    def _same_item_candidate(self, left: dict[str, Any], right: dict[str, Any]) -> bool:
        left_amount = numeric(left.get("amount") or left.get("price"))
        right_amount = numeric(right.get("amount") or right.get("price"))
        if not left_amount or not right_amount:
            return False
        left_name = re.sub(r"[^A-Z0-9 ]+", "", str(left.get("name") or "").upper())
        right_name = re.sub(r"[^A-Z0-9 ]+", "", str(right.get("name") or "").upper())
        if not left_name or not right_name:
            return False
        left_qty = compact(left.get("qty") or left.get("count") or "1")
        right_qty = compact(right.get("qty") or right.get("count") or "1")
        same_quantity = left_qty == right_qty
        amount_delta = abs(left_amount - right_amount)
        near_duplicate_amount = amount_delta <= max(0.10, min(left_amount, right_amount) * 0.001)
        exact_amount = amount_delta <= 0.01
        if left_name == right_name:
            return exact_amount or (same_quantity and near_duplicate_amount)
        if fuzz is not None:
            similar_name = fuzz.token_set_ratio(left_name, right_name) >= 88 or fuzz.ratio(left_name, right_name) >= 86
            return similar_name and (exact_amount or (same_quantity and near_duplicate_amount))
        return one_edit_apart(left_name, right_name) and (exact_amount or (same_quantity and near_duplicate_amount))

    def _filter_financially_impossible_items(
        self,
        item_result: dict[str, Any],
        totals: dict[str, Any],
        payment: dict[str, Any],
    ) -> list[dict[str, Any]]:
        items = list(item_result.get("items", []))
        fields = totals.get("fields", {}) if isinstance(totals, dict) else {}
        payment_fields = payment.get("fields", {}) if isinstance(payment, dict) else {}
        receipt_total = numeric(fields.get("total") or payment_fields.get("charge") or fields.get("charge"))
        if receipt_total <= 0:
            return items
        threshold = max(receipt_total + 0.35, receipt_total * 1.08)
        kept: list[dict[str, Any]] = []
        rejected = item_result.setdefault("rejected", [])
        for item in items:
            item_amount = numeric(item.get("amount") or item.get("price"))
            if item_amount and item_amount > threshold:
                rejected.append({
                    "line": item.get("name", ""),
                    "lineIndex": item.get("lineIndex"),
                    "region": "items",
                    "reason": "item_amount_exceeds_receipt_total",
                    "score": item.get("confidence", 0),
                    "receiptTotal": f"{receipt_total:.2f}",
                    "itemAmount": f"{item_amount:.2f}",
                    "boundary": item_result.get("boundary", {}),
                })
                continue
            kept.append(item)
        return [{**item, "id": index + 1} for index, item in enumerate(kept)]

    def _detect_item_cardinality(self, lines: list[ReceiptLineGeometry]) -> dict[str, Any]:
        candidates: list[dict[str, Any]] = []
        patterns = (
            r"\b(?:TOTAL\s+)?(?:NUMBER\s+OF\s+)?ITEMS?\s+SOLD\D{0,12}(?P<count>\d{1,3})\b",
            r"\b(?:TOTAL\s+)?ITEM\s+COUNT\D{0,12}(?P<count>\d{1,3})\b",
            r"\b(?P<count>\d{1,3})\s+(?:ITEMS?\s+SOLD|SOLD\s+ITEMS?)\b",
        )
        for line in lines:
            upper = line.text.upper()
            for pattern in patterns:
                match = re.search(pattern, upper)
                if not match:
                    continue
                count = int(match.group("count"))
                if count <= 0:
                    continue
                confidence = 0.92 if "TOTAL" in upper or "NUMBER" in upper else 0.84
                candidates.append({
                    "count": count,
                    "line": line.text,
                    "lineIndex": line.index,
                    "confidence": confidence,
                    "bbox": {
                        "x": round(line.x, 2),
                        "y": round(line.y, 2),
                        "width": round(line.width, 2),
                        "height": round(line.height, 2),
                    },
                })
        selected = max(candidates, key=lambda item: item["confidence"], default=None)
        return {
            "schemaVersion": "receipt-item-cardinality-v1",
            "count": selected["count"] if selected else None,
            "confidence": selected["confidence"] if selected else 0.0,
            "sourceLine": selected["line"] if selected else "",
            "candidates": candidates,
        }

    def _reconcile_item_candidates(
        self,
        item_result: dict[str, Any],
        totals: dict[str, Any],
        payment: dict[str, Any],
        cardinality: dict[str, Any],
    ) -> list[dict[str, Any]]:
        candidates = list(item_result.get("items", []))
        target = self._item_reconciliation_target(totals, payment)
        expected_count = cardinality.get("count") if isinstance(cardinality, dict) else None
        candidate_graph = self._candidate_item_graph(candidates)
        item_result["candidateGraph"] = candidate_graph
        if not candidates:
            item_result["financialReconciliation"] = self._reconciliation_trace([], [], target, expected_count, "no_candidates")
            return []

        all_sum = sum(numeric(item.get("amount") or item.get("price")) for item in candidates)
        should_solve = bool(expected_count and expected_count < len(candidates))
        if target and abs(all_sum - target) > max(0.35, target * 0.04):
            should_solve = True
        if not should_solve:
            item_result["financialReconciliation"] = self._reconciliation_trace(candidates, candidates, target, expected_count, "all_candidates_consistent")
            return [{**item, "id": index + 1} for index, item in enumerate(candidates)]

        selected = self._best_item_subset(candidates, target, expected_count)
        reason = "constraint_solver_selected_subset" if selected != candidates else "all_candidates_best_subset"
        rejected = item_result.setdefault("rejected", [])
        selected_indexes = {item.get("lineIndex") for item in selected}
        for item in candidates:
            if item.get("lineIndex") in selected_indexes:
                continue
            rejected.append({
                "line": item.get("name", ""),
                "lineIndex": item.get("lineIndex"),
                "region": "items",
                "reason": "global_financial_reconciliation_rejected",
                "score": item.get("confidence", 0),
                "amount": item.get("amount") or item.get("price"),
                "targetTotal": f"{target:.2f}" if target else "",
                "expectedItemCount": expected_count,
                "boundary": item_result.get("boundary", {}),
            })
        item_result["financialReconciliation"] = self._reconciliation_trace(candidates, selected, target, expected_count, reason)
        return [{**item, "id": index + 1} for index, item in enumerate(selected)]

    def _item_reconciliation_target(self, totals: dict[str, Any], payment: dict[str, Any]) -> float:
        fields = totals.get("fields", {}) if isinstance(totals, dict) else {}
        subtotal = numeric(fields.get("subtotal"))
        tax = numeric(fields.get("tax"))
        total = numeric(fields.get("total"))
        charge = numeric((payment.get("fields", {}) if isinstance(payment, dict) else {}).get("charge") or fields.get("charge"))
        if subtotal:
            return subtotal
        if total and tax and total > tax:
            return max(0.0, total - tax)
        return total or charge

    def _best_item_subset(self, candidates: list[dict[str, Any]], target: float, expected_count: int | None) -> list[dict[str, Any]]:
        max_candidates = 18
        indexed = list(enumerate(candidates[:max_candidates]))
        if expected_count and 0 < expected_count <= len(indexed):
            sizes = [expected_count]
        else:
            sizes = list(range(1, min(len(indexed), 8) + 1))
        best_combo: tuple[int, ...] | None = None
        best_score = float("-inf")
        for size in sizes:
            for combo in combinations(range(len(indexed)), size):
                subset = [indexed[position][1] for position in combo]
                score = self._subset_score(subset, target, expected_count)
                if score > best_score:
                    best_score = score
                    best_combo = combo
        if best_combo is None:
            return candidates
        selected = [indexed[position][1] for position in best_combo]
        if len(candidates) > max_candidates:
            selected.extend(candidates[max_candidates:])
        return selected

    def _subset_score(self, subset: list[dict[str, Any]], target: float, expected_count: int | None) -> float:
        subset_sum = sum(numeric(item.get("amount") or item.get("price")) for item in subset)
        target_penalty = 0.0
        if target:
            target_penalty = min(4.0, abs(subset_sum - target) / max(target, 1.0) * 8.0)
        count_penalty = 0.0
        if expected_count:
            count_penalty = abs(len(subset) - expected_count) * 1.5
        confidence_score = sum(float(item.get("confidence", 0.0) or 0.0) for item in subset) / max(len(subset), 1)
        semantic_score = sum(float(item.get("semanticProductScore", self._product_likeness_score(item.get("name", ""))) or 0.0) for item in subset) / max(len(subset), 1)
        noise_penalty = sum(1.0 - float(item.get("semanticProductScore", self._product_likeness_score(item.get("name", ""))) or 0.0) for item in subset) * 0.12
        return (confidence_score * 1.4) + (semantic_score * 1.8) - target_penalty - count_penalty - noise_penalty

    def _candidate_item_graph(self, candidates: list[dict[str, Any]]) -> dict[str, Any]:
        nodes = []
        edges = []
        for index, item in enumerate(candidates):
            semantic_score = self._product_likeness_score(item.get("name", ""))
            item["semanticProductScore"] = semantic_score
            node_id = f"item-candidate-{index + 1}"
            nodes.append({
                "id": node_id,
                "text": item.get("name", ""),
                "price": item.get("amount") or item.get("price"),
                "quantity": item.get("qty") or item.get("count") or "1",
                "lineIndex": item.get("lineIndex"),
                "confidence": item.get("confidence", 0),
                "semanticScore": semantic_score,
                "sectionState": "ITEMS",
                "bbox": item.get("bbox", {}),
                "confidenceTrace": item.get("confidenceTrace", {}),
            })
            if index:
                edges.append({"from": nodes[index - 1]["id"], "to": node_id, "type": "NEXT_ITEM_CANDIDATE"})
        return {
            "schemaVersion": "receipt-item-candidate-graph-v1",
            "nodes": nodes,
            "edges": edges,
        }

    def _product_likeness_score(self, name: Any) -> float:
        upper = compact(name).upper()
        if not upper:
            return 0.0
        if any(keyword in upper for keyword in ITEM_EXCLUSION_KEYWORDS):
            return 0.02
        if self.items._is_near_section_keyword(upper):
            return 0.04
        tokens = [token for token in re.split(r"\s+", upper) if token]
        alpha_tokens = [token for token in tokens if re.search(r"[A-Z]{3,}", token)]
        score = 0.18
        if len(alpha_tokens) >= 1:
            score += 0.22
        if len(alpha_tokens) >= 2:
            score += 0.22
        if any(len(token) >= 5 for token in alpha_tokens):
            score += 0.12
        vowel_tokens = [token for token in alpha_tokens if re.search(r"[AEIOUY]", token)]
        if vowel_tokens:
            score += 0.12
        if len(vowel_tokens) < max(1, len(alpha_tokens) // 2):
            score -= 0.2
        if re.fullmatch(r"[A-Z]{1,4}|[A-Z]{1,4}\d{3,}|[0-9A-Z]{8,}", upper):
            score -= 0.32
        return round(max(0.0, min(1.0, score)), 3)

    def _reconciliation_trace(
        self,
        candidates: list[dict[str, Any]],
        selected: list[dict[str, Any]],
        target: float,
        expected_count: int | None,
        reason: str,
    ) -> dict[str, Any]:
        selected_sum = sum(numeric(item.get("amount") or item.get("price")) for item in selected)
        candidate_sum = sum(numeric(item.get("amount") or item.get("price")) for item in candidates)
        return {
            "schemaVersion": "receipt-financial-reconciliation-v1",
            "reason": reason,
            "targetTotal": f"{target:.2f}" if target else "",
            "expectedItemCount": expected_count,
            "candidateCount": len(candidates),
            "selectedCount": len(selected),
            "candidateSum": f"{candidate_sum:.2f}" if candidate_sum else "0",
            "selectedSum": f"{selected_sum:.2f}" if selected_sum else "0",
            "delta": round(abs(selected_sum - target), 2) if target else None,
            "selectedLineIndexes": [item.get("lineIndex") for item in selected],
            "rejectedLineIndexes": [item.get("lineIndex") for item in candidates if item not in selected],
        }

    def _layout_graph(
        self,
        regions: list[ReceiptRegion],
        state_machine: dict[str, Any],
        item_result: dict[str, Any],
        totals: dict[str, Any],
        payment: dict[str, Any],
        visual_hierarchy: dict[str, Any],
        table_graph: dict[str, Any],
    ) -> dict[str, Any]:
        nodes: list[dict[str, Any]] = []
        edges: list[dict[str, Any]] = []
        saliency_by_index = {
            int(row.get("lineIndex")): row
            for row in (visual_hierarchy.get("lines") or [])
            if isinstance(row, dict) and isinstance(row.get("lineIndex"), int)
        }
        for index, region in enumerate(regions):
            region_id = f"region-{index + 1}-{region.kind}"
            region_saliency = [saliency_by_index.get(line.index, {}) for line in region.lines]
            visual_importance = sum(float(row.get("visualImportance", 0.0) or 0.0) for row in region_saliency) / max(len(region_saliency), 1)
            nodes.append({
                "id": region_id,
                "type": region.kind.upper(),
                "state": ReceiptDocumentStateMachine.STATE_BY_REGION.get(region.kind, "HEADER"),
                "confidence": round(region.confidence, 3),
                "visualImportance": round(visual_importance, 3),
                "saliencyTier": self.visual_hierarchy._tier(visual_importance),
                "bbox": region.to_dict()["bbox"],
                "lineIndexes": [line.index for line in region.lines],
                "text": region.text[:600],
                "reasons": region.reasons[:8],
            })
            if index > 0:
                edges.append({"from": nodes[index - 1]["id"], "to": region_id, "type": "NEXT_REGION"})
        for transition in state_machine.get("transitions", []) or []:
            edges.append({
                "from": transition.get("from", ""),
                "to": transition.get("to", ""),
                "type": "STATE_TRANSITION",
                "region": transition.get("region", ""),
                "confidence": transition.get("confidence", 0),
            })
        return {
            "schemaVersion": "receipt-layout-graph-v1",
            "nodes": nodes,
            "edges": edges,
            "constraints": {
                "productsOnlyInItems": True,
                "totalsStopItemParsing": True,
                "paymentRowsCannotBecomeProducts": True,
                "footerIgnored": True,
            },
            "diagnostics": {
                "duplicateClusters": item_result.get("duplicateClusters", []),
                "itemCandidateGraph": item_result.get("candidateGraph", {}),
                "financialReconciliation": item_result.get("financialReconciliation", {}),
                "tableGraph": table_graph,
                "totalsCandidates": totals.get("candidates", []),
                "taxRelationshipDiagnostics": totals.get("taxRelationshipDiagnostics", []),
                "paymentCandidates": payment.get("candidates", []),
            },
        }

    def _debug(
        self,
        regions: list[ReceiptRegion],
        item_result: dict[str, Any],
        totals: dict[str, Any],
        payment: dict[str, Any],
        validation: dict[str, Any],
        table_graph: dict[str, Any],
    ) -> dict[str, Any]:
        return {
            "sectionBoundaryVisualization": [
                {
                    "kind": region.kind,
                    "start": region.start,
                    "end": region.end,
                    "bbox": region.to_dict()["bbox"],
                    "lineCount": len(region.lines),
                }
                for region in regions
            ],
            "regionOverlays": [
                {
                    "kind": region.kind,
                    "confidence": round(region.confidence, 3),
                    "bbox": region.to_dict()["bbox"],
                    "label": f"{region.kind.upper()} {region.start}-{region.end}",
                    "lineIndexes": [line.index for line in region.lines],
                }
                for region in regions
            ],
            "parserStateVisualization": [
                {
                    "kind": region.kind,
                    "state": ReceiptDocumentStateMachine.STATE_BY_REGION.get(region.kind, "HEADER"),
                    "start": region.start,
                    "end": region.end,
                    "activeParser": ReceiptDocumentStateMachine.PARSER_BY_STATE.get(
                        ReceiptDocumentStateMachine.STATE_BY_REGION.get(region.kind, "HEADER"),
                        "header",
                    ),
                    "confidence": round(region.confidence, 3),
                }
                for region in regions
            ],
            "itemBoundaryLock": item_result.get("boundary", {}),
            "rejectedItemRows": item_result.get("rejected", []),
            "totalsRejectedRows": totals.get("rejected", []),
            "confidenceTraces": [item.get("confidenceTrace", {}) for item in item_result.get("items", [])],
            "arithmeticValidationLogs": validation.get("arithmeticChecks", []),
            "taxRelationshipDiagnostics": totals.get("taxRelationshipDiagnostics", []),
            "rowReconstructionVisualization": table_graph.get("rowReconstructionVisualization", []),
            "tableColumnOverlays": table_graph.get("columnOverlays", []),
            "paymentCandidateLines": payment.get("candidates", []),
            "duplicateSuppressionDiagnostics": item_result.get("duplicateClusters", []),
            "candidateItemGraphVisualization": item_result.get("candidateGraph", {}),
            "financialReconciliationTrace": item_result.get("financialReconciliation", {}),
            "itemCardinalityDiagnostics": item_result.get("cardinality", {}),
        }
