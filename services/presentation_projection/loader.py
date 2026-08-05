from .projection_registry import ProjectionRegistry


class ProjectionProfileLoader:
    def load(self):
        return ProjectionRegistry().profiles()

