from __future__ import annotations

import os
import re
from dataclasses import dataclass, field
from typing import Any

from services.receipt_geometry import ReceiptGeometryEngine
from services.receipt_dom import ReceiptDocument, ReceiptDomBuilder, ReceiptDomSerializer
from services.receipt_structure import (
    ReceiptPhysicalStructure,
    ReceiptPhysicalStructureEngine,
    ReceiptStructureSerializer,
)
from services.merchant_intelligence import (
    MerchantBlueprint,
    MerchantBlueprintService,
    MerchantIntelligenceContext,
    MerchantIntelligenceSerializer,
)
from services.receipt_classification import (
    ReceiptClassification,
    ReceiptClassificationEngine,
    ReceiptClassificationSerializer,
)
from services.document_family import (
    DocumentFamilyContext,
    DocumentFamilyEngine,
    DocumentFamilySerializer,
)
from services.receipt_grammar import (
    ReceiptGrammarContext,
    ReceiptGrammarEngine,
    ReceiptGrammarSerializer,
)
from services.receipt_constraints import (
    ConstraintEngine,
    ReceiptConstraintResult,
    ReceiptConstraintSerializer,
)
from services.product_intelligence import (
    ProductIntelligenceEngine,
    ProductIntelligenceResult,
    ProductIntelligenceSerializer,
)
from services.enterprise_graph import (
    EnterpriseGraphContext,
    EnterpriseGraphEngine,
    EnterpriseGraphSerializer,
)
from services.cross_document_intelligence import (
    CrossDocumentIntelligenceEngine,
    CrossDocumentSerializer,
    IntelligenceResult,
)
from services.enterprise_learning import (
    EnterpriseLearningEngine,
    EnterpriseLearningResult,
    EnterpriseLearningSerializer,
)
from services.enterprise_reasoning import (
    EnterpriseReasoningEngine,
    EnterpriseReasoningSerializer,
    ReasoningContextBuilder,
    ReasoningResponse,
)
from services.presentation_projection import (
    BusinessProjection,
    PresentationProjectionEngine,
    PresentationProjectionSerializer,
)
from services.intelligence_snapshot import (
    InMemorySnapshotRepository,
    ReceiptIntelligenceSnapshotEngine,
    SnapshotSerializer,
)
from services.receipt_quality import ReceiptCaptureQualityEngine
from services.receipt_processing import ReceiptProcessingExperienceEngine, ReceiptProcessingSerializer
from services.document_review import DocumentFamilyReviewEngine, DocumentReviewSerializer


@dataclass
class ReceiptAgentAttempt:
    index: int
    strategy: str
    source: str
    donut: dict[str, Any] = field(default_factory=dict)
    semantic: dict[str, Any] = field(default_factory=dict)
    llama: dict[str, Any] | None = None
    ocr_fallback: dict[str, Any] = field(default_factory=dict)
    score: float = 0.0
    retry_plan: list[dict[str, Any]] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)
    receipt_document: ReceiptDocument | None = None
    receipt_structure: ReceiptPhysicalStructure | None = None
    receipt_classification: ReceiptClassification | None = None
    document_family_context: DocumentFamilyContext | None = None
    receipt_grammar: ReceiptGrammarContext | None = None
    receipt_constraint_result: ReceiptConstraintResult | None = None
    product_intelligence: ProductIntelligenceResult | None = None
    enterprise_knowledge_graph: EnterpriseGraphContext | None = None
    cross_document_intelligence: IntelligenceResult | None = None
    enterprise_learning: EnterpriseLearningResult | None = None
    enterprise_reasoning: ReasoningResponse | None = None
    business_projection: BusinessProjection | None = None

    def summary(self) -> dict[str, Any]:
        validation = self.semantic.get("validation") or {}
        llama_intelligence = (self.llama or {}).get("receiptIntelligence") or {}
        return {
            "index": self.index,
            "strategy": self.strategy,
            "source": self.source,
            "score": round(float(self.score or 0.0), 3),
            "donutAvailable": bool(self.donut.get("available")),
            "ocrFallbackAvailable": bool(self.ocr_fallback.get("available")),
            "itemCount": len(self.semantic.get("items") or []),
            "merchant": self.semantic.get("merchant") or self.semantic.get("storeName") or "",
            "validation": validation,
            "retryPlan": self.retry_plan,
            "warnings": self.warnings,
            "llamaValidation": llama_intelligence.get("validation", {}),
        }


