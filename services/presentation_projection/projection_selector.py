from __future__ import annotations

from .migration_controller import ProjectionMigrationController
from .projection_registry import ProjectionRegistry


class ProjectionSelector:
    def __init__(self, registry=None, migration_controller=None):
        self.registry = registry or ProjectionRegistry()
        self.migration_controller = migration_controller or ProjectionMigrationController()

    def select(self, family: str, **options):
        return self.registry.resolve(family), self.migration_controller.select_mode(family=family, **options)

