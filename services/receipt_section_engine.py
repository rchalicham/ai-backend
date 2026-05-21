from __future__ import annotations

import logging
import re
from dataclasses import dataclass, field
from typing import Any

try:
    from rapidfuzz import fuzz
except Exception:  # pragma: no cover - dependency is installed in production requirements.
    fuzz = None


logger = logging.getLogger(__name__)

TOTAL_KEYWORDS = (
    "SUBTOTAL", "SUB TOTAL", "TAX", "TOTAL", "BALANCE", "CHANGE", "TIP", "CHARGE", "AMOUNT",
)
PAYMENT_KEYWORDS = (
    "VISA", "MASTERCARD", "MASTER CARD", "AMEX", "AMERICAN EXPRESS", "DISCOVER",
    "CREDIT", "DEBIT", "CARD", "AUTH", "APPROVAL", "APPROVED", "AID", "ENTRY", "CHIP",
    "LAST FOUR", "LAST 4", "CARD LAST", "ENDING IN",
)
FOOTER_KEYWORDS = (
    "THANK", "SURVEY", "FEEDBACK", "RETURN POLICY", "COME AGAIN", "VISIT", "WWW.",
)
ITEM_EXCLUSION_KEYWORDS = TOTAL_KEYWORDS + PAYMENT_KEYWORDS + FOOTER_KEYWORDS + (
    "TERMINAL", "TRANS", "TRANSACTION", "CASHIER", "REGISTER", "RECEIPT",
    "BARCODE", "COUPON", "SAVINGS", "ITEM COUNT", "SOLD ITEM",
)
SECTION_LOCK_KINDS = {"totals", "payment", "footer"}
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
    match = re.search(r"-?\d{1,7}\b", text)
    return match.group(0) if match else ""


def numeric(value: Any) -> float:
    parsed = amount(value)
    try:
        return float(parsed) if parsed else 0.0
    except ValueError:
        return 0.0


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
        if any(keyword in upper for keyword in PAYMENT_KEYWORDS):
            return "payment", ["payment_keyword"], 0.9
        if index <= 4 and re.search(r"[A-Z]{3,}", upper) and amount_count == 0:
            return "header", ["top_text_no_amount"], 0.8
        if any(keyword in upper for keyword in TOTAL_KEYWORDS):
            return "totals", ["total_keyword"], 0.9
        if any(keyword in upper for keyword in FOOTER_KEYWORDS):
            return "footer", ["footer_keyword"], 0.82
        if re.search(r"[A-Z]{3,}", upper) and amount_count and right_aligned_amount:
            return "items", ["product_text_with_right_amount"], 0.78
        if re.search(r"[A-Z]{3,}", upper) and amount_count:
            return "items", ["product_text_with_amount"], 0.66
        return "unknown", reasons or ["low_signal"], 0.45

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
                candidates.append({"label": label, "amount": value, "line": line.text, "confidence": self._confidence(label, line)})
        for label in ("subtotal", "tax", "tip", "charge", "total", "change"):
            matches = [candidate for candidate in candidates if candidate["label"] == label]
            if matches:
                fields[label] = max(matches, key=lambda item: item["confidence"])["amount"]
        return {
            "fields": fields,
            "candidates": candidates,
            "rejected": rejected[:80],
            "confidence": round(sum(item["confidence"] for item in candidates) / max(len(candidates), 1), 3) if candidates else 0.0,
        }

    def _label(self, text: str) -> str:
        upper = text.upper().replace("SUB TOTAL", "SUBTOTAL")
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
        if "TOTAL" in upper:
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
        items = [{**item, "id": index + 1} for index, item in enumerate(items)]
        return {
            "items": items,
            "rejected": rejected[:120],
            "boundary": lock,
        }

    def _parse_line(self, line: ReceiptLineGeometry, max_right: float) -> tuple[dict[str, Any] | None, list[str], float]:
        reasons: list[str] = []
        upper = line.text.upper()
        if any(keyword in upper for keyword in ITEM_EXCLUSION_KEYWORDS):
            reasons.append("section_keyword_in_item_candidate")
        if self._is_near_section_keyword(upper):
            reasons.append("ocr_mutation_of_section_keyword")
        if self._looks_like_survey_or_barcode(upper):
            reasons.append("survey_or_barcode_numeric_row")
        match = re.search(r"(?P<name>.+?)\s+(?P<amount>-?\d{1,7}(?:[.,]\d{2}))\s*[A-Z]?$", line.text)
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
        }, sorted(set(score_reasons)), score

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
        if not re.search(r"\d{1,7}(?:[.,]\d{2})\s*[A-Z]?\s*$", line.text):
            return False
        if line.x == 0:
            return True
        return max_right <= 0 or line.right >= max_right * 0.68

    def _looks_like_monetary_row(self, text: str) -> bool:
        return bool(re.search(r"\d{1,7}(?:[.,]\d{2})\s*[A-Z]?\s*$", text))

    def _looks_like_survey_or_barcode(self, upper: str) -> bool:
        if any(token in upper for token in ("SURVEY", "BARCODE", "COUPON", "REWARD", "RECEIPT ID")):
            return True
        digits = re.sub(r"\D", "", upper)
        return len(digits) >= 8 and not re.search(r"\d{1,7}[.,]\d{2}", upper)

    def _is_near_section_keyword(self, upper: str) -> bool:
        token = re.sub(r"[^A-Z]", "", upper.split()[0] if upper.split() else "")
        if len(token) < 4:
            return False
        if token in {"GATT", "HARGE", "T0TAL", "TOTAI", "TQTAL", "SUBT0TAL", "CHARGF", "CHAR6E"}:
            return True
        targets = ("TOTAL", "SUBTOTAL", "CHARGE", "PAYMENT", "CHANGE", "TAX", "VISA", "CARD", "AUTH")
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


