from __future__ import annotations

from .models import ProjectionProfile


def _profile(family: str, view: str, *, items: bool = True, extra=()) -> ProjectionProfile:
    sections = [
        ("summary", ("merchant", "date", "total")),
        ("merchant", ("merchant", "address", "phone")),
        ("payment", ("payment_method", "card_brand", "card_last_four", "approval_code")),
        ("financial", ("subtotal", "tax", "total")),
    ]
    if items:
        sections.append(("items", ("items", "products")))
    sections.extend((("references", ("invoice_number", "reference_number")), ("reasoning", ("reasoning",))))
    return ProjectionProfile(
        f"{family}-projection-v1", family, view, tuple(sections),
        tuple(extra), items,
    )


BUILTIN_PROFILES = (
    _profile("retail_receipt", "retail_receipt_view"),
    _profile("restaurant_receipt", "restaurant_receipt_view"),
    _profile("fuel_receipt", "fuel_receipt_view"),
    _profile("pharmacy_receipt", "pharmacy_receipt_view", extra=("merchant", "total", "payment_method", "reference_number")),
    _profile("payment_slip", "payment_slip_view", items=False, extra=("merchant", "address", "total", "payment_method", "card_brand", "card_last_four", "approval_code")),
    _profile("credit_card_slip", "credit_card_slip_view", items=False, extra=("merchant", "total", "payment_method", "card_brand", "card_last_four", "approval_code")),
    _profile("refund_receipt", "refund_view"),
    _profile("return_receipt", "refund_view"),
    _profile("invoice", "invoice_view", extra=("merchant", "invoice_number", "total")),
    _profile("statement", "statement_view", items=False),
    _profile("warranty", "warranty_view", items=False),
    _profile("medical_bill", "medical_bill_view", items=False),
    _profile("insurance_eob", "insurance_eob_view", items=False),
    _profile("donation_receipt", "donation_receipt_view", items=False),
    _profile("unknown", "unknown_view"),
)


class ProjectionRegistry:
    def __init__(self, profiles=BUILTIN_PROFILES):
        self._profiles = {profile.family: profile for profile in profiles}

    def register(self, profile: ProjectionProfile) -> None:
        self._profiles[profile.family] = profile

    def resolve(self, family: str) -> ProjectionProfile:
        return self._profiles.get(str(family), self._profiles["unknown"])

    def profiles(self) -> tuple[ProjectionProfile, ...]:
        return tuple(self._profiles.values())
