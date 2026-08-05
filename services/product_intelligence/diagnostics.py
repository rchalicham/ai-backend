from __future__ import annotations

from .models import ProductDiagnostic, ProductDiagnostics, ProductEnrichment


class ProductDiagnosticsEngine:
    def create(self, enrichments: tuple[ProductEnrichment, ...]) -> ProductDiagnostics:
        unmatched = tuple(
            ProductDiagnostic(
                "canonical_product_not_matched",
                "No approved canonical product was asserted; original item remains unchanged.",
                "warning",
                item.item_index,
            )
            for item in enrichments if item.canonical_product is None
        )
        return ProductDiagnostics(
            warnings=unmatched,
            information=(
                ProductDiagnostic(
                    "product_sidecar_evaluated",
                    f"Enriched {len(enrichments)} extracted line item(s) without changing parser output.",
                ),
            ),
        )

    def failed(self, error: Exception) -> ProductDiagnostics:
        return ProductDiagnostics(errors=(
            ProductDiagnostic(
                "product_sidecar_failed",
                f"Product Intelligence failed safely: {error.__class__.__name__}.",
                "error",
            ),
        ))