class ReceiptSectionConfidenceEngine:
    def score(self, regions: list[ReceiptRegion], totals: dict[str, Any], payment: dict[str, Any], items: list[dict[str, Any]]) -> dict[str, float]:
        region_score = min(1.0, len([region for region in regions if region.kind != "unknown"]) / max(len(regions), 1)) if regions else 0.0
        totals_score = totals.get("confidence", 0.0)
        payment_score = payment.get("confidence", 0.0)
        items_score = min(1.0, len(items) / 4) if items else 0.0
        overall = region_score * 0.28 + totals_score * 0.32 + payment_score * 0.18 + items_score * 0.22
        return {
            "overall": round(overall, 3),
            "regions": round(region_score, 3),
            "totals": round(totals_score, 3),
            "payment": round(payment_score, 3),
            "items": round(items_score, 3),
        }


class ReceiptSectionValidationEngine:
    def validate(self, totals: dict[str, Any], payment: dict[str, Any], items: list[dict[str, Any]]) -> dict[str, Any]:
        fields = totals.get("fields", {})
        subtotal = numeric(fields.get("subtotal"))
        tax = numeric(fields.get("tax"))
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
        return {
            "itemSum": f"{item_sum:.2f}" if item_sum else "0",
            "warnings": warnings,
            "valid": not warnings,
        }


class ReceiptSectionExtractionEngine:
    def __init__(self) -> None:
        self.geometry = ReceiptGeometryBuilder()
        self.classifier = ReceiptRegionClassifier()
        self.totals = TotalsParser()
        self.payment = PaymentParser()
        self.items = SectionAwareItemParser()
        self.confidence = ReceiptSectionConfidenceEngine()
        self.validation = ReceiptSectionValidationEngine()

    def extract(
        self,
        raw_text: str = "",
        lines: list[str] | None = None,
        ocr_blocks: list[dict[str, Any]] | None = None,
    ) -> dict[str, Any]:
        geometry = self.geometry.from_inputs(raw_text=raw_text, lines=lines, boxes=ocr_blocks)
        regions = self.classifier.classify(geometry)
        totals = self.totals.parse(regions)
        payment = self.payment.parse(regions)
        item_result = self.items.parse_with_diagnostics(regions)
        items = item_result["items"]
        confidence = self.confidence.score(regions, totals, payment, items)
        validation = self.validation.validate(totals, payment, items)
        debug = self._debug(regions, item_result, totals, payment)
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
            "regions": [region.to_dict() for region in regions],
            "totals": totals,
            "payment": payment,
            "items": items,
            "confidence": confidence,
            "validation": validation,
            "debug": debug,
        }

    def _debug(
        self,
        regions: list[ReceiptRegion],
        item_result: dict[str, Any],
        totals: dict[str, Any],
        payment: dict[str, Any],
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
            "itemBoundaryLock": item_result.get("boundary", {}),
            "rejectedItemRows": item_result.get("rejected", []),
            "totalsRejectedRows": totals.get("rejected", []),
            "confidenceTraces": [item.get("confidenceTrace", {}) for item in item_result.get("items", [])],
            "paymentCandidateLines": payment.get("candidates", []),
        }
