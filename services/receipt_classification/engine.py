from __future__ import annotations

from typing import Iterable

from services.merchant_intelligence import MerchantBlueprint
from services.receipt_dom import ReceiptDocument
from services.receipt_structure import ReceiptPhysicalStructure

from .confidence import ReceiptConfidenceEngine
from .features import ReceiptFeatureExtractor
from .matcher import ReceiptBlueprintMatcher
from .models import BlueprintComparison, BlueprintLearningSuggestion, ReceiptClassification
from .ranking import ReceiptCandidateRanker
from .similarity import ReceiptSimilarityEngine


class ReceiptClassificationEngine:
    def __init__(
        self,
        *,
        feature_extractor: ReceiptFeatureExtractor | None = None,
        blueprint_matcher: ReceiptBlueprintMatcher | None = None,
        similarity_engine: ReceiptSimilarityEngine | None = None,
        confidence_engine: ReceiptConfidenceEngine | None = None,
        candidate_ranker: ReceiptCandidateRanker | None = None,
        top_n: int = 3,
    ) -> None:
        self.feature_extractor = feature_extractor or ReceiptFeatureExtractor()
        self.blueprint_matcher = blueprint_matcher or ReceiptBlueprintMatcher()
        self.similarity_engine = similarity_engine or ReceiptSimilarityEngine()
        self.confidence_engine = confidence_engine or ReceiptConfidenceEngine()
        self.candidate_ranker = candidate_ranker or ReceiptCandidateRanker()
        self.top_n = top_n

    def classify(
        self,
        document: ReceiptDocument,
        structure: ReceiptPhysicalStructure,
        blueprints: Iterable[MerchantBlueprint] = (),
    ) -> ReceiptClassification:
        vector = self.feature_extractor.extract(document, structure)
        comparisons: list[BlueprintComparison] = []
        for profile in self.blueprint_matcher.profiles(blueprints):
            scores, deltas, coverage = self.similarity_engine.compare(vector, profile)
            confidence, breakdown = self.confidence_engine.calculate(scores, deltas, profile.confidence)
            comparisons.append(BlueprintComparison(
                receipt_family=profile.receipt_family,
                profile_version=profile.profile_version,
                similarity_scores=scores,
                confidence_breakdown=breakdown,
                feature_deltas=deltas,
                coverage=coverage,
                confidence=confidence,
                blueprint_reference=profile.blueprint_reference,
            ))
        frozen_comparisons = tuple(comparisons)
        candidates = self.candidate_ranker.rank(frozen_comparisons, top_n=self.top_n)
        suggestions = tuple(
            BlueprintLearningSuggestion(
                receipt_family=candidate.receipt_family,
                proposed_metrics=vector.flatten(),
                confidence=candidate.confidence,
            )
            for candidate in candidates
        )
        return ReceiptClassification(
            document_id=document.id,
            feature_vector=vector,
            candidates=candidates,
            comparisons=frozen_comparisons,
            learning_suggestions=suggestions,
            diagnostics=(
                ("classificationScope", "physical_receipt_family_only"),
                ("usesOcrText", False),
                ("merchantDetectionPerformed", False),
                ("affectsExtraction", False),
                ("blueprintProfilesCompared", len(comparisons)),
            ),
        )

    def safe_classify(
        self,
        document: ReceiptDocument | None,
        structure: ReceiptPhysicalStructure | None,
        blueprints: Iterable[MerchantBlueprint] = (),
    ) -> ReceiptClassification | None:
        if document is None or structure is None:
            return None
        try:
            return self.classify(document, structure, blueprints)
        except Exception:
            return None
