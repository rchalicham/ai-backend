from .models import QueryType


class QueryClassifier:
    KEYWORDS = (
        (QueryType.TIMELINE, ("when", "timeline", "history", "over time")),
        (QueryType.BUDGET, ("budget", "afford", "spending limit")),
        (QueryType.HEALTH, ("health", "nutrition", "calorie", "sodium")),
        (QueryType.EXPENSE, ("expense", "spent", "cost", "price")),
        (QueryType.CROSS_DOCUMENT, ("documents", "receipts", "across", "recurring")),
        (QueryType.KNOWLEDGE_GRAPH, ("relationship", "related", "graph", "path")),
        (QueryType.PRODUCT, ("product", "item", "brand", "category")),
        (QueryType.MERCHANT, ("merchant", "store", "retailer")),
        (QueryType.RECEIPT, ("receipt", "purchase", "transaction")),
        (QueryType.ANALYTICS, ("analytics", "trend", "aggregate")),
    )

    def classify(self, question: str) -> QueryType:
        normalized = " ".join(question.casefold().split())
        return next(
            (kind for kind, words in self.KEYWORDS if any(word in normalized for word in words)),
            QueryType.UNKNOWN,
        )
