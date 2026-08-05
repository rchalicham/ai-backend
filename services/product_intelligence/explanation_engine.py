from __future__ import annotations

from .models import ProductExplanation, ProductMatch


class ProductExplanationEngine:
    def explain(
        self,
        match: ProductMatch,
        normalized: str,
        category_reason: str,
        brand_reason: str,
    ) -> ProductExplanation:
        if match.product is None:
            summary = f"No approved canonical product matched normalized description '{normalized}'."
            product_id = ""
            reasons = ("original receipt description preserved", "no canonical identity asserted")
        else:
            summary = (
                f"Matched canonical product '{match.product.canonical_name}' using "
                f"{match.strategy.replace('_', ' ')} matching."
            )
            product_id = match.product.product_id
            reasons = (
                f"normalized description: {normalized}",
                f"match score: {match.score:.3f}",
            )
        return ProductExplanation(
            product_id=product_id,
            summary=summary,
            match_reasons=reasons,
            category_reason=category_reason,
            brand_reason=brand_reason,
            knowledge_sources=(match.knowledge_source,) if match.knowledge_source else (),
        )

