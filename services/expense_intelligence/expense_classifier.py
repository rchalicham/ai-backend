from __future__ import annotations

from .models import ExpenseCategory


class ExpenseClassifier:
    DEFAULT_RULES = (
        (ExpenseCategory.PHARMACY, ("pharmacy", "drug", "rx", "cvs", "walgreens")),
        (ExpenseCategory.HEALTHCARE, ("hospital", "clinic", "medical", "dental")),
        (ExpenseCategory.FUEL, ("fuel", "gas station", "shell", "exxon", "chevron")),
        (ExpenseCategory.RESTAURANTS, ("restaurant", "cafe", "pizza", "grill", "coffee")),
        (ExpenseCategory.GROCERIES, ("grocery", "market", "supermarket", "foods")),
        (ExpenseCategory.TRAVEL, ("airline", "hotel", "travel", "flight")),
        (ExpenseCategory.UTILITIES, ("electric", "water", "utility", "internet", "phone")),
        (ExpenseCategory.INSURANCE, ("insurance",)),
        (ExpenseCategory.RENT, ("rent",)),
        (ExpenseCategory.MORTGAGE, ("mortgage",)),
        (ExpenseCategory.ENTERTAINMENT, ("streaming", "cinema", "movie", "concert")),
        (ExpenseCategory.EDUCATION, ("school", "tuition", "course", "bookstore")),
        (ExpenseCategory.AUTOMOTIVE, ("automotive", "auto repair", "tire")),
        (ExpenseCategory.PETS, ("pet", "veterinary", "vet")),
        (ExpenseCategory.ELECTRONICS, ("electronics", "computer", "mobile device")),
        (ExpenseCategory.TAXES, ("tax", "revenue service")),
        (ExpenseCategory.BUSINESS, ("business", "office supply")),
        (ExpenseCategory.HOUSEHOLD, ("household", "home improvement", "hardware")),
        (ExpenseCategory.SHOPPING, ("store", "shop", "retail")),
    )

    def __init__(self, rules=None) -> None:
        self.rules = tuple(rules or self.DEFAULT_RULES)

    def classify(self, description: str, merchant: str = "") -> ExpenseCategory:
        value = f"{merchant} {description}".casefold()
        return next(
            (category for category, words in self.rules if any(word in value for word in words)),
            ExpenseCategory.UNKNOWN,
        )
