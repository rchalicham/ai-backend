from __future__ import annotations

import logging
import re
from dataclasses import dataclass, field
from typing import Any

from services.receipt_visual_hierarchy import LEGAL_DISCLAIMER_TERMS, ReceiptVisualHierarchyEngine


logger = logging.getLogger(__name__)

CARD_BRANDS = {
    "VISA": "VISA",
    "MASTERCARD": "MASTERCARD",
    "MASTER CARD": "MASTERCARD",
    "AMEX": "AMEX",
    "AMERICAN EXPRESS": "AMEX",
    "DISCOVER": "DISCOVER",
}
STREET_TERMS = (
    "ROAD", "RD", "STREET", "ST", "AVENUE", "AVE", "BOULEVARD", "BLVD", "DRIVE", "DR",
    "LANE", "LN", "HIGHWAY", "HWY", "PARKWAY", "PKWY", "WAY", "COURT", "CT", "NORTH",
    "SOUTH", "EAST", "WEST", "CIRCLE", "CIR", "PLACE", "PL", "TERRACE", "TER", "TRAIL",
    "TRL", "PLAZA", "PLZ", "SUITE", "STE", "UNIT", "BUILDING", "BLDG",
)
HEADER_SKIP_TERMS = (
    "REG", "TRN", "CSHR", "STR", "STORE", "RECEIPT", "TOTAL", "SUBTOTAL",
    "TAX", "VISA", "MASTERCARD", "AUTH", "APPROVAL", "CARD", "SURVEY",
    "FEEDBACK", "RETURN POLICY", "NO PURCHASE", "NO PURCHASE NECESSARY",
    "VOID WHERE PROHIBITED", "PROHIBITED", "SWEEPSTAKES", "SWEEPST", "OFFICIAL RULES", "RULES",
    "QUANTITY", "PRICE",
)
US_STATE_CODES = {
    "AL", "AK", "AZ", "AR", "CA", "CO", "CT", "DE", "FL", "GA", "HI", "IA", "ID", "IL",
    "IN", "KS", "KY", "LA", "MA", "MD", "ME", "MI", "MN", "MO", "MS", "MT", "NC", "ND",
    "NE", "NH", "NJ", "NM", "NV", "NY", "OH", "OK", "OR", "PA", "RI", "SC", "SD", "TN",
    "TX", "UT", "VA", "VT", "WA", "WI", "WV", "WY", "DC",
}


@dataclass
class EntityLine:
    text: str
    index: int
    x: float = 0.0
    y: float = 0.0
    width: float = 0.0
    height: float = 14.0
    confidence: float = 1.0
    page: int = 1


@dataclass
class EntityCandidate:
    value: str
    confidence: float
    source: str
    line_indexes: list[int] = field(default_factory=list)
    debug: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "value": self.value,
            "confidence": round(self.confidence, 3),
            "source": self.source,
            "lineIndexes": self.line_indexes,
            "debug": self.debug,
        }


def compact(value: Any) -> str:
    return re.sub(r"\s+", " ", str(value or "")).strip()


