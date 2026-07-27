from __future__ import annotations

from services.receipt_dom import ReceiptDocument

from .models import (
    PageRegionClass,
    PhysicalRegionType,
    ReceiptStructuralHints,
)


class ReceiptStructuralHintsBuilder:
    def build(
        self,
        document: ReceiptDocument,
        *,
        region_annotations,
        candidate_tables,
        alignment_groups,
        visual_groups,
        separators,
        whitespace_zones,
    ) -> ReceiptStructuralHints:
        region_confidence = (
            sum(annotation.confidence for annotation in region_annotations) / len(region_annotations)
            if region_annotations else 0.0
        )
        table_confidence = (
            sum(table.confidence for table in candidate_tables) / len(candidate_tables)
            if candidate_tables else 0.0
        )
        grouping_confidence = (
            sum(group.confidence for group in visual_groups) / len(visual_groups)
            if visual_groups else 0.0
        )
        return ReceiptStructuralHints(
            candidate_tables=tuple(table.id for table in candidate_tables),
            candidate_headers=tuple(annotation.node_id for annotation in region_annotations if annotation.page_region == PageRegionClass.HEADER),
            candidate_footers=tuple(annotation.node_id for annotation in region_annotations if annotation.page_region == PageRegionClass.FOOTER),
            alignment_groups=tuple(group.id for group in alignment_groups),
            visual_groups=tuple(group.id for group in visual_groups),
            separator_lines=tuple(separator.id for separator in separators),
            dense_regions=tuple(annotation.node_id for annotation in region_annotations if annotation.physical_type == PhysicalRegionType.DENSE_TEXT),
            sparse_regions=tuple(annotation.node_id for annotation in region_annotations if annotation.physical_type == PhysicalRegionType.SPARSE_TEXT),
            whitespace_zones=tuple(zone.id for zone in whitespace_zones),
            reading_columns=tuple(column for page in document.pages for column in page.geometry.detected_columns),
            confidence=(
                ("regions", round(region_confidence, 4)),
                ("tables", round(table_confidence, 4)),
                ("grouping", round(grouping_confidence, 4)),
                ("overall", round((region_confidence + table_confidence + grouping_confidence) / 3.0, 4)),
            ),
        )
