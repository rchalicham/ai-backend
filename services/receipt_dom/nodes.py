from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
from typing import Any
from uuid import uuid4

from .geometry import BoundingBox, CoordinateSpace, Dimensions, ReceiptGeometrySnapshot


class RegionType(str, Enum):
    UNKNOWN = "unknown"
    TEXT = "text_region"
    IMAGE = "image_region"
    TABLE = "table_region"
    WHITESPACE = "whitespace_region"
    DETECTED = "detected_region"


class BlockType(str, Enum):
    UNKNOWN = "unknown"
    PARAGRAPH = "paragraph"
    TABLE = "table_block"
    TEXT = "text_block"
    IMAGE = "image_block"
    MIXED = "mixed_block"


@dataclass(frozen=True, slots=True)
class NodeRelationships:
    parent_id: str | None = None
    previous_sibling_id: str | None = None
    next_sibling_id: str | None = None
    above_id: str | None = None
    below_id: str | None = None
    left_id: str | None = None
    right_id: str | None = None
    nearest_neighbor_ids: tuple[str, ...] = ()


@dataclass(frozen=True, slots=True)
class SourceReference:
    engine: str = ""
    source_type: str = ""
    source_index: int | None = None
    external_id: str = ""


@dataclass(frozen=True, slots=True)
class ReceiptWord:
    id: str
    text: str
    geometry: BoundingBox
    confidence: float
    rotation: float = 0.0
    baseline: tuple[float, float, float, float] | None = None
    source_ocr_engine: str = ""
    reading_order: int = 0
    relationships: NodeRelationships = field(default_factory=NodeRelationships)
    source_reference: SourceReference = field(default_factory=SourceReference)

    @property
    def children(self) -> tuple[()]:
        return ()


@dataclass(frozen=True, slots=True)
class ReceiptLine:
    id: str
    text: str
    geometry: BoundingBox
    confidence: float
    words: tuple[ReceiptWord, ...] = ()
    baseline: tuple[float, float, float, float] | None = None
    orientation: float = 0.0
    reading_order: int = 0
    relationships: NodeRelationships = field(default_factory=NodeRelationships)
    source_reference: SourceReference = field(default_factory=SourceReference)

    @property
    def children(self) -> tuple[ReceiptWord, ...]:
        return self.words


@dataclass(frozen=True, slots=True)
class ReceiptBlock:
    id: str
    block_type: BlockType
    geometry: BoundingBox
    confidence: float
    lines: tuple[ReceiptLine, ...] = ()
    reading_order: int = 0
    relationships: NodeRelationships = field(default_factory=NodeRelationships)
    source_reference: SourceReference = field(default_factory=SourceReference)

    @property
    def children(self) -> tuple[ReceiptLine, ...]:
        return self.lines


@dataclass(frozen=True, slots=True)
class ReceiptRegion:
    id: str
    region_type: RegionType
    geometry: BoundingBox
    confidence: float
    blocks: tuple[ReceiptBlock, ...] = ()
    reading_order: int = 0
    relationships: NodeRelationships = field(default_factory=NodeRelationships)
    source_reference: SourceReference = field(default_factory=SourceReference)

    @property
    def children(self) -> tuple[ReceiptBlock, ...]:
        return self.blocks


@dataclass(frozen=True, slots=True)
class ReceiptPage:
    id: str
    index: int
    geometry: ReceiptGeometrySnapshot
    dimensions: Dimensions
    coordinate_system: CoordinateSpace
    regions: tuple[ReceiptRegion, ...] = ()
    reading_order: tuple[str, ...] = ()
    relationships: NodeRelationships = field(default_factory=NodeRelationships)

    @property
    def children(self) -> tuple[ReceiptRegion, ...]:
        return self.regions


@dataclass(frozen=True, slots=True)
class ReceiptDocumentMetadata:
    document_id: str
    version: str
    created_at: str
    document_type: str
    source_image_id: str
    source_filename: str
    page_count: int
    coordinate_system: CoordinateSpace
    diagnostics: tuple[tuple[str, Any], ...] = ()

    @classmethod
    def create(
        cls,
        *,
        source_image_id: str = "",
        source_filename: str = "",
        page_count: int = 1,
        diagnostics: tuple[tuple[str, Any], ...] = (),
    ) -> "ReceiptDocumentMetadata":
        return cls(
            document_id=str(uuid4()),
            version="receipt-dom-v1",
            created_at=datetime.now(timezone.utc).isoformat(),
            document_type="physical_receipt",
            source_image_id=source_image_id,
            source_filename=source_filename,
            page_count=page_count,
            coordinate_system=CoordinateSpace.CORRECTED_IMAGE,
            diagnostics=diagnostics,
        )


@dataclass(frozen=True, slots=True)
class ReceiptDocument:
    metadata: ReceiptDocumentMetadata
    pages: tuple[ReceiptPage, ...]

    @property
    def id(self) -> str:
        return self.metadata.document_id

    @property
    def children(self) -> tuple[ReceiptPage, ...]:
        return self.pages

    def walk(self) -> tuple[Any, ...]:
        nodes: list[Any] = [self]
        for page in self.pages:
            nodes.append(page)
            for region in page.regions:
                nodes.append(region)
                for block in region.blocks:
                    nodes.append(block)
                    for line in block.lines:
                        nodes.append(line)
                        nodes.extend(line.words)
        return tuple(nodes)