class ReceiptAgentOrchestrator:
    """Autonomous receipt-processing loop over the existing deterministic services.

    The agent is intentionally bounded. It executes only local image/OCR/semantic
    retry actions, selects the highest-scoring result, and emits review tasks for
    the existing unprocessed receipt UI.
    """

    def __init__(
        self,
        *,
        donut_receipt_service: Any,
        receipt_image_isolation_service: Any,
        receipt_ocr_service: Any,
        llm_service: Any,
        receipt_geometry_engine: ReceiptGeometryEngine | None = None,
        receipt_dom_builder: ReceiptDomBuilder | None = None,
        receipt_dom_serializer: ReceiptDomSerializer | None = None,
        receipt_structure_engine: ReceiptPhysicalStructureEngine | None = None,
        receipt_structure_serializer: ReceiptStructureSerializer | None = None,
        merchant_blueprint_service: MerchantBlueprintService | None = None,
        merchant_intelligence_serializer: MerchantIntelligenceSerializer | None = None,
        receipt_classification_engine: ReceiptClassificationEngine | None = None,
        receipt_classification_serializer: ReceiptClassificationSerializer | None = None,
        document_family_engine: DocumentFamilyEngine | None = None,
        document_family_serializer: DocumentFamilySerializer | None = None,
        receipt_grammar_engine: ReceiptGrammarEngine | None = None,
        receipt_grammar_serializer: ReceiptGrammarSerializer | None = None,
        receipt_constraint_engine: ConstraintEngine | None = None,
        receipt_constraint_serializer: ReceiptConstraintSerializer | None = None,
        product_intelligence_engine: ProductIntelligenceEngine | None = None,
        product_intelligence_serializer: ProductIntelligenceSerializer | None = None,
        enterprise_graph_engine: EnterpriseGraphEngine | None = None,
        enterprise_graph_serializer: EnterpriseGraphSerializer | None = None,
        cross_document_intelligence_engine: CrossDocumentIntelligenceEngine | None = None,
        cross_document_serializer: CrossDocumentSerializer | None = None,
        enterprise_learning_engine: EnterpriseLearningEngine | None = None,
        enterprise_learning_serializer: EnterpriseLearningSerializer | None = None,
        enterprise_reasoning_engine: EnterpriseReasoningEngine | None = None,
        enterprise_reasoning_serializer: EnterpriseReasoningSerializer | None = None,
        reasoning_context_builder: ReasoningContextBuilder | None = None,
        presentation_projection_engine: PresentationProjectionEngine | None = None,
        presentation_projection_serializer: PresentationProjectionSerializer | None = None,
        intelligence_snapshot_engine: ReceiptIntelligenceSnapshotEngine | None = None,
        intelligence_snapshot_serializer: SnapshotSerializer | None = None,
        capture_quality_engine: ReceiptCaptureQualityEngine | None = None,
        processing_experience_engine: ReceiptProcessingExperienceEngine | None = None,
        processing_experience_serializer: ReceiptProcessingSerializer | None = None,
        document_review_engine: DocumentFamilyReviewEngine | None = None,
        document_review_serializer: DocumentReviewSerializer | None = None,
    ) -> None:
        self.donut_receipt_service = donut_receipt_service
        self.receipt_image_isolation_service = receipt_image_isolation_service
        self.receipt_ocr_service = receipt_ocr_service
        self.llm_service = llm_service
        self.receipt_geometry_engine = receipt_geometry_engine or ReceiptGeometryEngine()
        self.receipt_dom_builder = receipt_dom_builder or ReceiptDomBuilder()
        self.receipt_dom_serializer = receipt_dom_serializer or ReceiptDomSerializer()
        self.receipt_structure_engine = receipt_structure_engine or ReceiptPhysicalStructureEngine()
        self.receipt_structure_serializer = receipt_structure_serializer or ReceiptStructureSerializer()
        self.merchant_blueprint_service = merchant_blueprint_service
        self.merchant_intelligence_serializer = merchant_intelligence_serializer or MerchantIntelligenceSerializer()
        self.receipt_classification_engine = receipt_classification_engine or ReceiptClassificationEngine()
        self.receipt_classification_serializer = receipt_classification_serializer or ReceiptClassificationSerializer()
        self.document_family_engine = document_family_engine or DocumentFamilyEngine()
        self.document_family_serializer = document_family_serializer or DocumentFamilySerializer()
        self.receipt_grammar_engine = receipt_grammar_engine or ReceiptGrammarEngine()
        self.receipt_grammar_serializer = receipt_grammar_serializer or ReceiptGrammarSerializer()
        self.receipt_constraint_engine = receipt_constraint_engine or ConstraintEngine()
        self.receipt_constraint_serializer = receipt_constraint_serializer or ReceiptConstraintSerializer()
        self.product_intelligence_engine = product_intelligence_engine or ProductIntelligenceEngine()
        self.product_intelligence_serializer = product_intelligence_serializer or ProductIntelligenceSerializer()
        self.enterprise_graph_engine = enterprise_graph_engine or EnterpriseGraphEngine()
        self.enterprise_graph_serializer = enterprise_graph_serializer or EnterpriseGraphSerializer()
        self.cross_document_intelligence_engine = (
            cross_document_intelligence_engine or CrossDocumentIntelligenceEngine()
        )
        self.cross_document_serializer = cross_document_serializer or CrossDocumentSerializer()
        self.enterprise_learning_engine = enterprise_learning_engine or EnterpriseLearningEngine()
        self.enterprise_learning_serializer = (
            enterprise_learning_serializer or EnterpriseLearningSerializer()
        )
        self.enterprise_reasoning_engine = (
            enterprise_reasoning_engine or EnterpriseReasoningEngine()
        )
        self.enterprise_reasoning_serializer = (
            enterprise_reasoning_serializer or EnterpriseReasoningSerializer()
        )
        self.reasoning_context_builder = reasoning_context_builder or ReasoningContextBuilder()
        self.presentation_projection_engine = presentation_projection_engine or PresentationProjectionEngine()
        self.presentation_projection_serializer = presentation_projection_serializer or PresentationProjectionSerializer()
        self.intelligence_snapshot_engine = intelligence_snapshot_engine or ReceiptIntelligenceSnapshotEngine(
            InMemorySnapshotRepository(),
        )
        self.intelligence_snapshot_serializer = intelligence_snapshot_serializer or SnapshotSerializer()
        self.capture_quality_engine = capture_quality_engine
        self.processing_experience_engine = processing_experience_engine
        self.processing_experience_serializer = processing_experience_serializer or ReceiptProcessingSerializer()
        self.document_review_engine = document_review_engine
        self.document_review_serializer = document_review_serializer or DocumentReviewSerializer()
        self.max_attempts = int(os.getenv("RECEIPT_AGENT_MAX_ATTEMPTS", "3"))
        self.accept_confidence = float(os.getenv("RECEIPT_AGENT_ACCEPT_CONFIDENCE", "0.82"))
        self.review_confidence = float(os.getenv("RECEIPT_AGENT_REVIEW_CONFIDENCE", "0.78"))
        self.ocr_first_reprocess = os.getenv("RECEIPT_AGENT_OCR_FIRST_REPROCESS", "true").lower() not in {"0", "false", "no"}

    async def process(
        self,
        *,
        image_bytes: bytes = b"",
        raw_text: str = "",
        lines: list[str] | None = None,
        ocr_blocks: list[dict[str, Any]] | None = None,
        parser_json: dict[str, Any] | None = None,
        ocr_engine: str | None = None,
        ocr_variants: list[dict[str, Any]] | None = None,
        run_llama: bool = True,
        source_image_id: str = "",
        source_filename: str = "",
        merchant_knowledge_key: str = "",
    ) -> dict[str, Any]:
        parser_json = parser_json or {}
        supplied_lines = lines or []
        supplied_blocks = ocr_blocks or []
        supplied_variants = ocr_variants or []
        merchant_intelligence = self._load_merchant_intelligence(merchant_knowledge_key)

        capture_quality = None
        if image_bytes and self.capture_quality_engine is not None:
            capture_quality = self.capture_quality_engine.evaluate(image_bytes)
            if not capture_quality.passed:
                response = self._quality_failure_response(capture_quality, parser_json)
                response = self._attach_document_review(response)
                return self._attach_processing_experience(response)
            image_bytes = capture_quality.normalized_image_bytes

        image_sources = self._image_sources(image_bytes)
        if not image_sources:
            image_sources = [{"source": "text_only", "strategy": "semantic_text_only", "imageBytes": b"", "diagnostics": {}}]

        attempts: list[ReceiptAgentAttempt] = []
        for source in image_sources[: self.max_attempts]:
            attempt = await self._run_attempt(
                index=len(attempts),
                source=source,
                raw_text=raw_text,
                supplied_lines=supplied_lines,
                supplied_blocks=supplied_blocks,
                parser_json=parser_json,
                ocr_engine=ocr_engine,
                ocr_variants=supplied_variants,
                run_llama=run_llama,
                source_image_id=source_image_id,
                source_filename=source_filename,
                classification_blueprints=(
                    (merchant_intelligence.blueprint,)
                    if merchant_intelligence is not None and merchant_intelligence.blueprint is not None
                    else ()
                ),
                merchant_knowledge_key=merchant_knowledge_key,
            )
            attempts.append(attempt)
            if self._attempt_is_good_enough(attempt):
                break

        best = max(attempts, key=lambda attempt: attempt.score) if attempts else ReceiptAgentAttempt(0, "none", "none")
        response = {
            "donut": best.donut,
            "semantic": best.semantic,
            "llama": best.llama,
        }
        if capture_quality is not None:
            response["receiptQuality"] = capture_quality.to_dict()
        if best.receipt_document is not None:
            response["receiptDocument"] = self.receipt_dom_serializer.to_dict(best.receipt_document, debug=True)
        if best.receipt_structure is not None:
            response["receiptStructure"] = self.receipt_structure_serializer.to_dict(best.receipt_structure, debug=True)
        if best.receipt_classification is not None:
            response["receiptClassification"] = self.receipt_classification_serializer.to_dict(
                best.receipt_classification, debug=True,
            )
        if best.document_family_context is not None:
            response["documentFamilyContext"] = self.document_family_serializer.to_dict(
                best.document_family_context,
            )
        if best.receipt_grammar is not None:
            response["receiptGrammar"] = self.receipt_grammar_serializer.context_to_dict(best.receipt_grammar)
        if best.receipt_constraint_result is not None:
            response["receiptConstraintResult"] = self.receipt_constraint_serializer.to_dict(
                best.receipt_constraint_result,
            )
        if best.product_intelligence is not None:
            response["productIntelligence"] = self.product_intelligence_serializer.to_dict(
                best.product_intelligence,
            )
        if best.enterprise_knowledge_graph is not None:
            response["enterpriseKnowledgeGraph"] = self.enterprise_graph_serializer.to_dict(
                best.enterprise_knowledge_graph,
            )
        if best.cross_document_intelligence is not None:
            response["crossDocumentIntelligence"] = self.cross_document_serializer.to_dict(
                best.cross_document_intelligence,
            )
        if best.enterprise_learning is not None:
            response["enterpriseLearning"] = self.enterprise_learning_serializer.to_dict(
                best.enterprise_learning,
            )
        if best.enterprise_reasoning is not None:
            response["enterpriseReasoning"] = self.enterprise_reasoning_serializer.to_dict(
                best.enterprise_reasoning,
            )
        if best.business_projection is not None:
            response["businessProjection"] = self.presentation_projection_serializer.to_dict(
                best.business_projection,
            )
        if merchant_intelligence is not None:
            response["merchantIntelligence"] = self.merchant_intelligence_serializer.context_to_dict(merchant_intelligence)
        response = self._attach_document_review(response)
        agent = self._build_agent_summary(
            attempts=attempts,
            selected=best,
            parser_json=parser_json,
            isolation_diagnostics=[source.get("diagnostics") for source in image_sources if source.get("diagnostics")],
            document_review=response.get("documentReview"),
        )
        response["receiptAgent"] = agent
        self._attach_agent_metadata(response, agent)
        response = self._attach_processing_experience(response)
        snapshot_receipt_id = (
            best.receipt_document.id if best.receipt_document is not None
            else source_image_id or source_filename or "anonymous-receipt"
        )
        try:
            snapshot = self.intelligence_snapshot_engine.capture(
                response,
                receipt_id=snapshot_receipt_id,
            )
            response["receiptIntelligenceSnapshot"] = self.intelligence_snapshot_serializer.to_dict(snapshot)
            response["snapshotProjection"] = self.intelligence_snapshot_serializer.to_dict(
                self.intelligence_snapshot_engine.project(snapshot),
            )
            response["snapshotHistory"] = self.intelligence_snapshot_serializer.to_dict(
                self.intelligence_snapshot_engine.history(snapshot_receipt_id),
            )
        except Exception as exc:
            response["receiptIntelligenceSnapshotDiagnostics"] = {
                "persisted": False,
                "warning": f"snapshot_capture_failed:{type(exc).__name__}",
                "parserModified": False,
                "receiptModified": False,
            }
        return response

    def _attach_document_review(self, response: dict[str, Any]) -> dict[str, Any]:
        if self.document_review_engine is None:
            return response
        result = self.document_review_engine.review(response)
        return {**response, "documentReview": self.document_review_serializer.to_dict(result)}

    def _attach_processing_experience(self, response: dict[str, Any]) -> dict[str, Any]:
        if self.processing_experience_engine is None:
            return response
        experience = self.processing_experience_engine.build(response)
        return {**response, "receiptProcessing": self.processing_experience_serializer.to_dict(experience)}

    @staticmethod
    def _quality_failure_response(capture_quality: Any, parser_json: dict[str, Any]) -> dict[str, Any]:
        quality = capture_quality.to_dict()
        reasons = [
            {
                "field": "image",
                "reason": recommendation.code,
                "severity": recommendation.severity,
                "detail": recommendation.message,
                "action": recommendation.message,
            }
            for recommendation in capture_quality.recommendations
        ]
        return {
            "donut": {"available": False, "warning": "capture_quality_gate_failed"},
            "semantic": dict(parser_json),
            "llama": None,
            "receiptQuality": quality,
            "receiptAgent": {
                "schemaVersion": "receipt-agent-v1",
                "status": "quality_failure",
                "selectedAttempt": None,
                "attemptCount": 0,
                "confidence": capture_quality.confidence,
                "autonomousActions": [],
                "attempts": [],
                "humanReview": {
                    "required": True,
                    "queue": "capture_quality",
                    "reviewMode": "recapture",
                    "priority": "high",
                    "riskScore": round((1.0 - capture_quality.overall_score) * 100),
                    "summary": "Capture quality failed. Recapture before OCR.",
                    "reasons": reasons,
                    "actionableExplanations": [item.message for item in capture_quality.recommendations],
                    "suggestedChecks": [item.factor for item in capture_quality.recommendations],
                },
                "diagnostics": {"ocrInvoked": False, "parserModified": False},
            },
        }

    def _load_merchant_intelligence(self, merchant_knowledge_key: str) -> MerchantIntelligenceContext | None:
        """Explicit-key knowledge lookup only; never derives or detects merchant identity."""
        if self.merchant_blueprint_service is None:
            return None
        try:
            return self.merchant_blueprint_service.load_context(merchant_knowledge_key)
        except Exception as exc:
            return MerchantIntelligenceContext(
                merchant_key=merchant_knowledge_key,
                blueprint=None,
                loaded=False,
                diagnostics=(
                    ("lookupMode", "explicit_key_only"),
                    ("detectionPerformed", False),
                    ("affectsExtraction", False),
                    ("warning", f"knowledge_lookup_failed:{exc.__class__.__name__}"),
                ),
            )

    async def _run_attempt(
        self,
        *,
        index: int,
        source: dict[str, Any],
        raw_text: str,
        supplied_lines: list[str],
        supplied_blocks: list[dict[str, Any]],
        parser_json: dict[str, Any],
        ocr_engine: str | None,
        ocr_variants: list[dict[str, Any]],
        run_llama: bool,
        source_image_id: str,
        source_filename: str,
        classification_blueprints: tuple[MerchantBlueprint, ...],
        merchant_knowledge_key: str,
    ) -> ReceiptAgentAttempt:
        image_bytes = source.get("imageBytes") or b""
        use_ocr_first = self._use_ocr_first_attempt(source, run_llama)
        donut_json = {
            "available": True,
            "model": "ocr-first-reprocess",
            "warning": "donut_skipped_for_ocr_first_reprocess",
        } if use_ocr_first and image_bytes else await self.donut_receipt_service.analyze_image_bytes(image_bytes) if image_bytes else {
            "available": False,
            "warning": "text_only_receipt_agent_attempt",
        }
        next_raw_text = raw_text
        next_lines = list(supplied_lines)
        next_blocks = list(supplied_blocks)
        ocr_fallback: dict[str, Any] = {}
        if self._needs_ocr_fallback(donut_json, next_raw_text, next_lines, next_blocks) and image_bytes:
            ocr_fallback = self.receipt_ocr_service.extract(image_bytes).to_dict()
            next_raw_text, next_lines, next_blocks = self._merge_ocr_fallback(next_raw_text, next_lines, next_blocks, ocr_fallback)

        receipt_document = self._build_receipt_document(
            image_bytes=image_bytes,
            lines=next_lines,
            ocr_blocks=next_blocks,
            ocr_engine=ocr_engine or source.get("strategy") or "receipt-agent",
            source_image_id=source_image_id,
            source_filename=source_filename,
        )
        receipt_structure = self.receipt_structure_engine.safe_analyze(receipt_document)
        receipt_classification = self.receipt_classification_engine.safe_classify(
            receipt_document,
            receipt_structure,
            classification_blueprints,
        )
        document_family_context = self.document_family_engine.safe_evaluate(
            receipt_document,
            receipt_structure,
            receipt_classification,
        )
        receipt_grammar = self.receipt_grammar_engine.safe_evaluate(
            receipt_document,
            receipt_structure,
            receipt_classification,
            document_family_context=document_family_context,
        )
        receipt_constraint_result = self.receipt_constraint_engine.safe_evaluate(
            receipt_document,
            receipt_structure,
            receipt_grammar,
            document_family_context=document_family_context,
        )
        donut_json = self.donut_receipt_service.consolidate_receipt_rows(
            donut_json,
            raw_text=next_raw_text,
            lines=next_lines,
            ocr_blocks=next_blocks,
            parser_json=parser_json,
        )
        if ocr_fallback:
            donut_json["ocrFallback"] = ocr_fallback

        semantic_ocr_variants = ocr_variants or ocr_fallback.get("ocrVariants") or []
        semantic_parser_json = self._semantic_parser_json(parser_json, donut_json)
        semantic = self.llm_service.receipt_intelligence.to_structured_json(
            raw_text=next_raw_text,
            lines=next_lines,
            parser_json=semantic_parser_json,
            ocr_variants=semantic_ocr_variants,
            ocr_blocks=next_blocks,
            ocr_engine=ocr_engine or source.get("strategy") or "receipt-agent",
        )
        semantic = self._prefer_consolidated_receipt_rows(semantic, donut_json)
        semantic = self._reconcile_merchant_confidence(semantic, parser_json=semantic_parser_json)
        semantic = self._reconcile_semantic_item_candidates(semantic)
        product_intelligence = self.product_intelligence_engine.safe_enrich(
            tuple(
                dict(item) for item in (semantic.get("items") or ())
                if isinstance(item, dict)
            ),
            constraint_result=receipt_constraint_result,
            merchant_key=merchant_knowledge_key,
            currency=str(semantic.get("currency") or ""),
        )
        enterprise_knowledge_graph = self.enterprise_graph_engine.safe_build(
            product_intelligence,
            receipt_id=receipt_document.id if receipt_document is not None else (
                source_image_id or f"attempt-{index}"
            ),
            merchant_key=merchant_knowledge_key,
            receipt_context=dict(semantic),
        )
        cross_document_intelligence = self.cross_document_intelligence_engine.safe_analyze(
            enterprise_knowledge_graph,
            document_id=receipt_document.id if receipt_document is not None else (
                source_image_id or f"attempt-{index}"
            ),
        )
        enterprise_learning = self.enterprise_learning_engine.safe_evaluate(
            cross_document_intelligence,
        )
        reasoning_document_id = (
            receipt_document.id if receipt_document is not None
            else source_image_id or f"attempt-{index}"
        )
        reasoning_context = self.reasoning_context_builder.build(
            f"reasoning-context:{reasoning_document_id}",
            constraint_result=(
                self.receipt_constraint_serializer.to_dict(receipt_constraint_result)
                if receipt_constraint_result is not None else None
            ),
            product_intelligence=(
                self.product_intelligence_serializer.to_dict(product_intelligence)
                if product_intelligence is not None else None
            ),
            enterprise_graph=(
                self.enterprise_graph_serializer.to_dict(enterprise_knowledge_graph)
                if enterprise_knowledge_graph is not None else None
            ),
            cross_document_intelligence=(
                self.cross_document_serializer.to_dict(cross_document_intelligence)
                if cross_document_intelligence is not None else None
            ),
            enterprise_learning=(
                self.enterprise_learning_serializer.to_dict(enterprise_learning)
                if enterprise_learning is not None else None
            ),
        )
        enterprise_reasoning = self.enterprise_reasoning_engine.safe_reason(
            self.enterprise_reasoning_engine.request(
                "Summarize the validated enterprise evidence for this receipt.",
                request_id=f"receipt-reasoning:{reasoning_document_id}",
                allow_llm=False,
            ),
            reasoning_context,
        )
        business_projection = self.presentation_projection_engine.safe_project(
            parser=dict(semantic),
            document_family_context=document_family_context,
            enterprise_reasoning=enterprise_reasoning,
            product_intelligence=product_intelligence,
            document_id=reasoning_document_id,
        )
        llama = None
        if run_llama:
            llama = await self.llm_service.structure_receipt(
                raw_text=next_raw_text or "\n".join(next_lines),
                lines=next_lines,
                ocr_blocks=next_blocks,
                parser_json=semantic_parser_json,
                ocr_engine=ocr_engine or source.get("strategy") or "receipt-agent",
                ocr_variants=semantic_ocr_variants,
            )
            llama = self._reconcile_llama_merchant_confidence(llama, semantic)
            llama = self._reconcile_llama_item_candidates(llama)
        score = self._score_attempt(semantic, llama, donut_json)
        retry_plan = self._combined_retry_plan(semantic, llama, donut_json)
        warnings = self._combined_warnings(semantic, llama, donut_json)
        return ReceiptAgentAttempt(
            index=index,
            strategy=str(source.get("strategy") or "receipt_agent_attempt"),
            source=str(source.get("source") or "image"),
            donut=donut_json,
            semantic=semantic,
            llama=llama,
            ocr_fallback=ocr_fallback,
            score=score,
            retry_plan=retry_plan,
            warnings=warnings,
            receipt_document=receipt_document,
            receipt_structure=receipt_structure,
            receipt_classification=receipt_classification,
            document_family_context=document_family_context,
            receipt_grammar=receipt_grammar,
            receipt_constraint_result=receipt_constraint_result,
            product_intelligence=product_intelligence,
            enterprise_knowledge_graph=enterprise_knowledge_graph,
            cross_document_intelligence=cross_document_intelligence,
            enterprise_learning=enterprise_learning,
            enterprise_reasoning=enterprise_reasoning,
            business_projection=business_projection,
        )

    def _build_receipt_document(
        self,
        *,
        image_bytes: bytes,
        lines: list[str],
        ocr_blocks: list[dict[str, Any]],
        ocr_engine: str,
        source_image_id: str,
        source_filename: str,
    ) -> ReceiptDocument | None:
        """Creates request-scoped physical DOM infrastructure without affecting extraction."""
        geometry = self.receipt_geometry_engine.safe_analyze(image_bytes) if image_bytes else None
        if geometry is None:
            return None
        try:
            return self.receipt_dom_builder.build(
                receipt_geometry=geometry,
                ocr_blocks=ocr_blocks,
                ocr_lines=lines,
                source_ocr_engine=ocr_engine,
                source_image_id=source_image_id,
                source_filename=source_filename,
                diagnostics={"sidecar": True, "affectsExtraction": False},
            )
        except Exception:
            return None

    def _use_ocr_first_attempt(self, source: dict[str, Any], run_llama: bool) -> bool:
        if not self.ocr_first_reprocess:
            return False
        return str(source.get("strategy") or "") in {"isolate_receipt_then_ocr", "central_receipt_crop_ocr"}

    def _image_sources(self, image_bytes: bytes) -> list[dict[str, Any]]:
        if not image_bytes:
            return []
        sources: list[dict[str, Any]] = []
        narrow_crop = self._narrow_receipt_crop_variant(image_bytes)
        if narrow_crop:
            sources.append(narrow_crop)
        isolation = self.receipt_image_isolation_service.isolate(image_bytes)
        geometry = self.receipt_geometry_engine.safe_analyze(image_bytes)
        isolation_diagnostics = dict(isolation.diagnostics)
        if geometry is not None:
            isolation_diagnostics["geometry"] = geometry.to_dict()
        if isolation.image_bytes:
            sources.append({
                "source": "isolated_receipt",
                "strategy": "isolate_receipt_then_ocr",
                "imageBytes": isolation.image_bytes,
                "diagnostics": isolation_diagnostics,
            })
        sources.append({"source": "uploaded_image", "strategy": "baseline_document_understanding", "imageBytes": image_bytes, "diagnostics": {}})
        sources.extend(self._opencv_retry_variants(isolation.image_bytes or image_bytes))
        deduped: list[dict[str, Any]] = []
        seen_sizes: set[tuple[str, int]] = set()
        for source in sources:
            key = (source["strategy"], len(source.get("imageBytes") or b""))
            if key in seen_sizes:
                continue
            seen_sizes.add(key)
            deduped.append(source)
        return deduped

    def _narrow_receipt_crop_variant(self, image_bytes: bytes) -> dict[str, Any] | None:
        try:
            import cv2
            import numpy as np
        except Exception:
            return None
        try:
            data = np.frombuffer(image_bytes, dtype=np.uint8)
            image = cv2.imdecode(data, cv2.IMREAD_COLOR)
            if image is None:
                return None
            height, width = image.shape[:2]
            if height < 600 or width < 400:
                return None
            min_width = int(width * 0.16)
            left, right = int(width * 0.38), int(width * 0.75)
            margin = int(width * 0.025)
            left = max(0, left - margin)
            right = min(width, right + margin)
            crop = image[:, left:right]
            if crop.shape[1] < min_width:
                return None
            scale = min(2.4, max(1.2, 1200.0 / max(crop.shape[1], 1)))
            crop = cv2.resize(crop, (int(crop.shape[1] * scale), int(crop.shape[0] * scale)), interpolation=cv2.INTER_CUBIC)
            success, encoded = cv2.imencode(".png", crop)
            if not success:
                return None
            return {
                "source": "narrow_receipt_crop",
                "strategy": "central_receipt_crop_ocr",
                "imageBytes": encoded.tobytes(),
                "diagnostics": {
                    "schemaVersion": "receipt-agent-image-variant-v1",
                    "strategy": "central_receipt_crop_ocr",
                    "crop": {"left": left, "right": right, "width": right - left, "sourceWidth": width, "sourceHeight": height},
                },
            }
        except Exception:
            return None

    def _opencv_retry_variants(self, image_bytes: bytes) -> list[dict[str, Any]]:
        try:
            import cv2
            import numpy as np
        except Exception:
            return []
        try:
            data = np.frombuffer(image_bytes, dtype=np.uint8)
            image = cv2.imdecode(data, cv2.IMREAD_COLOR)
            if image is None:
                return []
            gray = cv2.cvtColor(image, cv2.COLOR_BGR2GRAY)
            variants = []
            high_contrast = cv2.createCLAHE(clipLimit=2.6, tileGridSize=(8, 8)).apply(gray)
            variants.append(("opencv_preprocess_high_contrast", high_contrast))
            background = cv2.medianBlur(gray, 31)
            flattened = cv2.divide(gray, background, scale=255)
            threshold = cv2.adaptiveThreshold(flattened, 255, cv2.ADAPTIVE_THRESH_GAUSSIAN_C, cv2.THRESH_BINARY, 41, 9)
            variants.append(("deskew_and_adaptive_threshold", threshold))
            encoded_variants = []
            for strategy, variant in variants:
                success, encoded = cv2.imencode(".jpg", variant, [int(cv2.IMWRITE_JPEG_QUALITY), 94])
                if success:
                    encoded_variants.append({
                        "source": "opencv_retry_variant",
                        "strategy": strategy,
                        "imageBytes": encoded.tobytes(),
                        "diagnostics": {"schemaVersion": "receipt-agent-image-variant-v1", "strategy": strategy},
                    })
            return encoded_variants
        except Exception:
            return []

    def _semantic_parser_json(self, parser_json: dict[str, Any], donut_json: dict[str, Any]) -> dict[str, Any]:
        if not donut_json.get("available") and not donut_json.get("items"):
            return {**parser_json, "documentUnderstanding": donut_json}
        return {
            **parser_json,
            "company": donut_json.get("merchant", "") or parser_json.get("company", ""),
            "storeName": donut_json.get("merchant", "") or parser_json.get("storeName", ""),
            "date": donut_json.get("date", "") or parser_json.get("date", ""),
            "purchaseDate": donut_json.get("date", "") or parser_json.get("purchaseDate", ""),
            "items": donut_json.get("items", []) or parser_json.get("items", []),
            "subtotal": donut_json.get("subtotal", "") or parser_json.get("subtotal", ""),
            "tax": donut_json.get("tax", "") or parser_json.get("tax", ""),
            "discount": donut_json.get("discount", "") or parser_json.get("discount", ""),
            "totalDiscount": donut_json.get("totalDiscount", "") or parser_json.get("totalDiscount", ""),
            "totalSavings": donut_json.get("totalSavings", "") or parser_json.get("totalSavings", ""),
            "total": donut_json.get("total", "") or parser_json.get("total", ""),
            "logoCandidates": donut_json.get("logoCandidates", []),
            "visualIdentity": donut_json.get("visualIdentity", {}),
            "documentUnderstanding": donut_json,
        }

    def _needs_ocr_fallback(self, donut_json: dict[str, Any], raw_text: str = "", lines: list | None = None, ocr_blocks: list | None = None) -> bool:
        if str(raw_text or "").strip() or any(str(line).strip() for line in (lines or [])) or ocr_blocks:
            return False
        if not donut_json.get("available"):
            return True
        if str(donut_json.get("rawText") or "").strip():
            return False
        return True

    def _prefer_consolidated_receipt_rows(self, semantic: dict[str, Any], donut_json: dict[str, Any]) -> dict[str, Any]:
        if not isinstance(semantic, dict) or not isinstance(donut_json, dict):
            return semantic
        consolidated_items = donut_json.get("items")
        if not isinstance(consolidated_items, list) or not consolidated_items:
            return semantic
        semantic_items = semantic.get("items") if isinstance(semantic.get("items"), list) else []
        reconciliation = donut_json.get("rowConsolidation", {}).get("reconciliation", {})
        target_count = reconciliation.get("itemCountTarget")
        actual_count = reconciliation.get("itemCountActual")
        count_matched = bool(target_count and actual_count == target_count and len(consolidated_items) == target_count)
        arithmetic_matched = bool(reconciliation.get("matched"))
        consolidated_has_discount = bool(donut_json.get("totalDiscount") or donut_json.get("discount") or any(
            isinstance(item, dict) and item.get("discount")
            for item in consolidated_items
        ))
        semantic_has_receipt_level_row = any(
            re.search(r"\b(?:TOTAL|SUBTOTAL|TAX|AMOUNT|VISA|AMEX|AMERICAN\s+EXPRESS|MASTERCARD|DISCOVER|CHANGE|SAVINGS|DISCOUNT)\b", str(item.get("name") or ""), flags=re.IGNORECASE)
            for item in semantic_items
            if isinstance(item, dict)
        )
        materially_better_count = len(consolidated_items) >= max(len(semantic_items) + 3, len(semantic_items) * 2)
        if not (arithmetic_matched or count_matched or consolidated_has_discount or semantic_has_receipt_level_row or materially_better_count):
            return semantic
        semantic["items"] = [
            {
                **item,
                "id": index + 1,
                "confidence": round(float(item.get("confidence", item.get("weight", 0.0)) or 0.0), 3),
            }
            for index, item in enumerate(consolidated_items)
            if isinstance(item, dict)
        ]
        for key in ("subtotal", "tax", "tip", "discount", "totalDiscount", "totalSavings", "total", "cardUsed", "cardLast4", "paymentMethod", "address", "storeAddress", "phone"):
            value = donut_json.get(key)
            if value not in (None, ""):
                semantic[key] = value
        facts = semantic.setdefault("facts", {})
        if isinstance(facts, dict):
            for key in ("subtotal", "tax", "tip", "discount", "totalDiscount", "totalSavings", "total", "cardUsed", "cardLast4", "paymentMethod", "address", "storeAddress", "phone"):
                value = donut_json.get(key)
                if value not in (None, ""):
                    facts[key] = value
        semantic.setdefault("receiptAgentPasses", {})["consolidatedRowsOverride"] = {
            "source": "receipt_row_consolidation",
            "reason": "consolidated_rows_match_receipt_item_count_or_outperform_semantic_items",
            "semanticItemCount": len(semantic_items),
            "consolidatedItemCount": len(semantic["items"]),
            "itemCountTarget": target_count,
        }
        return semantic

    def _merge_ocr_fallback(self, raw_text: str, lines: list, ocr_blocks: list, ocr_result: dict) -> tuple[str, list, list]:
        return (
            raw_text or str(ocr_result.get("rawText") or ""),
            lines or ocr_result.get("rawLines") or [],
            ocr_blocks or ocr_result.get("ocrBlocks") or [],
        )

    def _score_attempt(self, semantic: dict[str, Any], llama: dict[str, Any] | None, donut: dict[str, Any]) -> float:
        candidates = [
            self._confidence_value(semantic.get("confidence")),
            self._confidence_value((llama or {}).get("confidence")),
            self._confidence_value(((llama or {}).get("receiptIntelligence") or {}).get("confidence")),
            self._confidence_value(donut.get("confidence")),
        ]
        score = max(candidates)
        validation = semantic.get("validation") or {}
        if validation.get("valid"):
            score = min(1.0, score + 0.04)
        if validation.get("warnings"):
            score = max(0.0, score - min(0.18, len(validation["warnings"]) * 0.05))
        item_count = len(semantic.get("items") or [])
        target_count = self._expected_item_count(semantic, donut)
        if target_count:
            if item_count == target_count:
                score = min(1.0, score + 0.16)
            elif item_count < max(2, int(target_count * 0.5)):
                score = max(0.0, score - 0.28)
            elif item_count < target_count:
                score = max(0.0, score - 0.12)
        facts = semantic.get("facts") if isinstance(semantic.get("facts"), dict) else {}
        if self._has_amount(facts.get("subtotal") or semantic.get("subtotal")):
            score = min(1.0, score + 0.06)
        if self._has_amount(facts.get("tax") or semantic.get("tax")):
            score = min(1.0, score + 0.03)
        if self._has_amount(facts.get("total") or semantic.get("total")):
            score = min(1.0, score + 0.04)
        return round(score, 3)

    def _has_amount(self, value: Any) -> bool:
        try:
            return float(str(value or "").replace("$", "").replace(",", "").strip()) > 0
        except Exception:
            return False

    def _reconcile_merchant_confidence(self, semantic: dict[str, Any], parser_json: dict[str, Any] | None = None) -> dict[str, Any]:
        if not isinstance(semantic, dict):
            return semantic
        parser_json = parser_json or {}
        current = str(semantic.get("merchant") or semantic.get("storeName") or "").strip()
        trace = semantic.get("merchantConfidenceTrace") if isinstance(semantic.get("merchantConfidenceTrace"), dict) else {}
        raw_ocr = str(trace.get("rawMerchant") or "").strip()
        candidates = self._merchant_candidates(semantic, parser_json, current)
        best = max(candidates, key=lambda item: (item["confidence"], self._merchant_source_priority(item.get("source")))) if candidates else None
        selected = current
        source = "existing_semantic_merchant"
        semantic_confidence = semantic.get("confidence") if isinstance(semantic.get("confidence"), dict) else {}
        confidence = self._confidence_value(trace.get("confidence") or semantic_confidence.get("merchant"))
        override_applied = False
        preserved_raw = False
        if best and best["confidence"] > 0.90:
            selected = best["merchant"]
            source = best["source"]
            confidence = best["confidence"]
            override_applied = selected != current
        elif raw_ocr:
            selected = raw_ocr
            source = "raw_ocr_preserved_uncertain_agent_merchant"
            confidence = max(confidence, best["confidence"] if best else 0.0)
            preserved_raw = selected != current or bool(trace.get("preservedRawOcr"))

        if selected:
            semantic["merchant"] = selected
            semantic["storeName"] = selected
            semantic["company"] = selected
        elif current:
            semantic["merchant"] = current
            semantic["storeName"] = current

        agent_pass = {
            "schemaVersion": "receipt-agent-merchant-confidence-v1",
            "selectedMerchant": selected,
            "previousMerchant": current,
            "rawOcrMerchant": raw_ocr,
            "confidence": round(float(confidence or 0.0), 3),
            "source": source,
            "overrideApplied": override_applied,
            "preservedRawOcr": preserved_raw,
            "overrideThreshold": 0.90,
            "candidates": candidates[:12],
        }
        semantic.setdefault("receiptAgentPasses", {})["merchantConfidence"] = agent_pass
        merged_trace = {
            **trace,
            "merchant": selected,
            "confidence": round(float(confidence or 0.0), 3),
            "source": source,
            "agentMerchantConfidence": agent_pass,
            "preservedRawOcr": preserved_raw or bool(trace.get("preservedRawOcr")),
        }
        semantic["merchantConfidenceTrace"] = merged_trace
        confidence_obj = semantic.get("confidence")
        if isinstance(confidence_obj, dict):
            confidence_obj["merchant"] = round(float(confidence or 0.0), 3)
        return semantic

    def _reconcile_llama_merchant_confidence(self, llama: dict[str, Any] | None, semantic: dict[str, Any]) -> dict[str, Any] | None:
        if not isinstance(llama, dict):
            return llama
        agent_pass = ((semantic.get("receiptAgentPasses") or {}).get("merchantConfidence") or {})
        selected = agent_pass.get("selectedMerchant")
        if selected:
            llama["company"] = selected
            llama["storeName"] = selected
        intelligence = llama.setdefault("receiptIntelligence", {})
        if isinstance(intelligence, dict) and agent_pass:
            intelligence.setdefault("receiptAgentPasses", {})["merchantConfidence"] = agent_pass
            trace = intelligence.setdefault("confidenceTrace", {})
            if isinstance(trace, dict):
                trace["merchant"] = semantic.get("merchantConfidenceTrace") or {}
        return llama

    def _merchant_candidates(self, semantic: dict[str, Any], parser_json: dict[str, Any], current: str) -> list[dict[str, Any]]:
        candidates: list[dict[str, Any]] = []
        text_lines = self._merchant_text_lines(semantic)
        evidence_lines = [*text_lines, *self._merchant_parser_text_lines(parser_json, start_index=len(text_lines))]
        for domain, merchant, line_index in self._domain_merchant_candidates(evidence_lines, parser_json):
            candidates.append({
                "merchant": merchant,
                "confidence": 0.98,
                "source": "domain_name",
                "reasons": [f"domain:{domain}", "domain_priority"],
                "lineIndex": line_index,
                "evidence": domain,
            })
        for candidate in self._return_policy_merchant_candidates(evidence_lines):
            candidates.append(candidate)
        for candidate in self._visual_header_merchant_candidates(semantic):
            candidates.append(candidate)
        trace = semantic.get("merchantConfidenceTrace") if isinstance(semantic.get("merchantConfidenceTrace"), dict) else {}
        selected_candidate = trace.get("selectedCandidate") if isinstance(trace.get("selectedCandidate"), dict) else {}
        trace_merchant = str(selected_candidate.get("merchant") or current or "").strip()
        trace_conf = self._confidence_value(selected_candidate.get("confidence") or trace.get("confidence"))
        if trace_merchant:
            candidates.append({
                "merchant": trace_merchant,
                "confidence": min(0.9, trace_conf),
                "source": "existing_merchant_trace",
                "reasons": ["existing_trace_capped_until_agent_verified"],
                "evidence": trace.get("source", ""),
            })
        return self._dedupe_merchant_candidates(self._merge_fuzzy_domain_visual_candidates(candidates))

    def _merchant_source_priority(self, source: Any) -> int:
        source_text = str(source or "")
        if source_text == "domain_visual_fuzzy_consensus":
            return 4
        if source_text == "domain_name":
            return 3
        if source_text == "return_policy_merchant_clue":
            return 3
        if source_text.startswith("visual_hierarchy"):
            return 2
        return 1

    def _merchant_text_lines(self, semantic: dict[str, Any]) -> list[dict[str, Any]]:
        lines = []
        for index, line in enumerate(semantic.get("reconstructedLines") or []):
            if isinstance(line, dict):
                lines.append({
                    "index": int(line.get("index", index) or index),
                    "text": str(line.get("text") or ""),
                    "bbox": line.get("bbox") if isinstance(line.get("bbox"), dict) else {},
                    "confidence": self._confidence_value(line.get("confidence", 0.0)),
                })
            else:
                lines.append({"index": index, "text": str(line or ""), "bbox": {}, "confidence": 0.72})
        if not lines:
            for index, block in enumerate(semantic.get("semanticBlocks") or []):
                if isinstance(block, dict):
                    for offset, text in enumerate(str(block.get("text") or "").splitlines()):
                        lines.append({"index": index + offset, "text": text, "bbox": {}, "confidence": self._confidence_value(block.get("confidence", 0.0))})
        return [line for line in lines if line["text"].strip()]

    def _merchant_parser_text_lines(self, parser_json: dict[str, Any], start_index: int = 0) -> list[dict[str, Any]]:
        if not isinstance(parser_json, dict):
            return []
        documents: list[dict[str, Any]] = []
        document_understanding = parser_json.get("documentUnderstanding")
        if isinstance(document_understanding, dict):
            documents.append(document_understanding)
            ocr_fallback = document_understanding.get("ocrFallback")
            if isinstance(ocr_fallback, dict):
                documents.append(ocr_fallback)
        for key in ("ocrFallback", "documentUnderstanding"):
            value = parser_json.get(key)
            if isinstance(value, dict) and value not in documents:
                documents.append(value)
        output: list[dict[str, Any]] = []
        seen: set[str] = set()
        for document in documents:
            raw_lines = document.get("rawLines")
            if isinstance(raw_lines, list):
                for text in raw_lines:
                    cleaned = re.sub(r"\s+", " ", str(text or "")).strip()
                    key = cleaned.upper()
                    if cleaned and key not in seen:
                        seen.add(key)
                        output.append({"index": start_index + len(output), "text": cleaned, "bbox": {}, "confidence": 0.68})
            raw_text = str(document.get("rawText") or "")
            if raw_text:
                for text in raw_text.splitlines():
                    cleaned = re.sub(r"\s+", " ", str(text or "")).strip()
                    key = cleaned.upper()
                    if cleaned and key not in seen:
                        seen.add(key)
                        output.append({"index": start_index + len(output), "text": cleaned, "bbox": {}, "confidence": 0.64})
        return output

    def _domain_merchant_candidates(self, lines: list[dict[str, Any]], parser_json: dict[str, Any]) -> list[tuple[str, str, int | None]]:
        found: list[tuple[str, str, int | None]] = []
        sources = [(line["text"], line["index"]) for line in lines[:40]]
        for key in ("domain", "website", "url", "image_url", "imageUrl"):
            if parser_json.get(key):
                sources.append((str(parser_json.get(key)), None))
        for text, line_index in sources:
            normalized_text = re.sub(r"\s*\.\s*", ".", str(text or ""))
            normalized_text = re.sub(r"\bwww\.\s+", "www.", normalized_text, flags=re.IGNORECASE)
            for match in re.finditer(r"\b(?:https?://)?(?:www\.)?([a-zA-Z0-9][a-zA-Z0-9-]{2,35})\.(com|net|org|io|co)\b", normalized_text):
                label = re.sub(r"[-_]+", " ", match.group(1)).strip()
                merchant = self._merchant_from_domain_label(label)
                if merchant:
                    found.append((f"{match.group(1)}.{match.group(2)}", merchant, line_index))
        return found

    def _return_policy_merchant_candidates(self, lines: list[dict[str, Any]]) -> list[dict[str, Any]]:
        output: list[dict[str, Any]] = []
        if not lines:
            return output
        text_values = [str(line.get("text") or "") for line in lines[:140]]
        combined = "\n".join(text_values)
        combined_upper = combined.upper()
        has_policy_context = bool(re.search(r"\b(?:RETURN|REFUND|EXCHANGE|RETURNS?)\b", combined_upper)) and bool(re.search(r"\bPOLIC", combined_upper))
        pharmacy_context = bool(re.search(r"\bPHAR[HMN]?ACY\b|\bPRESCRIPTION\b|\bRX\b", combined_upper))

        if has_policy_context and pharmacy_context:
            for index, text in enumerate(text_values):
                window = " ".join(text_values[max(0, index - 2): index + 3])
                if not re.search(r"\b(?:RETURN|REFUND|EXCHANGE|RETURNS?|POLIC)", window, flags=re.IGNORECASE):
                    continue
                if self._window_contains_cvs_policy_clue(window):
                    output.append({
                        "merchant": "CVS",
                        "confidence": 0.97,
                        "source": "return_policy_merchant_clue",
                        "reasons": ["return_policy_text", "pharmacy_context", "ocr_acronym_recovery"],
                        "lineIndex": lines[index].get("index"),
                        "evidence": window[:180],
                    })
                    break

        for index, text in enumerate(text_values):
            window = " ".join(text_values[max(0, index - 1): index + 2])
            for raw_merchant in self._extract_policy_merchants_from_text(window):
                merchant = self._normalize_policy_merchant(raw_merchant)
                if not merchant:
                    continue
                output.append({
                    "merchant": merchant,
                    "confidence": 0.93,
                    "source": "return_policy_merchant_clue",
                    "reasons": ["merchant_named_in_return_policy"],
                    "lineIndex": lines[index].get("index"),
                    "evidence": window[:180],
                })
        return output

    def _window_contains_cvs_policy_clue(self, text: str) -> bool:
        for token in re.findall(r"\b[A-Za-z0-9]{2,5}\b", str(text or "")):
            normalized = token.upper().replace("5", "S").replace("0", "O").replace("1", "I").replace("U", "V")
            if normalized == "CVS":
                return True
        compact = re.sub(r"[^A-Z0-9]+", "", str(text or "").upper())
        return "CVSRETURN" in compact or "CVSPOLIC" in compact

    def _extract_policy_merchants_from_text(self, text: str) -> list[str]:
        normalized = re.sub(r"\s+", " ", str(text or "")).strip()
        patterns = [
            r"\b(?P<merchant>[A-Za-z0-9&'./# -]{2,70}?)\s+(?:RETURN|RETURNS|REFUND|EXCHANGE)\s+POLIC\w*",
            r"\b(?:RETURN|RETURNS|REFUND|EXCHANGE)\s+POLIC\w*(?:\s+(?:AT|FOR|FROM))\s+(?P<merchant>[A-Za-z0-9&'./# -]{2,70})",
        ]
        found: list[str] = []
        for pattern in patterns:
            for match in re.finditer(pattern, normalized, flags=re.IGNORECASE):
                found.append(match.group("merchant"))
        return found

    def _normalize_policy_merchant(self, value: str) -> str:
        cleaned = re.sub(r"[^A-Za-z0-9&'./# -]+", " ", str(value or ""))
        cleaned = re.sub(r"\s+", " ", cleaned).strip(" -_:;,.")
        if not cleaned:
            return ""
        cleaned = re.sub(
            r"^(?:VISIT|SEE|VIEW|READ|OUR|THE|A|AN|YOUR|THIS|STORE|PLEASE|SUBJECT|WITH|RECEIPT|CUSTOMER|RETURNS?|ACCEPTED|UNDER)\s+",
            "",
            cleaned,
            flags=re.IGNORECASE,
        ).strip(" -_:;,.")
        cleaned = re.sub(r"^(?:ACCEPTED|UNDER)\s+", "", cleaned, flags=re.IGNORECASE).strip(" -_:;,.")
        cleaned = re.sub(
            r"\s+(?:VISIT|SEE|VIEW|READ|OUR|THE|A|AN|YOUR|THIS|STORE|PLEASE|SUBJECT|WITH|RECEIPT|CUSTOMER)$",
            "",
            cleaned,
            flags=re.IGNORECASE,
        ).strip(" -_:;,.")
        tokens = re.findall(r"[A-Za-z0-9&'./#-]+", cleaned)
        if not tokens:
            return ""
        if len(tokens) > 4:
            tokens = tokens[-4:]
        upper_tokens = [token.upper().replace("5", "S").replace("0", "O").replace("1", "I").replace("U", "V") for token in tokens]
        if "CVS" in upper_tokens:
            return "CVS"
        generic = {
            "RETURN", "RETURNS", "REFUND", "EXCHANGE", "POLICY", "POLICU", "POLICIES",
            "SUBJECT", "RECEIPT", "WITH", "THRU", "THROUGH", "DATE", "ITEM", "ITEMS",
            "ACCEPTED", "UNDER",
        }
        tokens = [token for token in tokens if token.upper() not in generic]
        if not tokens:
            return ""
        alpha_count = sum(1 for token in tokens if re.search(r"[A-Za-z]", token))
        if alpha_count == 0:
            return ""
        candidate = " ".join(tokens)
        if len(re.sub(r"[^A-Za-z]", "", candidate)) < 3:
            return ""
        if re.fullmatch(r"(?:STORE|STR|PHARMACY|ROAD|NORTH|SOUTH|EAST|WEST)(?:\s+#?\d+)?", candidate, flags=re.IGNORECASE):
            return ""
        return self._title_merchant(candidate)

    def _merchant_from_domain_label(self, label: str) -> str:
        cleaned = re.sub(r"(?:FEEDBACK|SURVEY|REWARDS|REWARD|RECEIPTS?)$", "", str(label or ""), flags=re.IGNORECASE)
        cleaned = re.sub(r"[^A-Za-z0-9 ]+", " ", cleaned)
        cleaned = re.sub(r"\s+", " ", cleaned).strip()
        if not cleaned or cleaned.upper() in {"WWW", "EMAIL", "RECEIPT", "RECEIPTS"}:
            return ""
        return cleaned.title()

    def _visual_header_merchant_candidates(self, semantic: dict[str, Any]) -> list[dict[str, Any]]:
        lines = self._merchant_text_lines(semantic)
        visual_by_index = self._visual_hierarchy_by_line(semantic)
        if not lines:
            return []
        page_width = max(
            (float((line.get("bbox") or {}).get("x", 0) or 0) + float((line.get("bbox") or {}).get("width", 0) or 0))
            for line in lines
        ) or 1.0
        output = []
        for position, line in enumerate(lines[:10]):
            text = line["text"].strip()
            if not self._looks_like_merchant_header_text(text):
                continue
            visual = visual_by_index.get(line["index"], {})
            bbox = line.get("bbox") or {}
            width = float(bbox.get("width", 0) or 0)
            x = float(bbox.get("x", 0) or 0)
            center = x + width / 2
            centered_delta = abs(center - (page_width / 2)) / max(page_width / 2, 1)
            centered = width > 0 and centered_delta <= 0.28
            visual_importance = self._confidence_value(visual.get("visualImportance", 0.0))
            if not visual_importance:
                visual_importance = min(0.9, max(0.35, line.get("confidence", 0.0)))
            score = 0.42
            reasons = []
            if position <= 2:
                score += 0.18
                reasons.append("top_header")
            elif position <= 5:
                score += 0.1
                reasons.append("upper_header")
            if centered:
                score += 0.16
                reasons.append("centered_header_text")
            score += min(0.18, visual_importance * 0.18)
            reasons.append("visual_hierarchy_scored")
            if self._has_business_hint(text):
                score += 0.08
                reasons.append("merchant_semantic_hint")
            quality = self._merchant_header_quality(text)
            if quality < 0.45:
                continue
            score += min(0.08, quality * 0.08)
            if self._looks_like_legal_or_disclaimer(text):
                score -= 0.42
                reasons.append("legal_disclaimer_penalty")
            if line.get("confidence"):
                score += min(0.08, float(line["confidence"]) * 0.08)
            if not self._has_business_hint(text) and quality < 0.72:
                score = min(score, 0.89)
            confidence = max(0.0, min(0.96, score))
            if confidence >= 0.62:
                merchant = self._title_merchant(text)
                if not re.search(r"[A-Za-z]{3,}", merchant):
                    continue
                output.append({
                    "merchant": merchant,
                    "confidence": round(confidence, 3),
                    "source": "visual_hierarchy_centered_header",
                    "reasons": reasons,
                    "lineIndex": line["index"],
                    "evidence": {
                        "text": text,
                        "bbox": bbox,
                        "centered": centered,
                        "visualImportance": round(visual_importance, 3),
                        "zone": visual.get("zone", ""),
                    },
                })
        return output

    def _visual_hierarchy_by_line(self, semantic: dict[str, Any]) -> dict[int, dict[str, Any]]:
        section = semantic.get("sectionExtraction") if isinstance(semantic.get("sectionExtraction"), dict) else {}
        visual = section.get("visualHierarchy") if isinstance(section.get("visualHierarchy"), dict) else {}
        by_index = {}
        for row in visual.get("lines") or []:
            if isinstance(row, dict) and isinstance(row.get("lineIndex"), int):
                by_index[int(row["lineIndex"])] = row
        return by_index

    def _looks_like_merchant_header_text(self, text: str) -> bool:
        upper = str(text or "").upper()
        letters = re.sub(r"[^A-Z]", "", upper)
        digits = re.sub(r"\D", "", upper)
        if re.search(r"\b(?:STORE|STR|PHARMACY|TEL|PHONE)\b", upper) and len(digits) > max(3, len(letters)):
            return False
        return (
            bool(re.search(r"[A-Z]{3,}", upper))
            and not re.search(r"\d{1,7}(?:[.,]\d{2})", upper)
            and not re.search(r"\b(?:SUBTOTAL|TOTAL|TAX|BALANCE|VISA|MASTERCARD|CREDIT|DEBIT|QUANTITY|PRICE)\b", upper)
            and not re.fullmatch(r"[A-Z]{3,4}", upper)
        )

    def _merchant_header_quality(self, text: str) -> float:
        cleaned = re.sub(r"[^A-Za-z0-9 &'#.-]+", " ", str(text or ""))
        tokens = re.findall(r"[A-Za-z][A-Za-z'&.-]*|\d+", cleaned)
        if not tokens:
            return 0.0
        alpha_tokens = [token for token in tokens if re.search(r"[A-Za-z]", token)]
        if not alpha_tokens:
            return 0.0
        meaningful = [token for token in alpha_tokens if len(re.sub(r"[^A-Za-z]", "", token)) >= 3]
        short_noise = [token for token in alpha_tokens if len(re.sub(r"[^A-Za-z]", "", token)) <= 2]
        digit_tokens = [token for token in tokens if token.isdigit()]
        quality = 0.38
        quality += min(0.32, len(meaningful) * 0.12)
        if self._has_business_hint(text):
            quality += 0.22
        if len(meaningful) >= 1 and not digit_tokens:
            quality += 0.12
        if short_noise:
            quality -= min(0.28, len(short_noise) * 0.09)
        if digit_tokens and not self._has_business_hint(text):
            quality -= min(0.22, len(digit_tokens) * 0.08)
        if len(alpha_tokens) >= 3 and len(meaningful) / max(len(alpha_tokens), 1) < 0.5:
            quality -= 0.18
        return max(0.0, min(1.0, quality))

    def _has_business_hint(self, text: str) -> bool:
        return bool(re.search(r"\b(?:MARKET|MART|STORE|STORES|CENTER|CENTERS|PHARMACY|KITCHEN|RESTAURANT|CAFE|LLC|INC|CO)\b", str(text or ""), flags=re.IGNORECASE))

    def _looks_like_legal_or_disclaimer(self, text: str) -> bool:
        upper = re.sub(r"[^A-Z ]+", " ", str(text or "").upper())
        upper = re.sub(r"\s+", " ", upper).strip()
        return bool(re.search(
            r"\b(?:NO PURCHASE|VOID WHERE PROHIBITED|PROHIBITED|OFFICIAL RULES|SWEEPSTAKES|SURVEY|FEEDBACK|RETURN POLICY|TERMS|CONDITIONS|RECEIPT REQUIRED)\b",
            upper,
        ))

    def _title_merchant(self, text: str) -> str:
        cleaned = re.sub(r"\s+", " ", str(text or "").strip())
        if re.search(r"(?:\(\d{3}\)|\b\d{3})[-\s)]+\d{3}[-\s]+\d{4}\b|\bSTORE\b|#\d+", cleaned, flags=re.IGNORECASE):
            cleaned = re.sub(r"(?:\(\d{3}\)|\b\d{3})[-\s)]+\d{3}[-\s]+\d{4}\b", " ", cleaned)
            cleaned = re.sub(r"\b(?:STORE|STORES?|SHOP|LOCATION|LOC|NO|NUMBER|NUM|TEL|PHONE)\b\.?\s*#?\s*\d*", " ", cleaned, flags=re.IGNORECASE)
            cleaned = re.sub(r"\b#?\d{2,}\b", " ", cleaned)
            tokens = [token for token in re.findall(r"[A-Za-z][A-Za-z']*", cleaned) if len(token) > 2]
            if tokens:
                cleaned = " ".join(tokens[:3])
            cleaned = re.sub(r"\s+", " ", cleaned).strip()
        if cleaned.isupper():
            return cleaned.title()
        return cleaned

    def _merge_fuzzy_domain_visual_candidates(self, candidates: list[dict[str, Any]]) -> list[dict[str, Any]]:
        merged = list(candidates)
        domain_candidates = [candidate for candidate in candidates if candidate.get("source") == "domain_name"]
        visual_candidates = [candidate for candidate in candidates if str(candidate.get("source") or "").startswith("visual_hierarchy")]
        for domain in domain_candidates:
            domain_key = self._merchant_similarity_key(domain.get("merchant"))
            if not domain_key:
                continue
            for visual in visual_candidates:
                visual_key = self._merchant_similarity_key(visual.get("merchant"))
                if not visual_key:
                    continue
                if self._edit_distance(domain_key, visual_key) <= max(1, round(max(len(domain_key), len(visual_key)) * 0.18)):
                    merged.append({
                        "merchant": visual.get("merchant"),
                        "confidence": round(max(float(domain.get("confidence", 0.0) or 0.0), float(visual.get("confidence", 0.0) or 0.0)), 3),
                        "source": "domain_visual_fuzzy_consensus",
                        "reasons": [
                            "domain_priority",
                            "visual_hierarchy_scored",
                            "fuzzy_domain_visual_consensus",
                            *list(domain.get("reasons") or [])[:2],
                            *list(visual.get("reasons") or [])[:2],
                        ],
                        "lineIndex": visual.get("lineIndex", domain.get("lineIndex")),
                        "evidence": {
                            "domainMerchant": domain.get("merchant"),
                            "visualMerchant": visual.get("merchant"),
                            "domainEvidence": domain.get("evidence"),
                            "visualEvidence": visual.get("evidence"),
                        },
                    })
        return merged

    def _merchant_similarity_key(self, value: Any) -> str:
        return re.sub(r"[^A-Z0-9]+", "", str(value or "").upper())

    def _edit_distance(self, left: str, right: str) -> int:
        if left == right:
            return 0
        if not left:
            return len(right)
        if not right:
            return len(left)
        previous = list(range(len(right) + 1))
        for i, left_char in enumerate(left, start=1):
            current = [i]
            for j, right_char in enumerate(right, start=1):
                current.append(min(
                    previous[j] + 1,
                    current[j - 1] + 1,
                    previous[j - 1] + (0 if left_char == right_char else 1),
                ))
            previous = current
        return previous[-1]

    def _dedupe_merchant_candidates(self, candidates: list[dict[str, Any]]) -> list[dict[str, Any]]:
        best_by_key: dict[str, dict[str, Any]] = {}
        for candidate in candidates:
            merchant = str(candidate.get("merchant") or "").strip()
            if not merchant:
                continue
            key = re.sub(r"[^A-Z0-9]+", "", merchant.upper())
            existing = best_by_key.get(key)
            if not existing or float(candidate.get("confidence", 0.0) or 0.0) > float(existing.get("confidence", 0.0) or 0.0):
                best_by_key[key] = candidate
        return sorted(best_by_key.values(), key=lambda item: item["confidence"], reverse=True)

    def _reconcile_semantic_item_candidates(self, semantic: dict[str, Any]) -> dict[str, Any]:
        if not isinstance(semantic, dict):
            return semantic
        items = semantic.get("items")
        if not isinstance(items, list) or len(items) <= 1:
            return semantic
        facts = semantic.get("facts") if isinstance(semantic.get("facts"), dict) else {}
        target = self._select_reconciliation_target(semantic, facts)
        if not target:
            return semantic
        expected_count = self._expected_item_count(semantic)
        reconciliation = self._select_financially_valid_items(
            items=items,
            target_cents=target["amountCents"],
            target_field=target["field"],
            expected_count=expected_count,
        )
        if not reconciliation.get("applied"):
            semantic.setdefault("receiptAgentPasses", {})["pass3CandidateSelection"] = reconciliation
            return semantic
        selected_items = reconciliation["selectedItems"]
        semantic["items"] = [
            {
                **item,
                "id": index + 1,
                "confidence": round(float(item.get("confidence", item.get("weight", 0.0)) or 0.0), 3),
            }
            for index, item in enumerate(selected_items)
        ]
        validation = self.llm_service.receipt_intelligence.validator.validate(semantic["items"], facts, {
            "subtotal": facts.get("subtotal", ""),
            "tax": facts.get("tax", ""),
            "tip": facts.get("tip", ""),
            "total": facts.get("total", ""),
        })
        semantic["validation"] = validation
        semantic["warnings"] = validation.get("warnings", [])
        semantic.setdefault("receiptAgentPasses", {})["pass3CandidateSelection"] = reconciliation
        section_extraction = semantic.get("sectionExtraction")
        if isinstance(section_extraction, dict):
            section_extraction["agentFinancialReconciliation"] = reconciliation
        return semantic

    def _reconcile_llama_item_candidates(self, llama: dict[str, Any] | None) -> dict[str, Any] | None:
        if not isinstance(llama, dict):
            return llama
        semantic_like = {
            "items": llama.get("items") or [],
            "facts": {
                "subtotal": llama.get("subtotal") or llama.get("subTotal") or "",
                "tax": llama.get("tax") or "",
                "tip": llama.get("tip") or "",
                "total": llama.get("total") or "",
            },
            "receiptIntelligence": llama.get("receiptIntelligence") or {},
        }
        reconciled = self._reconcile_semantic_item_candidates(semantic_like)
        reconciliation = (reconciled.get("receiptAgentPasses") or {}).get("pass3CandidateSelection")
        if reconciliation:
            llama["items"] = reconciled.get("items", llama.get("items", []))
            intelligence = llama.setdefault("receiptIntelligence", {})
            if isinstance(intelligence, dict):
                intelligence.setdefault("receiptAgentPasses", {})["pass3CandidateSelection"] = reconciliation
                if reconciled.get("validation"):
                    intelligence["validation"] = reconciled["validation"]
                    intelligence["warnings"] = reconciled["validation"].get("warnings", [])
        return llama

    def _select_reconciliation_target(self, semantic: dict[str, Any], facts: dict[str, Any]) -> dict[str, Any] | None:
        total_cents = self._amount_cents(facts.get("total") or semantic.get("total"))
        subtotal_cents = self._amount_cents(facts.get("subtotal") or facts.get("subTotal") or semantic.get("subtotal") or semantic.get("subTotal"))
        tax_cents = self._amount_cents(facts.get("tax") or semantic.get("tax"))
        tip_cents = self._amount_cents(facts.get("tip") or semantic.get("tip"))
        if subtotal_cents and total_cents and (tax_cents or tip_cents) and subtotal_cents <= total_cents:
            return {"field": "subtotal", "amountCents": subtotal_cents}
        if total_cents:
            return {"field": "total", "amountCents": total_cents}
        if subtotal_cents:
            return {"field": "subtotal", "amountCents": subtotal_cents}
        return None

    def _expected_item_count(self, semantic: dict[str, Any], donut: dict[str, Any] | None = None) -> int | None:
        donut = donut or {}
        donut_target = ((donut.get("rowConsolidation") or {}).get("reconciliation") or {}).get("itemCountTarget")
        parsed_donut_target = self._positive_int(donut_target)
        if parsed_donut_target:
            return parsed_donut_target
        section = semantic.get("sectionExtraction") if isinstance(semantic.get("sectionExtraction"), dict) else {}
        financial = section.get("financialReconciliation") if isinstance(section.get("financialReconciliation"), dict) else {}
        for value in (
            financial.get("expectedItemCount"),
            semantic.get("itemCount"),
            (semantic.get("facts") or {}).get("itemCount") if isinstance(semantic.get("facts"), dict) else None,
        ):
            parsed = self._positive_int(value)
            if parsed:
                return parsed
        text_sources: list[str] = []
        for line in semantic.get("reconstructedLines") or []:
            if isinstance(line, dict):
                text_sources.append(str(line.get("text") or ""))
            else:
                text_sources.append(str(line or ""))
        for block in semantic.get("semanticBlocks") or []:
            if isinstance(block, dict):
                text_sources.append(str(block.get("text") or ""))
        raw = "\n".join(text_sources)
        patterns = (
            r"(?:total\s+)?(?:number\s+of\s+)?items\s+sold\s*[=:]?\s*(\d{1,3})",
            r"\bitem\s+count\s*[=:]?\s*(\d{1,3})",
            r"\bsold\s+items?\s*[=:]?\s*(\d{1,3})",
        )
        for pattern in patterns:
            match = re.search(pattern, raw, flags=re.IGNORECASE)
            if match:
                parsed = self._positive_int(match.group(1))
                if parsed:
                    return parsed
        return None

    def _select_financially_valid_items(
        self,
        *,
        items: list[dict[str, Any]],
        target_cents: int,
        target_field: str,
        expected_count: int | None,
    ) -> dict[str, Any]:
        candidates = []
        rejected = []
        seen = set()
        for index, item in enumerate(items):
            candidate = self._item_candidate(item, index, target_cents)
            if candidate["hardReject"]:
                rejected.append(candidate["diagnostic"])
                continue
            key = (candidate["canonicalName"], candidate["amountCents"], candidate["qty"])
            if key in seen:
                diagnostic = candidate["diagnostic"]
                diagnostic["reasons"] = [*diagnostic["reasons"], "duplicate_candidate"]
                rejected.append(diagnostic)
                continue
            seen.add(key)
            candidates.append(candidate)
        if not candidates:
            return {
                "schemaVersion": "receipt-agent-pass3-v1",
                "applied": False,
                "reason": "no_valid_item_candidates",
                "targetField": target_field,
                "targetAmount": self._format_cents(target_cents),
                "expectedItemCount": expected_count,
                "rejectedCandidates": rejected[:80],
            }

        selected = self._best_item_subset(candidates, target_cents, expected_count)
        if not selected:
            selected = self._best_near_subset(candidates, target_cents, expected_count)
        selected_indexes = {candidate["index"] for candidate in selected}
        selected = sorted(selected, key=lambda candidate: candidate["index"])
        original_count = len(items)
        selected_sum = sum(candidate["amountCents"] for candidate in selected)
        rejected.extend(candidate["diagnostic"] | {"reasons": [*candidate["diagnostic"]["reasons"], "not_in_best_financial_subset"]} for candidate in candidates if candidate["index"] not in selected_indexes)
        applied = bool(selected) and (len(selected) < original_count or abs(selected_sum - target_cents) <= 1)
        return {
            "schemaVersion": "receipt-agent-pass3-v1",
            "applied": applied,
            "strategy": "constraint_based_financial_reconciliation",
            "targetField": target_field,
            "targetAmount": self._format_cents(target_cents),
            "targetCents": target_cents,
            "expectedItemCount": expected_count,
            "originalCandidateCount": original_count,
            "filteredCandidateCount": len(candidates),
            "selectedCount": len(selected),
            "selectedSum": self._format_cents(selected_sum),
            "selectedDelta": self._format_cents(abs(selected_sum - target_cents)),
            "score": round(self._subset_score(selected, target_cents, expected_count, len(candidates)), 3),
            "weights": {
                "arithmeticConsistency": 0.45,
                "semanticConfidence": 0.25,
                "itemCountMatch": 0.15,
                "minimalRows": 0.1,
                "nonItemPenalty": 0.05,
            },
            "selectedDiagnostics": [candidate["diagnostic"] for candidate in selected],
            "rejectedCandidates": rejected[:80],
            "selectedItems": [candidate["item"] for candidate in selected],
        }

    def _best_item_subset(self, candidates: list[dict[str, Any]], target_cents: int, expected_count: int | None) -> list[dict[str, Any]]:
        max_candidates = sorted(candidates, key=lambda item: item["candidateScore"], reverse=True)[:18]
        count_limits = [expected_count] if expected_count else list(range(1, min(8, len(max_candidates)) + 1))
        best: list[dict[str, Any]] = []
        best_score = -1.0
        for limit in count_limits:
            if not limit or limit > len(max_candidates):
                continue
            result = self._exhaustive_subset(max_candidates, target_cents, expected_count, limit, exact=True)
            if result:
                score = self._subset_score(result, target_cents, expected_count, len(max_candidates))
                if score > best_score:
                    best = result
                    best_score = score
        return best

    def _best_near_subset(self, candidates: list[dict[str, Any]], target_cents: int, expected_count: int | None) -> list[dict[str, Any]]:
        max_candidates = sorted(candidates, key=lambda item: item["candidateScore"], reverse=True)[:18]
        limits = [expected_count] if expected_count else list(range(1, min(8, len(max_candidates)) + 1))
        best: list[dict[str, Any]] = []
        best_score = -1.0
        for limit in limits:
            if not limit or limit > len(max_candidates):
                continue
            result = self._exhaustive_subset(max_candidates, target_cents, expected_count, limit, exact=False)
            if result:
                score = self._subset_score(result, target_cents, expected_count, len(max_candidates))
                if score > best_score:
                    best = result
                    best_score = score
        return best

    def _exhaustive_subset(
        self,
        candidates: list[dict[str, Any]],
        target_cents: int,
        expected_count: int | None,
        limit: int,
        *,
        exact: bool,
    ) -> list[dict[str, Any]]:
        best: list[dict[str, Any]] = []
        best_score = -1.0

        def walk(start: int, current: list[dict[str, Any]], current_sum: int) -> None:
            nonlocal best, best_score
            if len(current) == limit:
                delta = abs(current_sum - target_cents)
                if exact and delta > 1:
                    return
                if not exact and delta > max(100, round(target_cents * 0.04)):
                    return
                score = self._subset_score(current, target_cents, expected_count, len(candidates))
                if score > best_score:
                    best = list(current)
                    best_score = score
                return
            if current_sum > target_cents + max(100, round(target_cents * 0.04)):
                return
            remaining_needed = limit - len(current)
            for index in range(start, len(candidates) - remaining_needed + 1):
                candidate = candidates[index]
                walk(index + 1, [*current, candidate], current_sum + candidate["amountCents"])

        walk(0, [], 0)
        return best

    def _subset_score(self, subset: list[dict[str, Any]], target_cents: int, expected_count: int | None, candidate_count: int) -> float:
        if not subset:
            return 0.0
        total = sum(candidate["amountCents"] for candidate in subset)
        delta = abs(total - target_cents)
        arithmetic = max(0.0, 1.0 - (delta / max(target_cents, 1)))
        semantic = sum(candidate["candidateScore"] for candidate in subset) / max(len(subset), 1)
        if expected_count:
            count_match = 1.0 if len(subset) == expected_count else max(0.0, 1.0 - abs(len(subset) - expected_count) / max(expected_count, 1))
        else:
            count_match = 1.0
        minimal = max(0.0, 1.0 - ((len(subset) - 1) / max(candidate_count, 1)))
        non_item_penalty = sum(candidate["nonItemPenalty"] for candidate in subset) / max(len(subset), 1)
        return (
            arithmetic * 0.45
            + semantic * 0.25
            + count_match * 0.15
            + minimal * 0.1
            + (1.0 - non_item_penalty) * 0.05
        )

    def _item_candidate(self, item: dict[str, Any], index: int, target_cents: int) -> dict[str, Any]:
        name = str(item.get("name") or item.get("description") or "").strip()
        amount_cents = self._amount_cents(item.get("amount") or item.get("price"))
        qty = str(item.get("qty") or item.get("count") or "1").strip() or "1"
        canonical = re.sub(r"[^A-Z0-9 ]+", " ", name.upper())
        canonical = re.sub(r"\s+", " ", canonical).strip()
        reasons = []
        non_item_penalty = 0.0
        if not name:
            reasons.append("missing_item_name")
        if not amount_cents or amount_cents <= 0:
            reasons.append("missing_item_amount")
        if self._looks_like_non_item_row(name):
            reasons.append("totals_payment_or_footer_row")
            non_item_penalty = 1.0
        if target_cents and amount_cents > target_cents:
            reasons.append("item_amount_exceeds_receipt_target")
        if re.fullmatch(r"[\d\s#*/-]+", name):
            reasons.append("numeric_or_code_only_name")
        confidence = self._confidence_value(item.get("confidence", item.get("weight", 0.62)))
        length_score = min(1.0, max(0.2, len(canonical) / 18.0))
        candidate_score = max(0.0, min(1.0, (confidence * 0.72) + (length_score * 0.18) + ((1.0 - non_item_penalty) * 0.1)))
        hard_reject = bool({"missing_item_name", "missing_item_amount", "totals_payment_or_footer_row", "item_amount_exceeds_receipt_target", "numeric_or_code_only_name"} & set(reasons))
        diagnostic = {
            "index": index,
            "name": name,
            "amount": self._format_cents(amount_cents),
            "amountCents": amount_cents,
            "qty": qty,
            "confidence": round(confidence, 3),
            "candidateScore": round(candidate_score, 3),
            "reasons": reasons,
        }
        return {
            "index": index,
            "item": item,
            "name": name,
            "canonicalName": canonical,
            "amountCents": amount_cents,
            "qty": qty,
            "candidateScore": candidate_score,
            "nonItemPenalty": non_item_penalty,
            "hardReject": hard_reject,
            "diagnostic": diagnostic,
        }

    def _looks_like_non_item_row(self, name: str) -> bool:
        upper = re.sub(r"[^A-Z0-9 ]+", " ", str(name or "").upper())
        upper = re.sub(r"\s+", " ", upper).strip()
        if not upper:
            return True
        non_item_terms = (
            "SUBTOTAL", "SUB TOTAL", "TOTAL", "TAX", "TIP", "BALANCE", "BALANCE DUE",
            "CHANGE", "PAYMENT", "VISA", "MASTERCARD", "AMEX", "DISCOVER", "CASH",
            "CREDIT", "DEBIT", "APPROVED", "AUTH", "AID", "TERMINAL", "TRANSACTION",
            "USD", "THANK", "SURVEY", "FEEDBACK", "SAVINGS", "ITEM COUNT", "ITEMS SOLD",
            "NUMBER OF ITEMS", "TOTAL NUMBER",
        )
        return any(term in upper for term in non_item_terms)

    def _amount_cents(self, value: Any) -> int:
        text = str(value or "").replace(",", "").replace("$", "").strip()
        match = re.search(r"-?\d{1,7}(?:\.\d{1,2})?", text)
        if not match:
            return 0
        try:
            return int(round(float(match.group(0)) * 100))
        except Exception:
            return 0

    def _format_cents(self, cents: int) -> str:
        return f"{max(0, int(cents)) / 100:.2f}"

    def _positive_int(self, value: Any) -> int | None:
        try:
            parsed = int(str(value).strip())
        except Exception:
            return None
        return parsed if parsed > 0 else None

    def _confidence_value(self, value: Any) -> float:
        if isinstance(value, dict):
            value = value.get("overall")
        try:
            return max(0.0, min(1.0, float(value or 0.0)))
        except Exception:
            return 0.0

    def _combined_retry_plan(self, semantic: dict[str, Any], llama: dict[str, Any] | None, donut: dict[str, Any]) -> list[dict[str, Any]]:
        plans = []
        plans.extend(semantic.get("retryPlan") or [])
        plans.extend(((llama or {}).get("receiptIntelligence") or {}).get("retryPlan") or [])
        plans.extend(((donut.get("rowConsolidation") or {}).get("retryPlan") or []))
        return self._dedupe_dicts(plans)[:8]

    def _combined_warnings(self, semantic: dict[str, Any], llama: dict[str, Any] | None, donut: dict[str, Any]) -> list[str]:
        warnings: list[str] = []
        warnings.extend(str(item) for item in (semantic.get("warnings") or []))
        warnings.extend(str(item) for item in (((llama or {}).get("receiptIntelligence") or {}).get("warnings") or []))
        warnings.extend(str(item) for item in (((donut.get("rowConsolidation") or {}).get("reconciliation") or {}).get("warnings") or []))
        return list(dict.fromkeys(warnings))[:10]

    def _dedupe_dicts(self, values: list[dict[str, Any]]) -> list[dict[str, Any]]:
        output = []
        seen = set()
        for value in values:
            key = tuple(sorted((str(k), str(v)) for k, v in value.items()))
            if key in seen:
                continue
            seen.add(key)
            output.append(value)
        return output

    def _attempt_is_good_enough(self, attempt: ReceiptAgentAttempt) -> bool:
        validation = attempt.semantic.get("validation") or {}
        return attempt.score >= self.accept_confidence and validation.get("valid") and not attempt.retry_plan

    def _build_agent_summary(
        self,
        *,
        attempts: list[ReceiptAgentAttempt],
        selected: ReceiptAgentAttempt,
        parser_json: dict[str, Any],
        isolation_diagnostics: list[dict[str, Any]],
        document_review: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        review_task = ((document_review or {}).get("humanReview") or self._human_review_task(selected))
        return {
            "schemaVersion": "receipt-agent-v1",
            "mode": "bounded_autonomous_receipt_processing",
            "status": "needs_human_review" if review_task.get("required") else "accepted",
            "selectedAttempt": selected.index,
            "attemptCount": len(attempts),
            "confidence": round(selected.score, 3),
            "autonomousActions": self._autonomous_actions(attempts),
            "attempts": [attempt.summary() for attempt in attempts],
            "humanReview": review_task,
            "memory": self._memory_summary(selected, parser_json),
            "postScanTasks": self._post_scan_tasks(selected),
            "isolationDiagnostics": isolation_diagnostics[:3],
        }

    def _autonomous_actions(self, attempts: list[ReceiptAgentAttempt]) -> list[dict[str, Any]]:
        actions = []
        for attempt in attempts:
            actions.append({
                "stage": "document_understanding",
                "strategy": attempt.strategy,
                "source": attempt.source,
                "score": round(attempt.score, 3),
                "selected": attempt.score == max(item.score for item in attempts),
            })
            if attempt.ocr_fallback:
                actions.append({
                    "stage": "ocr",
                    "strategy": "tesseract_cross_check",
                    "source": attempt.source,
                    "available": bool(attempt.ocr_fallback.get("available")),
                })
        return actions

    def _human_review_task(self, attempt: ReceiptAgentAttempt) -> dict[str, Any]:
        semantic = attempt.semantic or {}
        validation = semantic.get("validation") or {}
        confidence = attempt.score
        reasons: list[dict[str, Any]] = []
        if confidence < self.review_confidence:
            reasons.append({"field": "receipt", "reason": "low_confidence", "severity": "medium", "detail": f"Agent confidence {round(confidence * 100)}%.", "action": "Compare extracted merchant, date, items, and total against the receipt image."})
        for warning in validation.get("warnings") or []:
            reasons.append({"field": "totals", "reason": str(warning), "severity": "critical", "detail": "Receipt arithmetic does not reconcile.", "action": "Verify subtotal, tax, tip, total, and item amounts before processing."})
        merchant_confidence = self._merchant_review_confidence(semantic)
        if not (semantic.get("merchant") or semantic.get("storeName")):
            reasons.append({"field": "merchant", "reason": "missing_merchant", "severity": "high", "detail": "Merchant was not confidently extracted.", "action": "Enter or correct the merchant name from the receipt header."})
        elif merchant_confidence and merchant_confidence < 0.9:
            reasons.append({"field": "merchant", "reason": "low_confidence_merchant", "severity": "high", "detail": f"Merchant confidence is {round(merchant_confidence * 100)}%.", "action": "Confirm the merchant name against the receipt header or domain."})
        item_count_reason = self._item_count_review_reason(semantic)
        if item_count_reason:
            reasons.append(item_count_reason)
        image_quality_reason = self._image_quality_review_reason(semantic)
        if image_quality_reason:
            reasons.append(image_quality_reason)
        if not (semantic.get("items") or []):
            reasons.append({"field": "items", "reason": "no_items_detected", "severity": "critical", "detail": "No purchased item rows were accepted.", "action": "Add missing purchased item rows or rerun extraction from a clearer scan."})
        for retry in attempt.retry_plan[:4]:
            reasons.append({
                "field": retry.get("stage", "receipt"),
                "reason": retry.get("reason", "retry_recommended"),
                "severity": "medium",
                "detail": retry.get("strategy", "Agent recommended another extraction pass."),
                "action": "Consider rerunning extraction after reviewing the current fields.",
            })
        reasons = self._rank_review_reasons(reasons)
        risk_score = self._review_risk_score(reasons, confidence)
        return {
            "required": bool(reasons),
            "queue": "unprocessed_receipts",
            "reviewMode": "human_in_the_loop",
            "priority": self._review_priority(risk_score),
            "riskScore": risk_score,
            "summary": self._review_summary(reasons, risk_score),
            "reasons": reasons[:10],
            "actionableExplanations": [reason["action"] for reason in reasons[:6] if reason.get("action")],
            "suggestedChecks": self._suggested_checks(semantic, reasons),
        }

    def _merchant_review_confidence(self, semantic: dict[str, Any]) -> float:
        agent_pass = ((semantic.get("receiptAgentPasses") or {}).get("merchantConfidence") or {})
        trace = semantic.get("merchantConfidenceTrace") or {}
        confidence = agent_pass.get("confidence") or trace.get("confidence")
        if not confidence and isinstance(semantic.get("confidence"), dict):
            confidence = semantic["confidence"].get("merchant")
        return self._confidence_value(confidence)

    def _item_count_review_reason(self, semantic: dict[str, Any]) -> dict[str, Any] | None:
        pass3 = ((semantic.get("receiptAgentPasses") or {}).get("pass3CandidateSelection") or {})
        expected = pass3.get("expectedItemCount")
        selected = pass3.get("selectedCount")
        if expected and selected is not None and int(expected) != int(selected):
            return {
                "field": "items",
                "reason": "item_count_mismatch",
                "severity": "high",
                "detail": f"Receipt says {expected} items, extraction selected {selected}.",
                "action": "Check whether any purchased item rows are missing, duplicated, or incorrectly rejected.",
            }
        return None

    def _image_quality_review_reason(self, semantic: dict[str, Any]) -> dict[str, Any] | None:
        quality = semantic.get("layoutQuality") or ((semantic.get("layout") or {}).get("quality") or {})
        if not isinstance(quality, dict):
            return None
        indicators = quality.get("indicators") or {}
        warnings = quality.get("warnings") or []
        if not isinstance(indicators, dict):
            indicators = {}
        active = [
            key for key, value in indicators.items()
            if bool(value) and key in {"likelyBlurry", "sparseOcr", "weakAlignment", "lowConfidenceOcr"}
        ]
        if not active and not warnings:
            return None
        severity = "high" if {"likelyBlurry", "sparseOcr"} & set(active) else "medium"
        issue = ", ".join(active[:3]) if active else str(warnings[0])
        return {
            "field": "image",
            "reason": "image_quality_risk",
            "severity": severity,
            "detail": f"Receipt image quality may affect extraction: {issue}.",
            "action": "Compare the extracted fields with the image and rescan if text is blurry, cropped, or poorly aligned.",
        }

    def _rank_review_reasons(self, reasons: list[dict[str, Any]]) -> list[dict[str, Any]]:
        field_rank = {"totals": 0, "merchant": 1, "items": 2, "image": 3, "receipt": 4}
        severity_rank = {"critical": 0, "high": 1, "medium": 2, "low": 3}
        return sorted(
            reasons,
            key=lambda reason: (
                field_rank.get(str(reason.get("field") or ""), 9),
                severity_rank.get(str(reason.get("severity") or ""), 9),
                str(reason.get("reason") or ""),
            ),
        )

    def _review_risk_score(self, reasons: list[dict[str, Any]], confidence: float) -> int:
        score = max(0, min(35, round((1.0 - max(0.0, min(1.0, confidence))) * 35)))
        weights = {
            "item_sum_does_not_match_subtotal": 45,
            "subtotal_tax_tip_total_mismatch": 45,
            "low_confidence_merchant": 30,
            "missing_merchant": 32,
            "item_count_mismatch": 34,
            "no_items_detected": 42,
            "image_quality_risk": 24,
            "low_confidence": 18,
        }
        for reason in reasons:
            score += weights.get(str(reason.get("reason") or ""), {"critical": 30, "high": 22, "medium": 12}.get(str(reason.get("severity") or ""), 6))
        return max(0, min(100, int(score)))

    def _review_priority(self, risk_score: int) -> str:
        if risk_score >= 75:
            return "urgent"
        if risk_score >= 50:
            return "high"
        if risk_score >= 25:
            return "medium"
        return "low"

    def _review_summary(self, reasons: list[dict[str, Any]], risk_score: int) -> str:
        if not reasons:
            return "No review blockers detected."
        top = reasons[0]
        return f"{self._review_priority(risk_score).title()} risk: {top.get('detail') or top.get('reason')}"

    def _suggested_checks(self, semantic: dict[str, Any], reasons: list[dict[str, Any]]) -> list[str]:
        checks = ["merchant", "date", "total"]
        if semantic.get("items"):
            checks.append("item rows")
        if any(reason.get("field") == "totals" for reason in reasons):
            checks.append("subtotal, tax, and total")
        return list(dict.fromkeys(checks))

    def _memory_summary(self, attempt: ReceiptAgentAttempt, parser_json: dict[str, Any]) -> dict[str, Any]:
        semantic = attempt.semantic or {}
        merchant_trace = semantic.get("merchantConfidenceTrace") or {}
        merchant = semantic.get("merchant") or semantic.get("storeName") or parser_json.get("company") or ""
        return {
            "schemaVersion": "receipt-agent-memory-v1",
            "merchant": merchant,
            "merchantConfidence": self._confidence_value(merchant_trace.get("confidence") or semantic.get("confidence")),
            "source": merchant_trace.get("source", "semantic_receipt"),
            "learnableCorrections": {
                "merchantAliases": [merchant] if merchant else [],
                "itemNames": [item.get("name") for item in (semantic.get("items") or [])[:20] if item.get("name")],
                "taxRelationship": semantic.get("taxRelationship") or {},
            },
            "appliedHints": {
                "parserJsonCompany": parser_json.get("company") or parser_json.get("storeName") or "",
                "knownMerchantAliases": parser_json.get("knownMerchantAliases") or [],
            },
        }

    def _post_scan_tasks(self, attempt: ReceiptAgentAttempt) -> list[dict[str, Any]]:
        semantic = attempt.semantic or {}
        merchant = semantic.get("merchant") or semantic.get("storeName") or ""
        total = (semantic.get("facts") or {}).get("total") or semantic.get("total") or ""
        tasks = [
            {"task": "link_company_address", "status": "ready" if merchant else "needs_review", "merchant": merchant},
            {"task": "dedupe_receipt", "status": "ready", "fingerprintFields": ["merchant", "date", "total"]},
            {"task": "categorize_expense", "status": "suggested", "category": self._expense_category(merchant, semantic.get("items") or [])},
            {"task": "embed_receipt_facts", "status": "ready" if merchant or semantic.get("items") else "deferred"},
            {"task": "update_receipt_graph", "status": "ready" if merchant else "deferred"},
            {"task": "bookkeeping_entry", "status": "suggested" if total else "needs_review", "amount": total},
        ]
        return tasks

    def _expense_category(self, merchant: str, items: list[dict[str, Any]]) -> str:
        text = " ".join([merchant, *[str(item.get("name") or "") for item in items[:8]]]).lower()
        if any(token in text for token in ("restaurant", "kitchen", "cafe", "coffee", "pizza", "naan")):
            return "meals"
        if any(token in text for token in ("lowe", "home depot", "hardware", "lumber", "paint")):
            return "supplies"
        if any(token in text for token in ("pharmacy", "cvs", "walgreens")):
            return "health"
        return "uncategorized"

    def _attach_agent_metadata(self, response: dict[str, Any], agent: dict[str, Any]) -> None:
        semantic = response.get("semantic")
        if isinstance(semantic, dict):
            semantic["receiptAgent"] = agent
            semantic["humanReview"] = agent.get("humanReview", {})
            semantic["postScanTasks"] = agent.get("postScanTasks", [])
        llama = response.get("llama")
        if isinstance(llama, dict):
            llama["receiptAgent"] = agent
            llama["humanReview"] = agent.get("humanReview", {})
            llama["postScanTasks"] = agent.get("postScanTasks", [])
            intelligence = llama.setdefault("receiptIntelligence", {})
            if isinstance(intelligence, dict):
                intelligence["receiptAgent"] = agent
                intelligence["humanReview"] = agent.get("humanReview", {})
                intelligence["postScanTasks"] = agent.get("postScanTasks", [])
