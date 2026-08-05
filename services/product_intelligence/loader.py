from __future__ import annotations

import json
from typing import Any

from .models import (
    Brand,
    CanonicalProduct,
    Manufacturer,
    NutritionProfile,
    PackageType,
    PricingProfile,
    ProductAlias,
    ProductCategory,
    ProductDepartment,
    ProductVersion,
    UnitOfMeasure,
)


class ProductLoader:
    def from_json(self, payload: str) -> CanonicalProduct:
        return self.from_dict(json.loads(payload))

    def from_dict(self, data: dict[str, Any]) -> CanonicalProduct:
        version = data.get("version") or {}
        return CanonicalProduct(
            product_id=str(data.get("product_id") or data.get("productId") or ""),
            canonical_name=str(data.get("canonical_name") or data.get("canonicalName") or ""),
            aliases=tuple(ProductAlias(**item) for item in data.get("aliases", ())),
            department=ProductDepartment(**(data.get("department") or {"name": "Unknown"})),
            category=ProductCategory(**(data.get("category") or {"name": "Unknown"})),
            subcategory=(
                ProductCategory(**data["subcategory"]) if data.get("subcategory") else None
            ),
            brand=Brand(**(data.get("brand") or {"name": "Unknown Brand"})),
            manufacturer=Manufacturer(**(data.get("manufacturer") or {"name": "Unknown"})),
            package_type=PackageType(**(data.get("package_type") or data.get("packageType") or {})),
            unit_of_measure=UnitOfMeasure(**(data.get("unit_of_measure") or data.get("unitOfMeasure") or {})),
            nutrition=NutritionProfile(**(data.get("nutrition") or {})),
            pricing=PricingProfile(**(data.get("pricing") or {})),
            metadata=tuple((str(key), value) for key, value in (data.get("metadata") or {}).items()),
            version=ProductVersion(**version),
        )