class EntityGeometryBuilder:
    def from_inputs(
        self,
        raw_text: str = "",
        lines: list[str] | None = None,
        boxes: list[dict[str, Any]] | None = None,
    ) -> list[EntityLine]:
        box_lines = self._from_boxes(boxes or [])
        if box_lines:
            return box_lines
        source_lines = [compact(line) for line in (lines or []) if compact(line)]
        if not source_lines and raw_text:
            source_lines = [compact(line) for line in raw_text.splitlines() if compact(line)]
        return [
            EntityLine(text=line, index=index, y=float(index * 18), width=max(80.0, len(line) * 7.0))
            for index, line in enumerate(source_lines)
        ]

    def _from_boxes(self, boxes: list[dict[str, Any]]) -> list[EntityLine]:
        parsed = [self._box(box) for box in boxes if isinstance(box, dict) and compact(box.get("text") or box.get("value"))]
        if not parsed:
            return []
        parsed.sort(key=lambda line: (line.page, line.y, line.x))
        heights = sorted([line.height for line in parsed if line.height > 0])
        tolerance = max(8.0, (heights[len(heights) // 2] if heights else 14) * 0.75)
        rows: list[list[EntityLine]] = []
        for line in parsed:
            center = line.y + line.height / 2
            target = next((row for row in rows if abs(self._row_center(row) - center) <= tolerance), None)
            if target is None:
                rows.append([line])
            else:
                target.append(line)
        output: list[EntityLine] = []
        for index, row in enumerate(rows):
            ordered = sorted(row, key=lambda item: item.x)
            left = min(item.x for item in ordered)
            top = min(item.y for item in ordered)
            right = max(item.x + item.width for item in ordered)
            bottom = max(item.y + item.height for item in ordered)
            output.append(EntityLine(
                text=compact(" ".join(item.text for item in ordered)),
                index=index,
                x=left,
                y=top,
                width=max(0.0, right - left),
                height=max(1.0, bottom - top),
                confidence=sum(item.confidence for item in ordered) / max(len(ordered), 1),
                page=ordered[0].page,
            ))
        return sorted(output, key=lambda line: (line.page, line.y, line.x))

    def _box(self, payload: dict[str, Any]) -> EntityLine:
        bbox = payload.get("bbox") or payload.get("box") or {}
        if isinstance(bbox, list) and len(bbox) >= 4:
            xs = [float(point[0]) for point in bbox if isinstance(point, (list, tuple)) and len(point) >= 2]
            ys = [float(point[1]) for point in bbox if isinstance(point, (list, tuple)) and len(point) >= 2]
            bbox = {
                "x": min(xs) if xs else 0,
                "y": min(ys) if ys else 0,
                "width": (max(xs) - min(xs)) if len(xs) >= 2 else 0,
                "height": (max(ys) - min(ys)) if len(ys) >= 2 else 14,
            }
        return EntityLine(
            text=compact(payload.get("text") or payload.get("value")),
            index=0,
            x=float(payload.get("x", bbox.get("x", bbox.get("left", 0))) or 0),
            y=float(payload.get("y", bbox.get("y", bbox.get("top", 0))) or 0),
            width=float(payload.get("width", bbox.get("width", bbox.get("w", 0))) or 0),
            height=float(payload.get("height", bbox.get("height", bbox.get("h", 14))) or 14),
            confidence=float(payload.get("confidence", payload.get("conf", 1.0)) or 0),
            page=int(payload.get("page", payload.get("pageNumber", 1)) or 1),
        )

    def _row_center(self, row: list[EntityLine]) -> float:
        return sum(line.y + line.height / 2 for line in row) / max(len(row), 1)


class HeaderEntityParser:
    def __init__(self) -> None:
        self.visual_hierarchy = ReceiptVisualHierarchyEngine()

    def parse(self, lines: list[EntityLine]) -> dict[str, Any]:
        visual_hierarchy = self.visual_hierarchy.analyze(lines)
        merchant = self._merchant(lines, visual_hierarchy)
        address = self._address(lines)
        phone = self._phone(lines)
        date = self._date(lines)
        return {
            "merchant": merchant.to_dict() if merchant else {},
            "address": address.to_dict() if address else {},
            "phone": phone.to_dict() if phone else {},
            "date": date.to_dict() if date else {},
            "visualHierarchy": visual_hierarchy,
        }

    def _merchant(self, lines: list[EntityLine], visual_hierarchy: dict[str, Any]) -> EntityCandidate | None:
        header = lines[:8]
        saliency_by_index = {
            int(row.get("lineIndex")): row
            for row in (visual_hierarchy.get("lines") or [])
            if isinstance(row, dict) and isinstance(row.get("lineIndex"), int)
        }
        candidates: list[EntityCandidate] = []
        for index, line in enumerate(header[:5]):
            upper = line.text.upper()
            if (
                re.search(r"[A-Za-z]{3,}", line.text)
                and not re.search(r"\d{4,}", line.text)
                and not re.search(r"\d{1,7}(?:[.,]\d{2})", line.text)
                and not any(term in upper for term in HEADER_SKIP_TERMS)
                and not self._followed_by_item_price(header, index)
            ):
                saliency = saliency_by_index.get(line.index, {})
                visual_importance = float(saliency.get("visualImportance", 0.45) or 0.0)
                zone = saliency.get("zone", "")
                semantic_bonus = 0.14 if re.search(r"\b(?:WWW\.)?[A-Z0-9][A-Z0-9-]{2,35}\.(?:COM|NET|ORG)\b", upper) else 0.0
                zone_bonus = 0.1 if zone in {"merchant_zone", "header_zone"} else 0.0
                confidence = min(0.96, 0.42 + (visual_importance * 0.36) + semantic_bonus + zone_bonus)
                if visual_importance < 0.34 and any(term in upper for term in LEGAL_DISCLAIMER_TERMS):
                    confidence = min(confidence, 0.28)
                candidates.append(EntityCandidate(
                    self._title(line.text),
                    confidence,
                    "visual_hierarchy.header_candidate",
                    [line.index],
                    {
                        "line": line.text,
                        "visualImportance": visual_importance,
                        "zone": zone,
                        "saliencyTier": saliency.get("saliencyTier", ""),
                    },
                ))
        candidates = [candidate for candidate in candidates if candidate.confidence >= 0.62]
        return max(candidates, key=lambda candidate: candidate.confidence) if candidates else None

    def _followed_by_item_price(self, lines: list[EntityLine], index: int) -> bool:
        for candidate in lines[index + 1: min(len(lines), index + 4)]:
            text = compact(candidate.text)
            if re.fullmatch(r"\d{1,3}", text):
                continue
            if re.search(r"-?\$?\d{1,7}(?:[.,]\d{2})\s*$", text):
                return True
            if re.search(r"[A-Za-z]{3,}", text):
                return False
        return False

    def _address(self, lines: list[EntityLine]) -> EntityCandidate | None:
        candidates: list[EntityCandidate] = []
        for index, line in enumerate(lines[:16]):
            street, street_score, street_reasons = self._street_candidate(line.text)
            if not street:
                continue
            city_line = self._nearby_city_state(lines, index)
            city_state = self._city_state(city_line.text) if city_line else ""
            value = street if not city_state else f"{street}, {city_state}"
            confidence = street_score + (0.2 if city_state else 0.0)
            if index <= 8:
                confidence += 0.04
            candidates.append(EntityCandidate(
                value=value,
                confidence=min(0.98, confidence),
                source="header.address_window",
                line_indexes=[line.index, *([city_line.index] if city_line else [])],
                debug={"streetLine": line.text, "cityStateLine": city_line.text if city_line else "", "reasons": street_reasons},
            ))
        return max(candidates, key=lambda candidate: candidate.confidence) if candidates else None

    def _street(self, text: str) -> str:
        return self._street_candidate(text)[0]

    def _street_candidate(self, text: str) -> tuple[str, float, list[str]]:
        upper = compact(text).upper()
        reasons: list[str] = []
        if re.search(r"[{}\[\]|]", upper):
            return "", 0.0, ["ocr_corrupt_address_punctuation"]
        if not re.search(r"\b\d{2,6}\b", upper):
            return "", 0.0, ["missing_street_number"]
        if self._looks_like_transaction_line(upper):
            return "", 0.0, ["transaction_or_payment_line"]
        has_suffix = any(re.search(rf"\b{re.escape(term)}\.?\b", upper) for term in STREET_TERMS)
        has_direction = bool(re.search(r"\b(?:N|S|E|W|NE|NW|SE|SW|NORTH|SOUTH|EAST|WEST)\b", upper))
        has_unit = bool(re.search(r"\b(?:SUITE|STE|UNIT|APT|#)\s*[A-Z0-9-]+\b", upper))
        if not has_suffix and not has_direction and not has_unit:
            return "", 0.0, ["missing_street_suffix_or_direction"]
        score = 0.5
        if has_suffix:
            score += 0.18
            reasons.append("street_suffix")
        if has_direction:
            score += 0.08
            reasons.append("directional")
        if has_unit:
            score += 0.06
            reasons.append("unit")
        if re.search(r"\b\d{5}(?:-\d{4})?\b", upper):
            score += 0.06
            reasons.append("zip_on_street_line")
        cleaned = self._clean_street_line(upper)
        return cleaned, min(0.82, score), reasons

    def _clean_street_line(self, upper: str) -> str:
        text = re.sub(r"^[^A-Z0-9]+|[^A-Z0-9# .'-]+$", "", upper)
        text = re.sub(r"\b(?:STORE|STR)\s*#?\s*\d+\b", "", text)
        text = re.sub(r"\s+", " ", text).strip(" ,")
        return text

    def _nearby_city_state(self, lines: list[EntityLine], street_index: int) -> EntityLine | None:
        for line in lines[street_index + 1: street_index + 5]:
            if self._city_state(line.text):
                return line
        return None

    def _city_state(self, text: str) -> str:
        upper = compact(text).upper().strip(" ,")
        if self._looks_like_transaction_line(upper):
            return ""
        if re.search(r"^\d+\s+", upper) or re.search(r"\d{1,4}[.,]\d{2}\w?$", upper):
            return ""
        match = re.search(r"\b(?P<city>[A-Z][A-Z .'-]{2,}?),?\s+(?P<state>[A-Z]{2})(?:\s+(?P<zip>\d{5}(?:-\d{4})?))?\b", upper)
        if not match:
            return ""
        state = match.group("state")
        if state not in US_STATE_CODES:
            return ""
        city = compact(match.group("city")).strip(" ,")
        if len(city.split()) > 3 or re.search(r"\b(?:SPRK|SPRNG|ITEM|SKU|REG|TRN|CSHR)\b", city):
            return ""
        if any(term in city for term in ("AUTH", "VISA", "TOTAL", "TAX", "REG", "TRN", "CSHR")):
            return ""
        zip_code = match.group("zip") or ""
        return f"{city}, {state}{f' {zip_code}' if zip_code else ''}"

    def _looks_like_transaction_line(self, upper: str) -> bool:
        if any(term in upper for term in ("AUTH", "APPROVAL", "VISA", "MASTERCARD", "AMEX", "DISCOVER", "TOTAL", "SUBTOTAL", "TAX")):
            return True
        if re.search(r"\b(?:REG|TRN|CSHR|TERMINAL|AID|REF)\s*#?\s*\d+", upper):
            return True
        return False

    def _phone(self, lines: list[EntityLine]) -> EntityCandidate | None:
        for line in lines[:20]:
            match = re.search(r"(?:\+?1[-.\s]?)?(?:\(?\d{3}\)?[-.\s]?)\d{3}[-.\s]?\d{4}", line.text)
            if match:
                return EntityCandidate(match.group(0), 0.9, "header.phone_regex", [line.index], {"line": line.text})
        return None

    def _date(self, lines: list[EntityLine]) -> EntityCandidate | None:
        patterns = (
            r"\b(\d{4}[-/]\d{1,2}[-/]\d{1,2})\b",
            r"\b(\d{1,2}[-/]\d{1,2}[-/]\d{2,4})\b",
            r"\b(\d{1,2}[- ](?:JAN|FEB|MAR|APR|MAY|JUN|JUL|AUG|SEP|SEPT|OCT|NOV|DEC)[A-Z]*\.?[- ]\d{2,4})\b",
            r"\b((?:JAN|FEB|MAR|APR|MAY|JUN|JUL|AUG|SEP|SEPT|OCT|NOV|DEC)[A-Z]*\.?\s+\d{1,2},?\s+\d{2,4})\b",
        )
        for line in lines[:24]:
            upper = line.text.upper()
            if any(token in upper for token in ("RETURN POLICY", "POLICY", "THRU", "EXPIRES", "EXPIRATION", "EXP. DATE", "EXP DATE", "VALID UNTIL", "COUPON", "REWARD")):
                continue
            if self._looks_like_transaction_line(upper) and not re.search(r"\bDATE\b", upper):
                continue
            for pattern in patterns:
                match = re.search(pattern, line.text, flags=re.IGNORECASE)
                if match and self._valid_date_candidate(match.group(1)):
                    return EntityCandidate(self._normalize_date_value(match.group(1)), 0.86, "header.date_regex", [line.index], {"line": line.text})
        return None

    def _valid_date_candidate(self, value: str) -> bool:
        text = compact(value).upper().strip()
        numeric_match = re.fullmatch(r"(\d{1,4})[-/](\d{1,2})[-/](\d{1,4})", text)
        if numeric_match:
            first, second, third = [int(part) for part in numeric_match.groups()]
            if len(numeric_match.group(1)) == 4:
                year, month, day = first, second, third
            else:
                month, day, year = first, second, third
                if year < 100:
                    year += 2000
            return 1 <= month <= 12 and 1 <= day <= 31 and 1990 <= year <= 2100
        month_match = re.search(
            r"\b(?:JAN|FEB|MAR|APR|MAY|JUN|JUL|AUG|SEP|SEPT|OCT|NOV|DEC)[A-Z]*\.?\s+(\d{1,2}),?\s+(\d{2,4})\b",
            text,
        )
        if month_match:
            day = int(month_match.group(1))
            year = int(month_match.group(2))
            if year < 100:
                year += 2000
            return 1 <= day <= 31 and 1990 <= year <= 2100
        day_month_match = re.search(
            r"\b(\d{1,2})[- ](?:JAN|FEB|MAR|APR|MAY|JUN|JUL|AUG|SEP|SEPT|OCT|NOV|DEC)[A-Z]*\.?[- ](\d{2,4})\b",
            text,
        )
        if day_month_match:
            day = int(day_month_match.group(1))
            year = int(day_month_match.group(2))
            if year < 100:
                year += 2000
            return 1 <= day <= 31 and 1990 <= year <= 2100
        return False

    def _normalize_date_value(self, value: str) -> str:
        text = compact(value).upper().strip()
        numeric_match = re.fullmatch(r"(\d{1,4})[-/](\d{1,2})[-/](\d{1,4})", text)
        if numeric_match:
            first, second, third = numeric_match.groups()
            if len(first) == 4:
                year, month, day = first, second, third
            else:
                month, day, year = first, second, third
                if len(year) == 2:
                    year = f"20{year}"
            return f"{int(month):02d}/{int(day):02d}/{year}"
        day_month_match = re.search(
            r"\b(\d{1,2})[- ](JAN|FEB|MAR|APR|MAY|JUN|JUL|AUG|SEP|SEPT|OCT|NOV|DEC)[A-Z]*\.?[- ](\d{2,4})\b",
            text,
        )
        if day_month_match:
            month_lookup = {
                "JAN": 1, "FEB": 2, "MAR": 3, "APR": 4, "MAY": 5, "JUN": 6,
                "JUL": 7, "AUG": 8, "SEP": 9, "SEPT": 9, "OCT": 10, "NOV": 11, "DEC": 12,
            }
            day, month_text, year = day_month_match.groups()
            if len(year) == 2:
                year = f"20{year}"
            return f"{month_lookup.get(month_text[:3], 0):02d}/{int(day):02d}/{year}"
        return value

    def _title(self, text: str) -> str:
        words = []
        for word in compact(text).split():
            parts = [part if part.isupper() else part.title() for part in word.split("/")]
            words.append("/".join(parts))
        return " ".join(words)


class PaymentEntityParser:
    def parse(self, lines: list[EntityLine]) -> dict[str, Any]:
        payment_windows = self._payment_windows(lines)
        card_type = self._card_type(payment_windows)
        last_four = self._last_four(payment_windows)
        approval = self._approval(payment_windows)
        method = self._method(payment_windows, card_type)
        return {
            "paymentMethod": method.to_dict() if method else {},
            "cardType": card_type.to_dict() if card_type else {},
            "lastFour": last_four.to_dict() if last_four else {},
            "approvalCode": approval.to_dict() if approval else {},
            "debug": {
                "paymentWindows": [
                    {"anchorIndex": anchor.index, "lines": [line.text for line in window]}
                    for anchor, window in payment_windows
                ],
            },
        }

    def _payment_windows(self, lines: list[EntityLine]) -> list[tuple[EntityLine, list[EntityLine]]]:
        windows: list[tuple[EntityLine, list[EntityLine]]] = []
        for index, line in enumerate(lines):
            upper = line.text.upper()
            if (
                any(token in upper for token in (*CARD_BRANDS.keys(), "CREDIT", "DEBIT", "CARD", "AUTH", "APPROVAL"))
                or re.search(r"\bLAST\s*(?:FOUR|4)\b|\bCARD\s*LAST\b|\bENDING\s+IN\b", upper)
                or re.search(r"[*X]{4,}\s*\d{3,4}", upper)
            ):
                windows.append((line, lines[max(0, index - 2): min(len(lines), index + 5)]))
        return windows

    def _card_type(self, windows: list[tuple[EntityLine, list[EntityLine]]]) -> EntityCandidate | None:
        for anchor, window in windows:
            for line in window:
                upper = line.text.upper()
                for token, brand in CARD_BRANDS.items():
                    if token in upper:
                        return EntityCandidate(brand, 0.94 if line.index == anchor.index else 0.86, "payment.card_brand_window", [line.index], {"line": line.text})
        return None

    def _last_four(self, windows: list[tuple[EntityLine, list[EntityLine]]]) -> EntityCandidate | None:
        patterns = [
            ("masked_pan", r"(?:[*X]{4,}|ENDING\s+IN|CARD\s*#?)\D{0,8}(\d{4})\b"),
            ("last_four_label", r"\bLAST\s*(?:FOUR|4)\D{0,12}(\d{4})\b"),
            ("card_brand", r"\b(?:VISA|MASTERCARD|MASTER CARD|AMEX|DISCOVER)\D{0,20}(\d{4})\b"),
            ("generic_payment_line", r"\b(\d{4})\b"),
        ]
        for anchor, window in windows:
            for line in window:
                upper = line.text.upper()
                if self._looks_like_approval_line(upper):
                    continue
                fuzzy_last4 = self._fuzzy_masked_last4(line.text)
                if fuzzy_last4 and self._near_payment_context(window, line):
                    return EntityCandidate(fuzzy_last4, 0.86, "payment.fuzzy_masked_last4", [line.index], {"line": line.text, "anchor": anchor.text})
                for pattern_name, pattern in patterns:
                    if pattern_name == "generic_payment_line" and not self._line_has_payment_context(upper):
                        continue
                    match = re.search(pattern, line.text, flags=re.IGNORECASE)
                    if match and self._near_payment_context(window, line):
                        return EntityCandidate(match.group(1), 0.93, "payment.last4_context_window", [line.index], {"line": line.text, "anchor": anchor.text})
            label = next((line for line in window if re.search(r"\bLAST\s*(?:FOUR|4)\b|\bCARD\s*LAST\b|\bENDING\s+IN\b", line.text, flags=re.IGNORECASE)), None)
            if label and self._near_payment_context(window, label):
                for line in window:
                    if self._looks_like_approval_line(line.text.upper()) or re.search(r"\bNOT\s+SET\b", line.text, flags=re.IGNORECASE):
                        continue
                    match = re.search(r"\b(\d{4})\b", line.text)
                    if match:
                        return EntityCandidate(match.group(1), 0.91, "payment.last4_label_window", [line.index], {"line": line.text, "anchor": anchor.text, "label": label.text})
        return None

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

    def _approval(self, windows: list[tuple[EntityLine, list[EntityLine]]]) -> EntityCandidate | None:
        patterns = [
            r"\bAUTH(?:ORIZATION)?\s*(?:CODE|#|NO|NUM)?[\s#:.-]*([A-Z0-9]{4,12})\b",
            r"\bAPPROVAL\s*(?:CODE|#|NO|NUM)?[\s#:.-]*([A-Z0-9]{4,12})\b",
            r"\bAPPR(?:OVED)?[\s#:.-]+([A-Z0-9]{4,12})\b",
        ]
        for anchor, window in windows:
            for line in window:
                for pattern in patterns:
                    match = re.search(pattern, line.text, flags=re.IGNORECASE)
                    if match:
                        return EntityCandidate(match.group(1), 0.9, "payment.approval_regex", [line.index], {"line": line.text, "anchor": anchor.text})
        return None

    def _method(self, windows: list[tuple[EntityLine, list[EntityLine]]], card_type: EntityCandidate | None) -> EntityCandidate | None:
        for anchor, window in windows:
            text = " ".join(line.text.upper() for line in window)
            if "CREDIT" in text:
                return EntityCandidate("credit", 0.9, "payment.method_keyword", [anchor.index], {"anchor": anchor.text})
            if "DEBIT" in text:
                return EntityCandidate("debit", 0.9, "payment.method_keyword", [anchor.index], {"anchor": anchor.text})
            if "CASH" in text:
                return EntityCandidate("cash", 0.86, "payment.method_keyword", [anchor.index], {"anchor": anchor.text})
        if card_type:
            return EntityCandidate("card", 0.78, "payment.method_card_brand", card_type.line_indexes, {})
        return None

    def _looks_like_approval_line(self, upper: str) -> bool:
        return any(token in upper for token in ("AUTH", "APPROVAL", "APPR"))

    def _near_payment_context(self, window: list[EntityLine], line: EntityLine) -> bool:
        text = " ".join(candidate.text.upper() for candidate in window)
        return bool(
            any(token in text for token in (*CARD_BRANDS.keys(), "CREDIT", "DEBIT", "CARD"))
            or re.search(r"\bLAST\s*(?:FOUR|4)\b|\bCARD\s*LAST\b|\bENDING\s+IN\b", text)
            or re.search(r"[*X]{4,}", line.text)
        )

    def _line_has_payment_context(self, upper: str) -> bool:
        return bool(
            any(token in upper for token in (*CARD_BRANDS.keys(), "CREDIT", "DEBIT", "CARD", "ACCT", "ACCOUNT"))
            or re.search(r"\bLAST\s*(?:FOUR|4)\b|\bCARD\s*LAST\b|\bENDING\s+IN\b", upper)
            or re.search(r"[*X]{4,}", upper)
        )


class ReceiptEntityConfidenceEngine:
    def score(self, header: dict[str, Any], payment: dict[str, Any]) -> dict[str, float]:
        merchant = float(header.get("merchant", {}).get("confidence") or 0)
        address = float(header.get("address", {}).get("confidence") or 0)
        phone = float(header.get("phone", {}).get("confidence") or 0)
        date = float(header.get("date", {}).get("confidence") or 0)
        card = float(payment.get("cardType", {}).get("confidence") or 0)
        last4 = float(payment.get("lastFour", {}).get("confidence") or 0)
        approval = float(payment.get("approvalCode", {}).get("confidence") or 0)
        overall = merchant * 0.16 + address * 0.19 + phone * 0.07 + date * 0.08 + card * 0.18 + last4 * 0.22 + approval * 0.1
        return {
            "overall": round(overall, 3),
            "merchant": round(merchant, 3),
            "address": round(address, 3),
            "phone": round(phone, 3),
            "date": round(date, 3),
            "payment": round(max(card, last4, approval), 3),
            "cardType": round(card, 3),
            "lastFour": round(last4, 3),
            "approvalCode": round(approval, 3),
        }


class ReceiptEntityExtractionEngine:
    def __init__(self) -> None:
        self.geometry = EntityGeometryBuilder()
        self.header = HeaderEntityParser()
        self.payment = PaymentEntityParser()
        self.confidence = ReceiptEntityConfidenceEngine()

    def extract(
        self,
        raw_text: str = "",
        lines: list[str] | None = None,
        ocr_blocks: list[dict[str, Any]] | None = None,
    ) -> dict[str, Any]:
        geometry = self.geometry.from_inputs(raw_text=raw_text, lines=lines, boxes=ocr_blocks)
        header = self.header.parse(geometry)
        payment = self.payment.parse(geometry)
        confidence = self.confidence.score(header, payment)
        fields = self._fields(header, payment)
        logger.info("Receipt entities extracted fields=%s confidence=%s", fields, confidence)
        return {
            "schemaVersion": "receipt-entities-v1",
            "fields": fields,
            "header": header,
            "payment": payment,
            "confidence": confidence,
            "debug": {
                "visualHierarchy": header.get("visualHierarchy", {}),
                "lineCount": len(geometry),
                "lines": [
                    {
                        "index": line.index,
                        "text": line.text,
                        "bbox": {"x": round(line.x, 2), "y": round(line.y, 2), "width": round(line.width, 2), "height": round(line.height, 2)},
                        "confidence": round(line.confidence, 3),
                    }
                    for line in geometry[:80]
                ],
            },
        }

    def _fields(self, header: dict[str, Any], payment: dict[str, Any]) -> dict[str, str]:
        merchant = self._confident_value(header.get("merchant", {}), 0.64)
        address = self._confident_value(header.get("address", {}), 0.78)
        phone = self._confident_value(header.get("phone", {}), 0.7)
        date = self._confident_value(header.get("date", {}), 0.7)
        card_type = self._confident_value(payment.get("cardType", {}), 0.7)
        last_four = self._confident_value(payment.get("lastFour", {}), 0.7)
        approval = self._confident_value(payment.get("approvalCode", {}), 0.7)
        method = self._confident_value(payment.get("paymentMethod", {}), 0.7)
        return {
            "merchant": merchant,
            "address": address,
            "storeAddress": address,
            "phone": phone,
            "date": date,
            "purchaseDate": date,
            "paymentMethod": method,
            "cardType": card_type,
            "cardUsed": card_type,
            "lastFour": last_four,
            "cardLast4": last_four,
            "approvalCode": approval,
        }

    def _confident_value(self, candidate: dict[str, Any], threshold: float) -> str:
        if not isinstance(candidate, dict):
            return ""
        try:
            confidence = float(candidate.get("confidence") or 0)
        except (TypeError, ValueError):
            confidence = 0.0
        return str(candidate.get("value") or "") if confidence >= threshold else ""
