from .models import ProjectionDiagnostics


class ProjectionDiagnosticsFactory:
    @staticmethod
    def create(*warnings: str) -> ProjectionDiagnostics:
        return ProjectionDiagnostics(warnings=tuple(filter(None, warnings)))

