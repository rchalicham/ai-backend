from __future__ import annotations

from collections.abc import Callable
from difflib import SequenceMatcher

from .models import CanonicalProduct, ProductMatch
from .product_normalizer import ProductNormalizer


class ProductMatcher:
    def __init__(
        self,
        normalizer: ProductNormalizer | None = None,
        fuzzy_threshold: float = 0.82,
        embedding_matcher: Callable[[str, tuple[CanonicalProduct, ...]], tuple[str, float] | None] | None = None,
    ) -> None:
        self.normalizer = normalizer or ProductNormalizer()
        self.fuzzy_threshold = fuzzy_threshold
        self.embedding_matcher = embedding_matcher

    def match(
        self,
        original: str,
        normalized: str,
        products: tuple[CanonicalProduct, ...],
        merchant_key: str = "",
        historical_product_ids: tuple[str, ...] = (),
    ) -> ProductMatch:
        original_value = original.strip()
        normalized_folded = normalized.casefold().strip()
        best = ProductMatch(None, "unmatched", 0.0)
        for product in products:
            canonical = product.canonical_name.casefold()
            if original_value == product.canonical_name:
                return ProductMatch(product, "exact", 1.0, original, "canonical_product")
            if normalized_folded == self.normalizer.normalize(product.canonical_name).casefold():
                return ProductMatch(product, "normalized", 0.97, normalized, "canonical_product")
            for alias in product.aliases:
                alias_normalized = self.normalizer.normalize(alias.normalized_value or alias.value).casefold()
                if normalized_folded == alias_normalized:
                    merchant_match = bool(alias.merchant_key and alias.merchant_key == merchant_key)
                    strategy = "merchant_specific" if merchant_match else "alias"
                    score = 0.98 if merchant_match else min(0.96, alias.confidence)
                    return ProductMatch(product, strategy, score, alias.value, alias.source)
            ratio = SequenceMatcher(None, normalized_folded, canonical).ratio()
            if product.product_id in historical_product_ids:
                ratio = min(1.0, ratio + 0.08)
                strategy = "historical"
            else:
                strategy = "fuzzy"
            if ratio >= self.fuzzy_threshold and ratio > best.score:
                best = ProductMatch(product, strategy, ratio, product.canonical_name, "product_repository")
        if best.product is None and self.embedding_matcher is not None:
            embedding = self.embedding_matcher(normalized, products)
            if embedding:
                product_id, score = embedding
                product = next((item for item in products if item.product_id == product_id), None)
                if product is not None:
                    return ProductMatch(
                        product, "embedding", max(0.0, min(1.0, float(score))),
                        product.canonical_name, "embedding_adapter",
                    )
        return best
