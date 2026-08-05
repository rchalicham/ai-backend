from __future__ import annotations

from .family_profiles import builtin_family_profiles
from .models import DocumentFamily, FamilyProfile


class DocumentFamilyRegistry:
    def __init__(self, profiles: tuple[FamilyProfile, ...] | None = None) -> None:
        self._profiles = {profile.family: profile for profile in (profiles or builtin_family_profiles())}

    def profile(self, family: DocumentFamily | str) -> FamilyProfile:
        try:
            key = family if isinstance(family, DocumentFamily) else DocumentFamily(str(family))
        except ValueError:
            key = DocumentFamily.UNKNOWN
        return self._profiles.get(key, self._profiles[DocumentFamily.UNKNOWN])

    def register(self, profile: FamilyProfile) -> None:
        self._profiles[profile.family] = profile

    def profiles(self) -> tuple[FamilyProfile, ...]:
        return tuple(self._profiles.values())
