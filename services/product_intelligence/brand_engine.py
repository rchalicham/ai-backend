from __future__ import annotations

from .models import Brand, CanonicalProduct, Manufacturer


class ProductBrandEngine:
    STORE_BRANDS = {
        "great value": ("Great Value", "Walmart"),
        "kirkland": ("Kirkland", "Costco"),
        "member s mark": ("Member's Mark", "Sam's Club"),
        "365": ("365", "Whole Foods Market"),
        "good gather": ("Good & Gather", "Target"),
    }

    def identify(
        self, product: CanonicalProduct | None, normalized_description: str, merchant_key: str = "",
    ) -> tuple[Brand, Manufacturer, float, str]:
        if product is not None and product.brand.name != "Unknown Brand":
            return product.brand, product.manufacturer, 1.0, "approved product knowledge"
        text = normalized_description.casefold().replace("&", " ")
        for alias, (name, manufacturer) in self.STORE_BRANDS.items():
            if alias in text:
                return Brand(name, store_brand=True, merchant_keys=(merchant_key,) if merchant_key else ()), Manufacturer(manufacturer), 0.85, "store-brand dictionary"
        return Brand("Unknown Brand"), Manufacturer("Unknown"), 0.0, "no approved brand match"

