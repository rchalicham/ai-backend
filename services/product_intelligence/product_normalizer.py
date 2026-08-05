from __future__ import annotations

import re
from collections.abc import Mapping


class ProductNormalizer:
    DEFAULT_ABBREVIATIONS = {
        "MLK": "MILK",
        "WHT": "WHITE",
        "BRD": "BREAD",
        "CHKN": "CHICKEN",
        "YOG": "YOGURT",
        "ORG": "ORGANIC",
        "DZ": "DOZEN",
        "PC": "PIECE",
        "PCT": "PERCENT",
        "WMT": "",
    }
    DEFAULT_OCR_CORRECTIONS = {"0IL": "OIL", "M1LK": "MILK"}

    def __init__(
        self,
        abbreviations: Mapping[str, str] | None = None,
        ocr_corrections: Mapping[str, str] | None = None,
    ) -> None:
        self.abbreviations = {
            **self.DEFAULT_ABBREVIATIONS, **dict(abbreviations or {}),
        }
        self.ocr_corrections = {
            **self.DEFAULT_OCR_CORRECTIONS, **dict(ocr_corrections or {}),
        }

    def normalize(self, value: str, merchant_abbreviations: Mapping[str, str] | None = None) -> str:
        text = re.sub(r"[^A-Z0-9%]+", " ", str(value or "").upper()).strip()
        substitutions = {**self.abbreviations, **dict(merchant_abbreviations or {})}
        tokens = [
            self.ocr_corrections.get(token, substitutions.get(token, token))
            for token in text.split()
        ]
        normalized = " ".join(tokens)
        normalized = re.sub(r"\b(\d+)\s*%", r"\1 PERCENT", normalized)
        return re.sub(r"\s+", " ", normalized).strip().title()
