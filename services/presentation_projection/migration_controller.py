from __future__ import annotations

import os

from .models import ProjectionMode


class ProjectionMigrationController:
    def __init__(self, default_mode: ProjectionMode | str | None = None):
        raw = default_mode or os.getenv("PRESENTATION_PROJECTION_MODE", "hybrid")
        try:
            self.default_mode = raw if isinstance(raw, ProjectionMode) else ProjectionMode(str(raw).lower())
        except ValueError:
            self.default_mode = ProjectionMode.HYBRID

    def select_mode(self, *, tenant_id: str = "", family: str = "", feature_flags=None,
                    tenant_overrides=None, family_overrides=None) -> ProjectionMode:
        flags = feature_flags or {}
        value = (family_overrides or {}).get(family) or (tenant_overrides or {}).get(tenant_id) or flags.get("presentationProjectionMode")
        try:
            return ProjectionMode(str(value).lower()) if value else self.default_mode
        except ValueError:
            return self.default_mode

