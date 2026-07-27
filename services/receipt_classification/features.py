from __future__ import annotations

from math import sqrt
from statistics import fmean, pstdev
from typing import Iterable

from services.receipt_dom import ReceiptBlock, ReceiptDocument, ReceiptLine, ReceiptWord
from services.receipt_structure import ReceiptPhysicalStructure

from .models import FeatureMetricGroup, ReceiptFeatureVector


def _mean(values: Iterable[float]) -> float:
    values = tuple(float(value) for value in values)
    return fmean(values) if values else 0.0


def _group(**values: float) -> FeatureMetricGroup:
    return FeatureMetricGroup(tuple(sorted((name, round(float(value), 8)) for name, value in values.items())))


class ReceiptFeatureExtractor:
    """Extracts geometry-only measurements; node text is deliberately never read."""

    def extract(
        self,
        document: ReceiptDocument,
        structure: ReceiptPhysicalStructure,
    ) -> ReceiptFeatureVector:
        pages = document.pages
        widths = [page.dimensions.width for page in pages]
        heights = [page.dimensions.height for page in pages]
        page_area = sum(max(page.dimensions.width * page.dimensions.height, 1.0) for page in pages)
        regions = structure.region_annotations
        blocks = tuple(node for page in pages for region in page.regions for node in region.blocks)
        lines = tuple(node for block in blocks for node in block.lines)
        words = tuple(node for line in lines for node in line.words)

        header_height = sum(item.geometry.height for item in regions if item.page_region.value == "header")
        footer_height = sum(item.geometry.height for item in regions if item.page_region.value == "footer")
        region_count = max(len(regions), 1)
        block_count = max(len(structure.block_annotations), 1)
        tables = structure.candidate_tables
        whitespace = structure.whitespace_zones

        line_gaps = self._vertical_gaps(lines)
        block_gaps = self._vertical_gaps(blocks)
        word_gaps = self._word_gaps(lines)
        densities = [cell.density for density_map in structure.density_maps for cell in density_map.cells]
        whitespace_area = sum(zone.geometry.width * zone.geometry.height for zone in whitespace)
        group_sizes = [len(group.node_ids) for group in structure.visual_groups]
        geometric_confidences = [page.geometry.geometric_confidence for page in pages]
        perspective_offsets = [
            abs(value - (1.0 if row == column else 0.0))
            for page in pages
            for row, values in enumerate(page.geometry.perspective_matrix)
            for column, value in enumerate(values)
        ]

        return ReceiptFeatureVector(
            document_id=document.id,
            page_metrics=_group(
                page_count=len(pages),
                width=_mean(widths),
                height=_mean(heights),
                aspect_ratio=_mean(width / max(height, 1.0) for width, height in zip(widths, heights)),
            ),
            layout_metrics=_group(
                header_height_ratio=header_height / page_area * _mean(widths),
                footer_height_ratio=footer_height / page_area * _mean(widths),
                reading_column_count=_mean(len(page.geometry.detected_columns) for page in pages),
                region_count=len(regions),
                dense_region_ratio=sum(item.physical_type.value == "dense_text_region" for item in regions) / region_count,
                sparse_region_ratio=sum(item.physical_type.value == "sparse_text_region" for item in regions) / region_count,
                table_block_ratio=sum(item.physical_type.value == "table_block" for item in structure.block_annotations) / block_count,
            ),
            table_metrics=_group(
                table_count=len(tables),
                average_row_count=_mean(len(table.row_line_ids) for table in tables),
                average_column_count=_mean(len(table.columns) for table in tables),
                average_width_ratio=_mean(table.geometry.width / max(_mean(widths), 1.0) for table in tables),
                row_spacing_consistency=_mean(table.row_spacing_consistency for table in tables),
                row_height_consistency=_mean(table.row_height_consistency for table in tables),
            ),
            spacing_metrics=_group(
                average_line_height=_mean(line.geometry.height for line in lines),
                average_word_spacing=_mean(word_gaps),
                average_block_spacing=_mean(block_gaps),
                average_line_spacing=_mean(line_gaps),
                separator_position=_mean(
                    separator.geometry.y / max(_mean(heights), 1.0) for separator in structure.separators
                ),
            ),
            alignment_metrics=_group(
                cluster_count=len(structure.alignment_groups),
                left_ratio=sum(group.alignment.value == "left_aligned" for group in structure.alignment_groups) / max(len(structure.alignment_groups), 1),
                center_ratio=sum(group.alignment.value == "center_aligned" for group in structure.alignment_groups) / max(len(structure.alignment_groups), 1),
                right_ratio=sum(group.alignment.value == "right_aligned" for group in structure.alignment_groups) / max(len(structure.alignment_groups), 1),
                average_confidence=_mean(group.confidence for group in structure.alignment_groups),
            ),
            reading_metrics=_group(
                reading_node_count=_mean(len(page.reading_order) for page in pages),
                visual_group_count=len(structure.visual_groups),
                average_visual_group_size=_mean(group_sizes),
                multiline_group_ratio=sum(group.group_type.value == "multiline_group" for group in structure.visual_groups) / max(len(group_sizes), 1),
                table_group_ratio=sum(group.group_type.value == "table_group" for group in structure.visual_groups) / max(len(group_sizes), 1),
            ),
            density_metrics=_group(
                mean_density=_mean(densities),
                density_stddev=pstdev(densities) if len(densities) > 1 else 0.0,
                maximum_density=max(densities, default=0.0),
                whitespace_percentage=min(1.0, whitespace_area / page_area),
                block_density=len(blocks) / page_area,
                line_density=len(lines) / page_area,
                word_density=len(words) / page_area,
            ),
            geometry_metrics=_group(
                confidence=_mean(geometric_confidences),
                absolute_rotation=_mean(abs(page.geometry.rotation) for page in pages),
                absolute_skew=_mean(abs(page.geometry.skew) for page in pages),
                perspective_distortion=sqrt(sum(value * value for value in perspective_offsets)),
                boundary_point_count=_mean(len(page.geometry.receipt_boundary) for page in pages),
            ),
        )

    @staticmethod
    def _vertical_gaps(nodes: Iterable[ReceiptBlock | ReceiptLine]) -> tuple[float, ...]:
        ordered = sorted(nodes, key=lambda node: (node.geometry.y, node.geometry.x))
        return tuple(max(0.0, current.geometry.y - previous.geometry.bottom) for previous, current in zip(ordered, ordered[1:]))

    @staticmethod
    def _word_gaps(lines: Iterable[ReceiptLine]) -> tuple[float, ...]:
        gaps: list[float] = []
        for line in lines:
            ordered: list[ReceiptWord] = sorted(line.words, key=lambda word: word.geometry.x)
            gaps.extend(max(0.0, current.geometry.x - previous.geometry.right) for previous, current in zip(ordered, ordered[1:]))
        return tuple(gaps)
