from __future__ import annotations

from .models import ProjectionMode, ProjectionSource


class ProjectionConflictResolver:
    def resolve(self, parser_value, enterprise_value, *, mode: ProjectionMode,
                prefer_enterprise=False, parser_confidence=0.0, enterprise_confidence=0.0):
        has_parser = parser_value not in (None, "", (), [])
        has_enterprise = enterprise_value not in (None, "", (), [])
        if mode in {ProjectionMode.PARSER_ONLY, ProjectionMode.SHADOW}:
            return parser_value, ProjectionSource.PARSER if has_parser else ProjectionSource.NONE, "migration mode preserves parser display"
        if mode is ProjectionMode.ENTERPRISE_ONLY:
            return enterprise_value, ProjectionSource.ENTERPRISE if has_enterprise else ProjectionSource.NONE, "enterprise-only migration mode"
        if has_enterprise and (prefer_enterprise or not has_parser or enterprise_confidence >= parser_confidence):
            return enterprise_value, ProjectionSource.ENTERPRISE, "enterprise semantic evidence is stronger for this family"
        if has_parser:
            return parser_value, ProjectionSource.PARSER, "parser value retained because enterprise evidence is absent or weaker"
        return enterprise_value, ProjectionSource.ENTERPRISE if has_enterprise else ProjectionSource.NONE, "only available value selected"

