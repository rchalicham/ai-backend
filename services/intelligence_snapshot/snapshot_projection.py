from .models import SnapshotProjection, thaw


class SnapshotProjectionEngine:
    TAB_FIELDS = (
        ("pipeline", "Pipeline"), ("document_family", "Document Family"),
        ("grammar", "Grammar"), ("constraints", "Constraint Solver"),
        ("product_intelligence", "Product Intelligence"),
        ("cross_document_intelligence", "Cross-Document Intelligence"),
        ("enterprise_reasoning", "Enterprise Reasoning"),
        ("business_projection", "Business Projection"),
        ("document_review", "Document Review"),
    )

    def project(self, snapshot):
        tabs = tuple(label for field, label in self.TAB_FIELDS if thaw(getattr(snapshot.context, field)))
        reference_tabs = {item.artifact_type for item in snapshot.references}
        if "enterprise_graph" in reference_tabs: tabs += ("Enterprise Knowledge Graph",)
        if "enterprise_learning" in reference_tabs: tabs += ("Enterprise Learning",)
        return SnapshotProjection(snapshot.header.snapshot_id, snapshot.header.receipt_id,
                                  snapshot.header.version.number, tabs, snapshot.context,
                                  snapshot.metadata, snapshot.confidence, snapshot.references)
