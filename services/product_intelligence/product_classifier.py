from __future__ import annotations

from .models import CanonicalProduct


class ProductClassifier:
    DEFAULT_CLASSES = (
        "Food", "Household", "Personal Care", "Medicine", "Electronics",
        "Office", "Pet", "Clothing", "Automotive", "Garden", "Unknown",
    )

    def classify(self, product: CanonicalProduct | None, normalized_description: str) -> tuple[str, float]:
        if product is not None and product.department.name:
            return product.department.name, 1.0
        text = normalized_description.casefold()
        keywords = {
            "Food": ("milk", "egg", "bread", "banana", "chicken", "beef", "yogurt", "oil"),
            "Household": ("detergent", "cleaner", "towel", "laundry"),
            "Personal Care": ("shampoo", "soap", "toothpaste"),
            "Medicine": ("tablet", "capsule", "medicine"),
            "Pet": ("dog food", "cat food", "pet"),
        }
        for classification, values in keywords.items():
            if any(value in text for value in values):
                return classification, 0.65
        return "Unknown", 0.0

