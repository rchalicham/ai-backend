from __future__ import annotations

from .models import ProjectionSection


class BusinessViewBuilder:
    def build(self, profile, fields):
        by_key = {field.key: field for field in fields}
        sections = []
        for section_key, field_keys in profile.sections:
            section_fields = tuple(by_key[key] for key in field_keys if key in by_key)
            visible = section_key != "items" or profile.items_expected
            sections.append(ProjectionSection(section_key, section_key.replace("_", " ").title(),
                                              section_fields, visible,
                                              "No purchased items" if section_key == "items" and not profile.items_expected else ""))
        return tuple(sections)

