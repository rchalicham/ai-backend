from __future__ import annotations

from .models import ProductConfidence


class ProductConfidenceEngine:
    WEIGHTS = {
        "product_match": 0.35,
        "category_match": 0.15,
        "brand_match": 0.10,
        "merchant_match": 0.10,
        "knowledge_match": 0.15,
        "constraint_confidence": 0.15,
    }

    def aggregate(
        self,
        *,
        product_match: float,
        category_match: float,
        brand_match: float,
        merchant_match: float,
        knowledge_match: float,
        constraint_confidence: float,
    ) -> ProductConfidence:
        values = {
            "product_match": product_match,
            "category_match": category_match,
            "brand_match": brand_match,
            "merchant_match": merchant_match,
            "knowledge_match": knowledge_match,
            "constraint_confidence": constraint_confidence,
        }
        clamped = {key: max(0.0, min(1.0, float(value or 0.0))) for key, value in values.items()}
        overall = sum(clamped[key] * weight for key, weight in self.WEIGHTS.items())
        return ProductConfidence(
            overall=round(overall, 6),
            **clamped,
            components=tuple((key, clamped[key]) for key in self.WEIGHTS),
        )

