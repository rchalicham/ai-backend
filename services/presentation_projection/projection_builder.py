from __future__ import annotations

from .business_view_builder import BusinessViewBuilder
from .diagnostics import ProjectionDiagnosticsFactory
from .field_resolver import ProjectionFieldResolver
from .models import BusinessProjection, ProjectionMetadata, ProjectionSource
from .projection_confidence import ProjectionConfidenceEngine


class ProjectionBuilder:
    def __init__(self, field_resolver=None, view_builder=None, confidence_engine=None):
        self.field_resolver = field_resolver or ProjectionFieldResolver()
        self.view_builder = view_builder or BusinessViewBuilder()
        self.confidence_engine = confidence_engine or ProjectionConfidenceEngine()

    def build(self, *, parser, family_context, enterprise_reasoning, product_intelligence,
              profile, mode, document_id):
        fields, conflicts = self.field_resolver.resolve_all(parser, family_context, enterprise_reasoning,
                                                            product_intelligence, profile, mode)
        sections = self.view_builder.build(profile, fields)
        overall = sum(field.confidence.display for field in fields) / len(fields) if fields else 0.0
        confidence = self.confidence_engine.calculate(ProjectionSource.HYBRID, parser=overall, enterprise=overall)
        metadata = ProjectionMetadata(f"projection:{document_id}", document_id, profile.family,
                                      profile.business_view, profile.profile_id, mode)
        return BusinessProjection(metadata, sections, fields, conflicts, confidence,
                                  ProjectionDiagnosticsFactory.create())

