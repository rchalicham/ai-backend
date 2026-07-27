from __future__ import annotations

from services.receipt_dom import BlockType, ReceiptDocument, RegionType

from .alignment import ReceiptAlignmentAnalyzer
from .density import ReceiptDensityAnalyzer
from .models import (
    AlignmentType,
    BlockAnnotation,
    CandidateTable,
    PageRegionClass,
    PhysicalBlockType,
    PhysicalRegionType,
    RegionAnnotation,
)


class ReceiptRegionClassifier:
    def __init__(self, density_analyzer: ReceiptDensityAnalyzer | None = None) -> None:
        self.density_analyzer = density_analyzer or ReceiptDensityAnalyzer()

    def classify(self, document: ReceiptDocument, tables: tuple[CandidateTable, ...]) -> tuple[RegionAnnotation, ...]:
        annotations = []
        table_blocks = {block_id for table in tables for block_id in table.block_ids}
        for page in document.pages:
            for region in page.regions:
                relative_top = region.geometry.y / max(page.dimensions.height, 1)
                relative_bottom = region.geometry.bottom / max(page.dimensions.height, 1)
                page_region = (
                    PageRegionClass.HEADER if relative_top <= 0.2
                    else PageRegionClass.FOOTER if relative_bottom >= 0.82
                    else PageRegionClass.BODY
                )
                density = self.density_analyzer.measure(region)
                block_ids = {block.id for block in region.blocks}
                if region.region_type == RegionType.WHITESPACE:
                    physical_type = PhysicalRegionType.WHITESPACE
                elif region.region_type == RegionType.IMAGE:
                    physical_type = PhysicalRegionType.IMAGE
                elif block_ids & table_blocks:
                    physical_type = PhysicalRegionType.TABLE_CANDIDATE
                elif density.whitespace_percentage > 0.85:
                    physical_type = PhysicalRegionType.SPARSE_TEXT
                elif density.character_density > 0.35 or density.line_density > 0.35:
                    physical_type = PhysicalRegionType.DENSE_TEXT
                elif region.blocks:
                    physical_type = PhysicalRegionType.SPARSE_TEXT
                else:
                    physical_type = PhysicalRegionType.UNKNOWN
                annotations.append(RegionAnnotation(
                    region.id, page_region, physical_type, region.geometry,
                    round(min(1.0, 0.55 + region.confidence * 0.4), 4), density,
                ))
        return tuple(annotations)


class ReceiptBlockClassifier:
    def __init__(
        self,
        density_analyzer: ReceiptDensityAnalyzer | None = None,
        alignment_analyzer: ReceiptAlignmentAnalyzer | None = None,
    ) -> None:
        self.density_analyzer = density_analyzer or ReceiptDensityAnalyzer()
        self.alignment_analyzer = alignment_analyzer or ReceiptAlignmentAnalyzer()

    def classify(self, document: ReceiptDocument, tables: tuple[CandidateTable, ...]) -> tuple[BlockAnnotation, ...]:
        annotations = []
        table_blocks = {block_id for table in tables for block_id in table.block_ids}
        for page in document.pages:
            for region in page.regions:
                for block in region.blocks:
                    density = self.density_analyzer.measure(block)
                    if block.id in table_blocks:
                        physical_type = PhysicalBlockType.TABLE
                    elif block.block_type == BlockType.IMAGE:
                        physical_type = PhysicalBlockType.IMAGE
                    elif density.whitespace_percentage > 0.96:
                        physical_type = PhysicalBlockType.WHITESPACE
                    elif block.geometry.height <= 4 and block.geometry.width >= page.dimensions.width * 0.65:
                        physical_type = PhysicalBlockType.SEPARATOR
                    elif len(block.lines) > 1:
                        physical_type = PhysicalBlockType.PARAGRAPH
                    elif block.lines:
                        physical_type = PhysicalBlockType.TEXT
                    else:
                        physical_type = PhysicalBlockType.UNKNOWN
                    line_alignments = [self.alignment_analyzer.classify(line, page.dimensions.width) for line in block.lines]
                    alignment = line_alignments[0] if line_alignments and len(set(line_alignments)) == 1 else AlignmentType.MIXED
                    annotations.append(BlockAnnotation(
                        block.id, physical_type, block.geometry,
                        round(min(1.0, 0.6 + block.confidence * 0.35), 4), alignment, density,
                    ))
        return tuple(annotations)
