from __future__ import annotations

from statistics import fmean, pvariance

from .models import CanonicalProduct, PricingProfile


class ProductPricingEngine:
    def profile(
        self,
        observed_price: float | None,
        product: CanonicalProduct | None = None,
        currency: str = "",
    ) -> PricingProfile:
        history = product.pricing.historical_prices if product is not None else ()
        values = (*history, observed_price) if observed_price is not None else history
        return PricingProfile(
            observed_price=observed_price,
            historical_prices=history,
            average_price=fmean(values) if values else None,
            typical_range=(min(values), max(values)) if values else (),
            price_variance=pvariance(values) if len(values) > 1 else 0.0 if values else None,
            currency=currency or (product.pricing.currency if product is not None else ""),
        )

