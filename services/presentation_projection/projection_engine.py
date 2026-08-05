from __future__ import annotations

from .projection_builder import ProjectionBuilder
from .projection_selector import ProjectionSelector


class PresentationProjectionEngine:
    def __init__(self, selector=None, builder=None):
        self.selector = selector or ProjectionSelector()
        self.builder = builder or ProjectionBuilder()

    def project(self, *, parser, document_family_context, enterprise_reasoning=None,
                product_intelligence=None, document_id="", **selection_options):
        family = str(getattr(getattr(document_family_context, "activation", None), "family", "unknown"))
        if "." in family:
            family = family.rsplit(".", 1)[-1].lower()
        family_value = getattr(getattr(document_family_context, "activation", None), "family", None)
        family = getattr(family_value, "value", family)
        profile, mode = self.selector.select(family, **selection_options)
        return self.builder.build(parser=dict(parser or {}), family_context=document_family_context,
                                  enterprise_reasoning=enterprise_reasoning,
                                  product_intelligence=product_intelligence,
                                  profile=profile, mode=mode, document_id=document_id or "unknown")

    def safe_project(self, **kwargs):
        return self.project(**kwargs)

