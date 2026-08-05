from __future__ import annotations

from dataclasses import fields, replace

from .models import (
    CanonicalProduct,
    ProductRepositoryIndex,
    ProductVersionComparison,
    utc_now,
)


class ProductRepository:
    """Append-only approved product knowledge keyed by canonical product identity."""

    def __init__(self) -> None:
        self._products: dict[str, list[CanonicalProduct]] = {}

    def load_products(
        self, product_id: str = "", version: int | None = None, include_archived: bool = False,
    ) -> tuple[CanonicalProduct, ...]:
        if product_id:
            history = self._products.get(product_id, ())
            if version is None:
                latest = next(
                    (item for item in reversed(history) if include_archived or item.version.status == "active"),
                    None,
                )
                values = (latest,) if latest is not None else ()
            else:
                values = tuple(
                    item for item in history if item.version.entity_version == version
                )
        else:
            values = tuple(history[-1] for _, history in sorted(self._products.items()) if history)
        return values if include_archived else tuple(
            item for item in values if item.version.status == "active"
        )

    def save_products(self, products: CanonicalProduct | tuple[CanonicalProduct, ...]) -> tuple[CanonicalProduct, ...]:
        values = (products,) if isinstance(products, CanonicalProduct) else tuple(products)
        saved = []
        for product in values:
            if not product.product_id:
                raise ValueError("canonical_product_requires_identity")
            if self._products.get(product.product_id):
                raise ValueError("product_already_exists_use_version_products")
            value = replace(product, version=replace(
                product.version, entity_version=1, status="active",
                updated_at=utc_now(), supersedes_version=None,
            ))
            self._products[product.product_id] = [value]
            saved.append(value)
        return tuple(saved)

    def version_products(
        self, product: CanonicalProduct, expected_version: int | None = None,
    ) -> CanonicalProduct:
        history = self._products.get(product.product_id, [])
        current = history[-1] if history else None
        current_version = current.version.entity_version if current else 0
        if expected_version is not None and expected_version != current_version:
            raise ValueError("product_version_conflict")
        value = replace(product, version=replace(
            product.version,
            entity_version=current_version + 1,
            status="active",
            created_at=current.version.created_at if current else product.version.created_at,
            updated_at=utc_now(),
            supersedes_version=current_version or None,
        ))
        self._products.setdefault(product.product_id, []).append(value)
        return value

    def archive_products(self, product_id: str, version: int | None = None) -> CanonicalProduct:
        history = self._products.get(product_id, [])
        value = next((
            item for item in reversed(history)
            if version is None or item.version.entity_version == version
        ), None)
        if value is None:
            raise KeyError("product_not_found")
        archived = replace(value, version=replace(value.version, status="archived", updated_at=utc_now()))
        history[history.index(value)] = archived
        return archived

    def compare_products(
        self, product_id: str, from_version: int, to_version: int,
    ) -> ProductVersionComparison:
        before = self.load_products(product_id, from_version, include_archived=True)
        after = self.load_products(product_id, to_version, include_archived=True)
        if not before or not after:
            raise KeyError("product_version_not_found")
        ignored = {"version"}
        changed = tuple(
            item.name for item in fields(CanonicalProduct)
            if item.name not in ignored and getattr(before[0], item.name) != getattr(after[0], item.name)
        )
        return ProductVersionComparison(product_id, from_version, to_version, changed)

    def index(self) -> ProductRepositoryIndex:
        latest = tuple(
            (product_id, history[-1].version.entity_version)
            for product_id, history in sorted(self._products.items()) if history
        )
        return ProductRepositoryIndex(
            product_ids=tuple(product_id for product_id, _ in latest),
            versions=latest,
        )

    loadProducts = load_products
    saveProducts = save_products
    versionProducts = version_products
    archiveProducts = archive_products
    compareProducts = compare_products
