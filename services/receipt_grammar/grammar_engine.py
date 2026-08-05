from __future__ import annotations

from services.receipt_classification import ReceiptClassification
from services.receipt_dom import ReceiptDocument
from services.receipt_structure import ReceiptPhysicalStructure

from .grammar_compiler import ReceiptGrammarCompiler
from .grammar_learning import ReceiptGrammarLearningService
from .grammar_repository import ReceiptGrammarRepository
from .grammar_validator import ReceiptGrammarValidator
from .models import ReceiptGrammarContext


class ReceiptGrammarEngine:
    """Coordinates grammar sidecar evaluation after receipt classification."""

    def __init__(
        self,
        repository: ReceiptGrammarRepository | None = None,
        compiler: ReceiptGrammarCompiler | None = None,
        validator: ReceiptGrammarValidator | None = None,
        learning: ReceiptGrammarLearningService | None = None,
    ) -> None:
        self.repository = repository or ReceiptGrammarRepository()
        self.compiler = compiler or ReceiptGrammarCompiler()
        self.validator = validator or ReceiptGrammarValidator()
        self.learning = learning or ReceiptGrammarLearningService()

    def evaluate(
        self,
        document: ReceiptDocument,
        structure: ReceiptPhysicalStructure,
        classification: ReceiptClassification,
        document_family_context=None,
    ) -> ReceiptGrammarContext:
        family = (
            document_family_context.activation.family.value
            if document_family_context is not None
            and document_family_context.activation.family.value != "unknown"
            else classification.candidates[0].receipt_family if classification.candidates else ""
        )
        if not family:
            return ReceiptGrammarContext(
                receipt_family="",
                loaded=False,
                diagnostics=self._diagnostics("no_classified_receipt_family"),
            )
        grammar = self.repository.load_grammar(family)
        if grammar is None:
            return ReceiptGrammarContext(
                receipt_family=family,
                loaded=False,
                diagnostics=self._diagnostics("matching_grammar_not_found"),
            )
        compilation = self.compiler.compile(grammar)
        if not compilation.valid:
            return ReceiptGrammarContext(
                receipt_family=family,
                loaded=True,
                grammar=grammar,
                compilation=compilation,
                diagnostics=self._diagnostics("grammar_compilation_failed"),
            )
        compliance = self.validator.validate(document, structure, grammar)
        suggestions = self.learning.suggest(grammar, compliance)
        return ReceiptGrammarContext(
            receipt_family=family,
            loaded=True,
            grammar=grammar,
            compilation=compilation,
            compliance=compliance,
            learning_suggestions=suggestions,
            diagnostics=(
                ("sidecar", True),
                ("affectsExtraction", False),
                ("parserAuthorityChanged", False),
                ("merchantDetectionPerformed", False),
                ("productDetectionPerformed", False),
                ("grammarExecutedAsParser", False),
            ),
        )

    def safe_evaluate(
        self,
        document: ReceiptDocument | None,
        structure: ReceiptPhysicalStructure | None,
        classification: ReceiptClassification | None,
        document_family_context=None,
    ) -> ReceiptGrammarContext | None:
        if document is None or structure is None or classification is None:
            return None
        try:
            return self.evaluate(document, structure, classification, document_family_context)
        except Exception as exc:
            return ReceiptGrammarContext(
                receipt_family="",
                loaded=False,
                diagnostics=self._diagnostics(f"grammar_sidecar_failed:{exc.__class__.__name__}"),
            )

    def _diagnostics(self, warning: str) -> tuple[tuple[str, object], ...]:
        return (
            ("sidecar", True),
            ("affectsExtraction", False),
            ("parserAuthorityChanged", False),
            ("merchantDetectionPerformed", False),
            ("productDetectionPerformed", False),
            ("grammarExecutedAsParser", False),
            ("warning", warning),
        )
