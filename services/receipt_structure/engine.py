from __future__ import annotations

from services.receipt_dom import ReceiptDocument

from .alignment import ReceiptAlignmentAnalyzer
from .classification import ReceiptBlockClassifier, ReceiptRegionClassifier
from .density import ReceiptDensityAnalyzer
from .grouping import ReceiptVisualGroupingEngine
from .hints import ReceiptStructuralHintsBuilder
from .models import ReceiptPhysicalStructure
from .table import ReceiptTableDetector
from .whitespace import ReceiptWhitespaceAnalyzer


class ReceiptPhysicalStructureEngine:
    """Produces immutable physical annotations over a ReceiptDocument."""

    def __init__(
        self,
        region_classifier: ReceiptRegionClassifier | None = None,
        block_classifier: ReceiptBlockClassifier | None = None,
        table_detector: ReceiptTableDetector | None = None,
        whitespace_analyzer: ReceiptWhitespaceAnalyzer | None = None,
        density_analyzer: ReceiptDensityAnalyzer | None = None,
        alignment_analyzer: ReceiptAlignmentAnalyzer | None = None,
        grouping_engine: ReceiptVisualGroupingEngine | None = None,
        hints_builder: ReceiptStructuralHintsBuilder | None = None,
    ) -> None:
        self.density_analyzer = density_analyzer or ReceiptDensityAnalyzer()
        self.alignment_analyzer = alignment_analyzer or ReceiptAlignmentAnalyzer()
        self.table_detector = table_detector or ReceiptTableDetector()
        self.whitespace_analyzer = whitespace_analyzer or ReceiptWhitespaceAnalyzer()
        self.region_classifier = region_classifier or ReceiptRegionClassifier(self.density_analyzer)
        self.block_classifier = block_classifier or ReceiptBlockClassifier(self.density_analyzer, self.alignment_analyzer)
        self.grouping_engine = grouping_engine or ReceiptVisualGroupingEngine()
        self.hints_builder = hints_builder or ReceiptStructuralHintsBuilder()

    def analyze(self, document: ReceiptDocument) -> ReceiptPhysicalStructure:
        tables = self.table_detector.detect(document)
        alignment_groups = self.alignment_analyzer.groups(document)
        visual_groups = self.grouping_engine.group(document, tables)
        whitespace_zones, separators = self.whitespace_analyzer.analyze(document)
        region_annotations = self.region_classifier.classify(document, tables)
        block_annotations = self.block_classifier.classify(document, tables)
        density_maps = self.density_analyzer.maps(document)
        hints = self.hints_builder.build(
            document,
            region_annotations=region_annotations,
            candidate_tables=tables,
            alignment_groups=alignment_groups,
            visual_groups=visual_groups,
            separators=separators,
            whitespace_zones=whitespace_zones,
        )
        return ReceiptPhysicalStructure(
            schema_version="receipt-physical-structure-v1",
            document_id=document.id,
            region_annotations=region_annotations,
            block_annotations=block_annotations,
            candidate_tables=tables,
            alignment_groups=alignment_groups,
            visual_groups=visual_groups,
            separators=separators,
            whitespace_zones=whitespace_zones,
            density_maps=density_maps,
            hints=hints,
            diagnostics=(
                ("immutableAnnotation", True),
                ("sourceDocumentVersion", document.metadata.version),
                ("affectsExtraction", False),
            ),
        )

    def safe_analyze(self, document: ReceiptDocument | None) -> ReceiptPhysicalStructure | None:
        if document is None:
            return None
        try:
            return self.analyze(document)
        except Exception:
            return None
