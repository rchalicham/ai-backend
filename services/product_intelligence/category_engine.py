from __future__ import annotations

from .models import CanonicalProduct, ProductCategory, ProductDepartment


class ProductCategoryEngine:
    def assign(
        self, product: CanonicalProduct | None, classification: str,
    ) -> tuple[ProductDepartment, ProductCategory, ProductCategory | None, float]:
        if product is not None:
            return product.department, product.category, product.subcategory, 1.0
        department = ProductDepartment(classification)
        return department, ProductCategory("Unknown", parent=classification), None, 0.0

