from __future__ import annotations

from collections.abc import Mapping, Sequence
from typing import Any

from .brand_engine import ProductBrandEngine
from .category_engine import ProductCategoryEngine
from .confidence_engine import ProductConfidenceEngine
from .diagnostics import ProductDiagnosticsEngine
from .explanation_engine import ProductExplanationEngine
from .learning import ProductLearningService
from .models import ProductEnrichment, ProductIntelligenceResult
from .nutrition_engine import ProductNutritionEngine
from .pricing_engine import ProductPricingEngine
from .product_classifier import ProductClassifier
from .product_matcher import ProductMatcher
from .product_normalizer import ProductNormalizer
from .product_repository import ProductRepository


class ProductIntelligenceEngine:
    """Enriches copied parser items without replacing any extracted value."""

    def __init__(
        self,
        repository: ProductRepository | None = None,
        normalizer: ProductNormalizer | None = None,
        matcher: ProductMatcher | None = None,
        classifier: ProductClassifier | None = None,
        category_engine: ProductCategoryEngine | None = None,
        brand_engine: ProductBrandEngine | None = None,
        nutrition_engine: ProductNutritionEngine | None = None,
        pricing_engine: ProductPricingEngine | None = None,
        confidence_engine: ProductConfidenceEngine | None = None,
        explanation_engine: ProductExplanationEngine | None = None,
        diagnostics_engine: ProductDiagnosticsEngine | None = None,
        learning: ProductLearningService | None = None,
    ) -> None:
        self.repository = repository or ProductRepository()
        self.normalizer = normalizer or ProductNormalizer()
        self.matcher = matcher or ProductMatcher(self.normalizer)
        self.classifier = classifier or ProductClassifier()
        self.category_engine = category_engine or ProductCategoryEngine()
        self.brand_engine = brand_engine or ProductBrandEngine()
        self.nutrition_engine = nutrition_engine or ProductNutritionEngine()
        self.pricing_engine = pricing_engine or ProductPricingEngine()
        self.confidence_engine = confidence_engine or ProductConfidenceEngine()
        self.explanation_engine = explanation_engine or ProductExplanationEngine()
        self.diagnostics_engine = diagnostics_engine or ProductDiagnosticsEngine()
        self.learning = learning or ProductLearningService()

    def enrich(
        self,
        extracted_items: Sequence[Mapping[str, Any]],
        *,
        constraint_result: Any = None,
        merchant_key: str = "",
        historical_product_ids: tuple[str, ...] = (),
        currency: str = "",
    ) -> ProductIntelligenceResult:
        products = self.repository.load_products()
        constraint_confidence = self._constraint_confidence(constraint_result)
        enrichments = []
        for index, item in enumerate(extracted_items):
            original = str(
                item.get("name") or item.get("description") or item.get("text") or ""
            ).strip()
            normalized = self.normalizer.normalize(original)
            match = self.matcher.match(
                original, normalized, products, merchant_key, historical_product_ids,
            )
            classification, classification_score = self.classifier.classify(
                match.product, normalized,
            )
            department, category, subcategory, category_score = self.category_engine.assign(
                match.product, classification,
            )
            brand, manufacturer, brand_score, brand_reason = self.brand_engine.identify(
                match.product, normalized, merchant_key,
            )
            merchant_score = 1.0 if match.strategy == "merchant_specific" else 0.5 if merchant_key else 0.0
            knowledge_score = 1.0 if match.product is not None else 0.0
            confidence = self.confidence_engine.aggregate(
                product_match=match.score,
                category_match=max(classification_score, category_score),
                brand_match=brand_score,
                merchant_match=merchant_score,
                knowledge_match=knowledge_score,
                constraint_confidence=constraint_confidence,
            )
            category_reason = (
                "Selected from approved canonical product knowledge."
                if match.product else f"Assigned extensible class '{classification}' from normalized text."
            )
            explanation = self.explanation_engine.explain(
                match, normalized, category_reason, brand_reason,
            )
            observed_price = self._price(item)
            enrichments.append(ProductEnrichment(
                item_index=index,
                original_description=original,
                normalized_description=normalized,
                canonical_product=match.product,
                match_strategy=match.strategy,
                department=department,
                category=category,
                subcategory=subcategory,
                brand=brand,
                manufacturer=manufacturer,
                nutrition=self.nutrition_engine.enrich(match.product),
                pricing=self.pricing_engine.profile(observed_price, match.product, currency),
                confidence=confidence,
                explanation=explanation,
            ))
        values = tuple(enrichments)
        return ProductIntelligenceResult(
            enrichments=values,
            diagnostics=self.diagnostics_engine.create(values),
            learning_suggestions=self.learning.suggest(values),
        )

    def safe_enrich(
        self,
        extracted_items: Sequence[Mapping[str, Any]] | None,
        **kwargs: Any,
    ) -> ProductIntelligenceResult:
        try:
            return self.enrich(tuple(extracted_items or ()), **kwargs)
        except Exception as exc:
            return ProductIntelligenceResult(diagnostics=self.diagnostics_engine.failed(exc))

    @staticmethod
    def _price(item: Mapping[str, Any]) -> float | None:
        value = item.get("price")
        if value is None:
            value = item.get("lineTotal") or item.get("total")
        try:
            return float(str(value).replace("$", "").replace(",", ""))
        except (TypeError, ValueError):
            return None

    @staticmethod
    def _constraint_confidence(result: Any) -> float:
        decision = getattr(result, "decision", None)
        best = getattr(decision, "best_candidate", None)
        scores = getattr(decision, "scores", ()) or ()
        score = next(
            (item for item in scores if best is not None and item.candidate_id == best.candidate_id),
            None,
        )
        confidence = getattr(score, "confidence", None)
        return float(getattr(confidence, "normalized", 0.0) or 0.0)

