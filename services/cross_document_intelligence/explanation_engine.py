from __future__ import annotations

from .models import Correlation, Explanation, Pattern, Timeline


class CrossDocumentExplanationEngine:
    def explain(
        self,
        correlations: tuple[Correlation, ...],
        timelines: tuple[Timeline, ...],
        patterns: tuple[Pattern, ...],
    ) -> tuple[Explanation, ...]:
        timeline_by_entity = {item.subject_entity_id: item for item in timelines}
        pattern_by_entity = {
            entity_id: pattern
            for pattern in patterns for entity_id in pattern.subject_entity_ids
        }
        values = []
        for correlation in correlations:
            entity_id = correlation.entity_ids[0] if correlation.entity_ids else ""
            timeline = timeline_by_entity.get(entity_id)
            pattern = pattern_by_entity.get(entity_id)
            values.append(Explanation(
                f"explanation:{correlation.correlation_id}",
                correlation.correlation_id,
                (
                    f"Documents were linked because {correlation.reason} "
                    f"Evidence: {', '.join(correlation.evidence_ids)}. "
                    f"Normalized confidence is {correlation.confidence.normalized:.3f}."
                ),
                correlation.evidence_ids,
                correlation.confidence.components or (
                    ("normalized", correlation.confidence.normalized),
                ),
                (
                    f"{len(timeline.events)} chronological evidence events were ordered."
                    if timeline else "No multi-event timeline was required."
                ),
                pattern.description if pattern else "No supported historical pattern detected.",
                f"Correlation type {correlation.correlation_type} preserves canonical identity and source provenance.",
            ))
        return tuple(values)
