from __future__ import annotations

from .family_registry import DocumentFamilyRegistry
from .models import DocumentFamily, FamilyProfile


class DocumentFamilyRepository:
    def __init__(self, registry: DocumentFamilyRegistry | None = None) -> None:
        self.registry = registry or DocumentFamilyRegistry()

    def load_profile(self, family: DocumentFamily | str) -> FamilyProfile:
        return self.registry.profile(family)

    def save_profile(self, profile: FamilyProfile) -> FamilyProfile:
        self.registry.register(profile)
        return profile

    def list_profiles(self) -> tuple[FamilyProfile, ...]:
        return self.registry.profiles()
