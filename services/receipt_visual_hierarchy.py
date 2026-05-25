from __future__ import annotations

import re
from statistics import median
from typing import Any


LEGAL_DISCLAIMER_TERMS = (
    "VOID WHERE PROHIBITED",
    "PROHIBITED",
    "NO PURCHASE",
    "NO PURCHASE NECESSARY",
    "SWEEPSTAKES",
    "SWEEPST",
    "OFFICIAL RULES",
    "RULES",
    "RETURN POLICY",
    "TERMS AND CONDITIONS",
    "SURVEY",
    "FEEDBACK",
    "THANK YOU",
)


def compact(value: Any) -> str:
    return re.sub(r"\s+", " ", str(value or "")).strip()


def line_text(line: Any) -> str:
    return compact(getattr(line, "text", line if isinstance(line, str) else ""))


def line_number(line: Any, key: str, default: float = 0.0) -> float:
    try:
        return float(getattr(line, key, default) or default)
    except (TypeError, ValueError):
        return default


class ReceiptVisualHierarchyEngine:
    """Scores OCR rows by visual saliency and receipt priority zones.

    The engine is intentionally document-generic: it uses geometry, confidence,
    section location, and broad receipt semantics. It does not include merchant
    templates or merchant-name rules.
    """

    def analyze(self, lines: list[Any] | None = None) -> dict[str, Any]:
        rows = [line for line in (lines or []) if line_text(line)]
        if not rows:
            return {
                "schemaVersion": "receipt-visual-hierarchy-v1",
                "lines": [],
                "zones": [],
                "debug": {"merchantCandidateRanking": [], "rejectedLowPriorityEntities": []},
            }

        page_width = max((line_number(line, "x") + max(line_number(line, "width"), len(line_text(line)) * 7.0) for line in rows), default=1.0)
        page_height = max((line_number(line, "y") + max(line_number(line, "height"), 14.0) for line in rows), default=1.0)
        heights = [max(line_number(line, "height"), 1.0) for line in rows]
        median_height = median(heights) if heights else 14.0
        sorted_rows = sorted(rows, key=lambda row: (line_number(row, "page", 1), line_number(row, "y"), line_number(row, "x")))

        line_scores = []
        for index, line in enumerate(sorted_rows):
            text = line_text(line)
            x = line_number(line, "x")
            y = line_number(line, "y")
            width = max(line_number(line, "width"), len(text) * 7.0, 1.0)
            height = max(line_number(line, "height"), median_height, 1.0)
            confidence = max(0.0, min(1.0, line_number(line, "confidence", 1.0)))
            y_ratio = y / max(page_height, 1.0)
            center_x = x + width / 2
            centeredness = max(0.0, 1.0 - abs(center_x - (page_width / 2)) / max(page_width / 2, 1.0))
            font_prominence = max(0.0, min(1.0, height / max(median_height * 1.8, 1.0)))
            width_prominence = max(0.0, min(1.0, width / max(page_width, 1.0)))
            density = len(re.sub(r"\s+", "", text)) / max(width * height, 1.0)
            text_density_score = 1.0 - min(1.0, abs(density - 0.055) / 0.12)
            zone = self._priority_zone(y_ratio)
            semantic_penalty, semantic_reasons = self._semantic_penalty(text)
            whitespace_score = self._whitespace_score(sorted_rows, index, page_height)
            zone_weight = {
                "merchant_zone": 0.18,
                "header_zone": 0.12,
                "item_table_zone": 0.1,
                "totals_zone": 0.1,
                "payment_zone": 0.06,
                "footer_legal_zone": -0.26,
            }.get(zone, 0.0)
            importance = (
                0.22 * font_prominence
                + 0.18 * centeredness
                + 0.14 * width_prominence
                + 0.12 * whitespace_score
                + 0.12 * confidence
                + 0.08 * text_density_score
                + zone_weight
                - semantic_penalty
            )
            importance = max(0.0, min(1.0, importance))
            line_scores.append({
                "lineIndex": int(getattr(line, "index", index) if getattr(line, "index", index) is not None else index),
                "text": text,
                "zone": zone,
                "visualImportance": round(importance, 3),
                "saliencyTier": self._tier(importance),
                "features": {
                    "fontProminence": round(font_prominence, 3),
                    "centeredness": round(centeredness, 3),
                    "widthProminence": round(width_prominence, 3),
                    "whitespaceGrouping": round(whitespace_score, 3),
                    "textDensity": round(text_density_score, 3),
                    "ocrConfidence": round(confidence, 3),
                    "yRatio": round(y_ratio, 3),
                },
                "bbox": {
                    "x": round(x, 2),
                    "y": round(y, 2),
                    "width": round(width, 2),
                    "height": round(height, 2),
                },
                "reasons": semantic_reasons,
            })

        zones = self._zone_summaries(line_scores)
        return {
            "schemaVersion": "receipt-visual-hierarchy-v1",
            "page": {"width": round(page_width, 2), "height": round(page_height, 2), "medianLineHeight": round(median_height, 2)},
            "lines": line_scores,
            "zones": zones,
            "debug": {
                "visualSaliencyOverlays": line_scores,
                "regionImportanceHeatmap": zones,
                "merchantCandidateRanking": self.merchant_candidate_ranking(line_scores),
                "rejectedLowPriorityEntities": [
                    row for row in line_scores
                    if row["visualImportance"] < 0.32 and any("legal" in reason or "footer" in reason for reason in row.get("reasons", []))
                ],
            },
        }

    def merchant_candidate_ranking(self, line_scores: list[dict[str, Any]]) -> list[dict[str, Any]]:
        candidates = []
        for row in line_scores:
            text = row.get("text", "")
            upper = text.upper()
            if not re.search(r"[A-Z]{3,}", upper) or re.search(r"\d{1,7}(?:[.,]\d{2})", text):
                continue
            if any(term in upper for term in LEGAL_DISCLAIMER_TERMS):
                semantic = 0.08
            elif re.search(r"\b(?:WWW\.)?[A-Z0-9][A-Z0-9-]{2,35}\.(?:COM|NET|ORG)\b", upper):
                semantic = 0.32
            elif row.get("zone") in {"merchant_zone", "header_zone"}:
                semantic = 0.2
            else:
                semantic = 0.0
            score = max(0.0, min(1.0, float(row.get("visualImportance", 0.0)) + semantic))
            candidates.append({
                "text": text,
                "lineIndex": row.get("lineIndex"),
                "zone": row.get("zone"),
                "visualImportance": row.get("visualImportance"),
                "merchantPriority": round(score, 3),
                "reasons": row.get("reasons", []),
            })
        return sorted(candidates, key=lambda item: item["merchantPriority"], reverse=True)[:12]

    def _priority_zone(self, y_ratio: float) -> str:
        if y_ratio <= 0.12:
            return "merchant_zone"
        if y_ratio <= 0.24:
            return "header_zone"
        if y_ratio <= 0.66:
            return "item_table_zone"
        if y_ratio <= 0.78:
            return "totals_zone"
        if y_ratio <= 0.88:
            return "payment_zone"
        return "footer_legal_zone"

    def _semantic_penalty(self, text: str) -> tuple[float, list[str]]:
        upper = text.upper()
        reasons: list[str] = []
        penalty = 0.0
        if any(term in upper for term in LEGAL_DISCLAIMER_TERMS):
            penalty += 0.42
            reasons.append("legal_or_footer_disclaimer")
        if re.search(r"\b(?:BARCODE|COUPON|REWARD|POLICY|RULES)\b", upper):
            penalty += 0.22
            reasons.append("low_priority_footer_semantics")
        if re.search(r"^\W*\d{8,}\W*$", upper):
            penalty += 0.3
            reasons.append("barcode_or_numeric_identifier")
        return min(0.7, penalty), reasons

    def _whitespace_score(self, rows: list[Any], index: int, page_height: float) -> float:
        current = rows[index]
        top = line_number(current, "y")
        bottom = top + max(line_number(current, "height"), 1.0)
        previous_gap = top - (line_number(rows[index - 1], "y") + max(line_number(rows[index - 1], "height"), 1.0)) if index > 0 else top
        next_gap = line_number(rows[index + 1], "y") - bottom if index + 1 < len(rows) else max(0.0, page_height - bottom)
        gap = max(previous_gap, next_gap)
        return max(0.0, min(1.0, gap / max(page_height * 0.08, 1.0)))

    def _tier(self, score: float) -> str:
        if score >= 0.68:
            return "HIGH"
        if score >= 0.4:
            return "MEDIUM"
        return "LOW"

    def _zone_summaries(self, line_scores: list[dict[str, Any]]) -> list[dict[str, Any]]:
        zones = []
        for zone in ("merchant_zone", "header_zone", "item_table_zone", "totals_zone", "payment_zone", "footer_legal_zone"):
            rows = [row for row in line_scores if row.get("zone") == zone]
            if not rows:
                continue
            zones.append({
                "zone": zone,
                "lineIndexes": [row["lineIndex"] for row in rows],
                "importance": round(sum(row["visualImportance"] for row in rows) / max(len(rows), 1), 3),
                "dominantTier": self._tier(max(row["visualImportance"] for row in rows)),
            })
        return zones
