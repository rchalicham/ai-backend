from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from typing import Any

from services.receipt_dom import BoundingBox


class PageRegionClass(str, Enum):
    HEADER = "header"
    BODY = "body"
    FOOTER = "footer"
    UNKNOWN = "unknown"


class PhysicalRegionType(str, Enum):
    DENSE_TEXT = "dense_text_region"
    SPARSE_TEXT = "sparse_text_region"
    TABLE_CANDIDATE = "table_candidate_region"
    IMAGE = "image_region"
    WHITESPACE = "whitespace_region"
    SEPARATOR = "separator_region"
    MIXED = "mixed_region"
    UNKNOWN = "unknown"


class PhysicalBlockType(str, Enum):
    PARAGRAPH = "paragraph_block"
    TABLE = "table_block"
    IMAGE = "image_block"
    MIXED = "mixed_block"
    SEPARATOR = "separator_block"
    WHITESPACE = "whitespace_block"
    TEXT = "text_block"
    UNKNOWN = "unknown"


class AlignmentType(str, Enum):
    LEFT = "left_aligned"
    CENTER = "center_aligned"
    RIGHT = "right_aligned"
    JUSTIFIED = "justified"
    MIXED = "mixed"


class VisualGroupType(str, Enum):
    WORD = "word_group"
    MULTILINE = "multiline_group"
    PARAGRAPH = "paragraph_group"
    TABLE = "table_group"
    CAPTION = "caption_group"


@dataclass(frozen=True, slots=True)
class DensityMetrics:
    character_density: float
    word_density: float
    line_density: float
    whitespace_percentage: float
    block_density: float


@dataclass(frozen=True, slots=True)
class DensityCell:
    geometry: BoundingBox
    density: float
    node_ids: tuple[str, ...] = ()


@dataclass(frozen=True, slots=True)
class DensityMap:
    page_id: str
    rows: int
    columns: int
    cells: tuple[DensityCell, ...]


@dataclass(frozen=True, slots=True)
class RegionAnnotation:
    node_id: str
    page_region: PageRegionClass
    physical_type: PhysicalRegionType
    geometry: BoundingBox
    confidence: float
    density: DensityMetrics


@dataclass(frozen=True, slots=True)
class BlockAnnotation:
    node_id: str
    physical_type: PhysicalBlockType
    geometry: BoundingBox
    confidence: float
    alignment: AlignmentType
    density: DensityMetrics


@dataclass(frozen=True, slots=True)
class TableColumn:
    index: int
    x: float
    width: float
    alignment: AlignmentType
    confidence: float


@dataclass(frozen=True, slots=True)
class CandidateTable:
    id: str
    page_id: str
    block_ids: tuple[str, ...]
    row_line_ids: tuple[str, ...]
    columns: tuple[TableColumn, ...]
    geometry: BoundingBox
    confidence: float
    row_spacing_consistency: float
    row_height_consistency: float


@dataclass(frozen=True, slots=True)
class AlignmentGroup:
    id: str
    page_id: str
    alignment: AlignmentType
    node_ids: tuple[str, ...]
    anchor: float
    confidence: float


@dataclass(frozen=True, slots=True)
class VisualGroup:
    id: str
    page_id: str
    group_type: VisualGroupType
    node_ids: tuple[str, ...]
    geometry: BoundingBox
    confidence: float


@dataclass(frozen=True, slots=True)
class WhitespaceZone:
    id: str
    page_id: str
    kind: str
    geometry: BoundingBox
    confidence: float


@dataclass(frozen=True, slots=True)
class SeparatorLine:
    id: str
    page_id: str
    geometry: BoundingBox
    confidence: float


@dataclass(frozen=True, slots=True)
class ReceiptStructuralHints:
    candidate_tables: tuple[str, ...]
    candidate_headers: tuple[str, ...]
    candidate_footers: tuple[str, ...]
    alignment_groups: tuple[str, ...]
    visual_groups: tuple[str, ...]
    separator_lines: tuple[str, ...]
    dense_regions: tuple[str, ...]
    sparse_regions: tuple[str, ...]
    whitespace_zones: tuple[str, ...]
    reading_columns: tuple[BoundingBox, ...]
    confidence: tuple[tuple[str, float], ...]


@dataclass(frozen=True, slots=True)
class ReceiptPhysicalStructure:
    schema_version: str
    document_id: str
    region_annotations: tuple[RegionAnnotation, ...]
    block_annotations: tuple[BlockAnnotation, ...]
    candidate_tables: tuple[CandidateTable, ...]
    alignment_groups: tuple[AlignmentGroup, ...]
    visual_groups: tuple[VisualGroup, ...]
    separators: tuple[SeparatorLine, ...]
    whitespace_zones: tuple[WhitespaceZone, ...]
    density_maps: tuple[DensityMap, ...]
    hints: ReceiptStructuralHints
    diagnostics: tuple[tuple[str, Any], ...] = ()
