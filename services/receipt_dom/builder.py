from __future__ import annotations

from dataclasses import replace
from typing import Any
from uuid import NAMESPACE_URL, uuid5

from .geometry import BoundingBox, CoordinateSpace, Dimensions, ReceiptGeometrySnapshot
from .nodes import (
    BlockType,
    NodeRelationships,
    ReceiptBlock,
    ReceiptDocument,
    ReceiptDocumentMetadata,
    ReceiptLine,
    ReceiptPage,
    ReceiptRegion,
    ReceiptWord,
    RegionType,
    SourceReference,
)
from .reading_order import ReadingOrderEngine


class ReceiptDomBuilder:
    """Builds an immutable physical AST from geometry and existing OCR artifacts."""

    def __init__(self, reading_order_engine: ReadingOrderEngine | None = None) -> None:
        self.reading_order_engine = reading_order_engine or ReadingOrderEngine()

    def build(
        self,
        *,
        receipt_geometry: Any,
        ocr_blocks: list[dict[str, Any]] | None = None,
        ocr_words: list[dict[str, Any]] | None = None,
        ocr_lines: list[str | dict[str, Any]] | None = None,
        source_ocr_engine: str = "",
        source_image_id: str = "",
        source_filename: str = "",
        diagnostics: dict[str, Any] | None = None,
    ) -> ReceiptDocument:
        geometry = (
            receipt_geometry
            if isinstance(receipt_geometry, ReceiptGeometrySnapshot)
            else ReceiptGeometrySnapshot.from_phase1(receipt_geometry)
        )
        metadata = ReceiptDocumentMetadata.create(
            source_image_id=source_image_id,
            source_filename=source_filename,
            diagnostics=_freeze_mapping(diagnostics or {}),
        )
        seed = metadata.document_id
        raw_words = list(ocr_words or ocr_blocks or [])
        blocks = self._build_blocks(seed, raw_words, list(ocr_lines or []), source_ocr_engine, geometry)
        region_box = self._union(tuple(block.geometry for block in blocks)) or BoundingBox(
            0, 0, geometry.page_dimensions.width, geometry.page_dimensions.height
        )
        text_region_id = self._id(seed, "region", 0)
        blocks = tuple(
            replace(block, relationships=replace(block.relationships, parent_id=text_region_id))
            for block in blocks
        )
        regions: list[ReceiptRegion] = [
            ReceiptRegion(
                id=text_region_id,
                region_type=RegionType.TEXT if blocks else RegionType.DETECTED,
                geometry=region_box,
                confidence=self._average(tuple(block.confidence for block in blocks), geometry.geometric_confidence),
                blocks=blocks,
                source_reference=SourceReference(source_type="ocr_layout"),
            )
        ]
        for index, box in enumerate(geometry.estimated_reading_zones):
            regions.append(
                ReceiptRegion(
                    id=self._id(seed, "detected-region", index),
                    region_type=RegionType.DETECTED,
                    geometry=box,
                    confidence=geometry.geometric_confidence,
                    source_reference=SourceReference(source_type="geometry.reading_zone", source_index=index),
                )
            )
        regions = list(self.reading_order_engine.order(regions))
        page_id = self._id(seed, "page", 0)
        regions = [
            replace(region, relationships=replace(region.relationships, parent_id=page_id))
            for region in regions
        ]
        page = ReceiptPage(
            id=page_id,
            index=0,
            geometry=geometry,
            dimensions=Dimensions(geometry.page_dimensions.width, geometry.page_dimensions.height),
            coordinate_system=CoordinateSpace.CORRECTED_IMAGE,
            regions=tuple(regions),
            reading_order=tuple(region.id for region in regions),
            relationships=NodeRelationships(parent_id=metadata.document_id),
        )
        return ReceiptDocument(metadata=metadata, pages=(page,))

    def _build_blocks(
        self,
        seed: str,
        raw_words: list[dict[str, Any]],
        raw_lines: list[str | dict[str, Any]],
        engine: str,
        geometry: ReceiptGeometrySnapshot,
    ) -> tuple[ReceiptBlock, ...]:
        grouped: dict[tuple[int, int], dict[int, list[tuple[int, dict[str, Any]]]]] = {}
        for index, word in enumerate(raw_words):
            block_key = (self._integer(word, "block", "block_num"), self._integer(word, "paragraph", "par_num"))
            line_key = self._integer(word, "line", "line_num")
            grouped.setdefault(block_key, {}).setdefault(line_key, []).append((index, word))
        blocks: list[ReceiptBlock] = []
        for block_index, (block_key, line_groups) in enumerate(sorted(grouped.items())):
            block_id = self._id(seed, "block", block_index)
            lines = []
            for line_index, (_, entries) in enumerate(sorted(line_groups.items())):
                lines.append(self._line_from_words(seed, block_id, block_index, line_index, entries, engine))
            ordered_lines = self.reading_order_engine.order(lines)
            box = self._union(tuple(line.geometry for line in ordered_lines))
            if box is None:
                continue
            blocks.append(
                ReceiptBlock(
                    id=block_id,
                    block_type=BlockType.TEXT,
                    geometry=box,
                    confidence=self._average(tuple(line.confidence for line in ordered_lines)),
                    lines=ordered_lines,
                    source_reference=SourceReference(
                        engine=engine, source_type="ocr.block", external_id=f"{block_key[0]}:{block_key[1]}"
                    ),
                )
            )
        if not blocks and raw_lines:
            blocks = [self._block_from_lines(seed, raw_lines, engine, geometry)]
        ordered_blocks = self.reading_order_engine.order(blocks)
        return tuple(self._reparent_block(block) for block in ordered_blocks)

    def _line_from_words(
        self,
        seed: str,
        block_id: str,
        block_index: int,
        line_index: int,
        entries: list[tuple[int, dict[str, Any]]],
        engine: str,
    ) -> ReceiptLine:
        words = []
        for word_index, (source_index, raw) in enumerate(entries):
            box = self._box(raw)
            text = str(raw.get("text") or raw.get("value") or "")
            words.append(
                ReceiptWord(
                    id=self._id(seed, f"word-{block_index}-{line_index}", word_index),
                    text=text,
                    geometry=box,
                    confidence=self._confidence(raw),
                    rotation=float(raw.get("rotation") or 0.0),
                    baseline=self._baseline(raw, box),
                    source_ocr_engine=str(raw.get("engine") or raw.get("source") or engine),
                    source_reference=SourceReference(
                        engine=engine, source_type=str(raw.get("source") or "ocr.word"),
                        source_index=source_index, external_id=str(raw.get("id") or ""),
                    ),
                )
            )
        ordered_words = self.reading_order_engine.order(words)
        line_id = self._id(seed, f"line-{block_index}", line_index)
        ordered_words = tuple(
            replace(word, relationships=replace(word.relationships, parent_id=line_id))
            for word in ordered_words
        )
        box = self._union(tuple(word.geometry for word in ordered_words)) or BoundingBox(0, 0, 0, 0)
        return ReceiptLine(
            id=line_id,
            text=" ".join(word.text for word in ordered_words if word.text).strip(),
            geometry=box,
            confidence=self._average(tuple(word.confidence for word in ordered_words)),
            words=ordered_words,
            baseline=(box.x, box.bottom, box.right, box.bottom),
            orientation=self._average(tuple(word.rotation for word in ordered_words), 0.0),
            relationships=NodeRelationships(parent_id=block_id),
            source_reference=SourceReference(engine=engine, source_type="ocr.line", source_index=line_index),
        )

    def _block_from_lines(
        self, seed: str, raw_lines: list[str | dict[str, Any]], engine: str,
        geometry: ReceiptGeometrySnapshot,
    ) -> ReceiptBlock:
        block_id = self._id(seed, "block", 0)
        page_width, page_height = geometry.page_dimensions.width, geometry.page_dimensions.height
        line_height = max(12.0, page_height / max(len(raw_lines) * 1.4, 1))
        lines = []
        for index, raw in enumerate(raw_lines):
            payload = raw if isinstance(raw, dict) else {"text": raw}
            box = self._box(payload)
            if box.width <= 0 or box.height <= 0:
                box = BoundingBox(page_width * 0.05, index * line_height, page_width * 0.9, line_height)
            lines.append(
                ReceiptLine(
                    id=self._id(seed, "line-0", index),
                    text=str(payload.get("text") or payload.get("value") or ""),
                    geometry=box,
                    confidence=self._confidence(payload),
                    baseline=self._baseline(payload, box),
                    orientation=float(payload.get("orientation") or payload.get("rotation") or 0.0),
                    relationships=NodeRelationships(parent_id=block_id),
                    source_reference=SourceReference(engine=engine, source_type="ocr.line", source_index=index),
                )
            )
        lines = list(self.reading_order_engine.order(lines))
        return ReceiptBlock(
            id=block_id,
            block_type=BlockType.TEXT,
            geometry=self._union(tuple(line.geometry for line in lines)) or BoundingBox(0, 0, 0, 0),
            confidence=self._average(tuple(line.confidence for line in lines)),
            lines=tuple(lines),
            source_reference=SourceReference(engine=engine, source_type="ocr.synthetic_block", source_index=0),
        )

    @staticmethod
    def _reparent_block(block: ReceiptBlock) -> ReceiptBlock:
        lines = tuple(
            replace(line, relationships=replace(line.relationships, parent_id=block.id))
            for line in block.lines
        )
        return replace(block, lines=lines)

    @staticmethod
    def _box(raw: dict[str, Any]) -> BoundingBox:
        bbox = raw.get("bbox") or raw.get("geometry") or {}
        return BoundingBox(
            float(raw.get("x", bbox.get("x", bbox.get("left", 0))) or 0),
            float(raw.get("y", bbox.get("y", bbox.get("top", 0))) or 0),
            float(raw.get("width", bbox.get("width", 0)) or 0),
            float(raw.get("height", bbox.get("height", 0)) or 0),
            CoordinateSpace.CORRECTED_IMAGE,
        )

    @staticmethod
    def _baseline(raw: dict[str, Any], box: BoundingBox) -> tuple[float, float, float, float]:
        baseline = raw.get("baseline")
        if isinstance(baseline, (list, tuple)) and len(baseline) == 4:
            return tuple(float(value) for value in baseline)  # type: ignore[return-value]
        return box.x, box.bottom, box.right, box.bottom

    @staticmethod
    def _integer(raw: dict[str, Any], *keys: str) -> int:
        for key in keys:
            try:
                return int(raw.get(key) or 0)
            except (TypeError, ValueError):
                continue
        return 0

    @staticmethod
    def _confidence(raw: dict[str, Any]) -> float:
        try:
            value = float(raw.get("confidence", 0.0))
            return max(0.0, min(1.0, value / 100.0 if value > 1 else value))
        except (TypeError, ValueError):
            return 0.0

    @staticmethod
    def _union(boxes: tuple[BoundingBox, ...]) -> BoundingBox | None:
        if not boxes:
            return None
        left, top = min(box.x for box in boxes), min(box.y for box in boxes)
        right, bottom = max(box.right for box in boxes), max(box.bottom for box in boxes)
        return BoundingBox(left, top, right - left, bottom - top, boxes[0].coordinate_space)

    @staticmethod
    def _average(values: tuple[float, ...], default: float = 0.0) -> float:
        return sum(values) / len(values) if values else default

    @staticmethod
    def _id(seed: str, kind: str, index: int) -> str:
        return str(uuid5(NAMESPACE_URL, f"{seed}:{kind}:{index}"))


def _freeze(value: Any) -> Any:
    if isinstance(value, dict):
        return _freeze_mapping(value)
    if isinstance(value, (list, tuple)):
        return tuple(_freeze(item) for item in value)
    return value


def _freeze_mapping(value: dict[str, Any]) -> tuple[tuple[str, Any], ...]:
    return tuple((str(key), _freeze(item)) for key, item in sorted(value.items()))
