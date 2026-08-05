from __future__ import annotations

from .models import CanonicalProduct, NutritionProfile


class ProductNutritionEngine:
    """Extensible local interface; no external provider is required."""

    def enrich(self, product: CanonicalProduct | None) -> NutritionProfile:
        return product.nutrition if product is not None else NutritionProfile()

