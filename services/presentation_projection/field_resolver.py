from __future__ import annotations

from dataclasses import asdict, is_dataclass
from typing import Any

from .conflict_resolver import ProjectionConflictResolver
from .models import (
    ProjectionConflict, ProjectionDecision, ProjectionField, ProjectionMode,
    ProjectionProfile,
)
from .projection_confidence import ProjectionConfidenceEngine
from .projection_explainer import ProjectionExplainer


LABELS = {
    "merchant": "Merchant", "address": "Address", "phone": "Phone", "date": "Date",
    "payment_method": "Payment Method", "card_brand": "Card", "card_last_four": "Ending",
    "approval_code": "Approval Code", "invoice_number": "Invoice Number",
    "reference_number": "Reference Number", "total": "Total", "subtotal": "Subtotal",
    "tax": "Tax", "items": "Items", "products": "Products", "reasoning": "Reasoning",
}


class ProjectionFieldResolver:
    def __init__(self, conflict_resolver=None, confidence_engine=None, explainer=None):
        self.conflicts = conflict_resolver or ProjectionConflictResolver()
        self.confidence = confidence_engine or ProjectionConfidenceEngine()
        self.explainer = explainer or ProjectionExplainer()

    def resolve_all(self, parser: dict[str, Any], family_context, enterprise_reasoning,
                    product_intelligence, profile: ProjectionProfile, mode: ProjectionMode):
        parser_confidence = self._score((parser.get("confidence") or {}).get("overall"), .55)
        enterprise = self._enterprise_values(family_context, enterprise_reasoning, product_intelligence, profile)
        fields, conflicts = [], []
        keys = tuple(dict.fromkeys(key for _, section_keys in profile.sections for key in section_keys))
        for key in keys:
            parser_value = self._parser_value(parser, key)
            enterprise_value, enterprise_confidence, evidence = enterprise.get(key, (None, 0.0, ()))
            displayed, source, reason = self.conflicts.resolve(
                parser_value, enterprise_value, mode=mode,
                prefer_enterprise=key in profile.prefer_enterprise_fields,
                parser_confidence=parser_confidence, enterprise_confidence=enterprise_confidence,
            )
            confidence = self.confidence.calculate(source, parser=parser_confidence,
                                                   enterprise=enterprise_confidence)
            decision = ProjectionDecision(key, source, reason, mode)
            explanation = self.explainer.explain(key, source, reason, evidence)
            fields.append(ProjectionField(key, LABELS.get(key, key.replace("_", " ").title()),
                                          parser_value, enterprise_value, displayed, source,
                                          confidence, tuple(evidence), decision, explanation))
            if self._different(parser_value, enterprise_value):
                conflicts.append(ProjectionConflict(key, parser_value, enterprise_value, source, reason))
        return tuple(fields), tuple(conflicts)

    def _enterprise_values(self, context, reasoning, products, profile):
        result = {}
        candidates = tuple(getattr(context, "entity_candidates", ()) or ())
        merchants = tuple(getattr(context, "merchant_candidates", ()) or ())
        addresses = tuple(getattr(context, "address_candidates", ()) or ())
        payments = tuple(getattr(context, "payment_candidates", ()) or ())
        relationships = tuple(getattr(context, "key_value_relationships", ()) or ())
        if merchants:
            result["merchant"] = self._candidate_value(merchants[0])
        if addresses:
            value = "\n".join(dict.fromkeys(str(item.value) for item in addresses if item.value))
            result["address"] = (value, max(item.confidence for item in addresses), tuple(item.candidate_id for item in addresses))
        mapping = {
            "payment_brand": "card_brand", "masked_pan": "card_last_four",
            "approval_code": "approval_code", "authorization_code": "approval_code",
            "entry_method": "payment_method", "reference_number": "reference_number",
        }
        for candidate in payments:
            entity_type = getattr(candidate.entity_type, "value", candidate.entity_type)
            key = mapping.get(str(entity_type))
            if key and (key not in result or candidate.confidence > result[key][1]):
                value = candidate.value
                if key == "card_last_four":
                    digits = "".join(char for char in str(value) if char.isdigit())
                    value = digits[-4:] if digits else value
                result[key] = (value, candidate.confidence, (candidate.candidate_id,))
        for candidate in candidates:
            entity_type = str(getattr(candidate.entity_type, "value", candidate.entity_type))
            if entity_type == "date" and "date" not in result:
                result["date"] = self._candidate_value(candidate)
            if entity_type == "financial_amount" and "total" not in result:
                result["total"] = self._candidate_value(candidate)
        for relationship in relationships:
            key_text = str(relationship.key).lower()
            target = "total" if any(term in key_text for term in ("sale amount", "total", "amount due")) else \
                "subtotal" if "subtotal" in key_text else "tax" if "tax" in key_text else \
                "invoice_number" if "invoice" in key_text else "approval_code" if "approval" in key_text else \
                "reference_number" if any(term in key_text for term in ("reference", "batch", "seq")) else None
            if target:
                result[target] = (relationship.value, relationship.confidence, (relationship.relationship_id,))
        if profile.items_expected:
            enrichments = tuple(getattr(products, "enrichments", ()) or ())
            if enrichments:
                result["products"] = (tuple(self._to_dict(item) for item in enrichments), .8,
                                      tuple(str(getattr(item, "enrichment_id", "")) for item in enrichments))
        else:
            result["items"] = ((), 1.0, ("family-profile:no-item-table",))
            result["products"] = ((), 1.0, ("family-profile:no-products",))
            result.setdefault("subtotal", ("", 1.0, ("family-profile:not-applicable",)))
            result.setdefault("tax", ("", 1.0, ("family-profile:not-applicable",)))
        decision = getattr(reasoning, "decision", None)
        if decision:
            result["reasoning"] = (getattr(decision, "answer", ""),
                                   getattr(getattr(decision, "confidence", None), "overall", 0.0),
                                   tuple(getattr(decision, "evidence_ids", ()) or ()))
        return result

    @staticmethod
    def _candidate_value(candidate):
        return candidate.value, candidate.confidence, (candidate.candidate_id,)

    @staticmethod
    def _parser_value(parser, key):
        aliases = {
            "merchant": ("company", "merchant", "storeName"), "address": ("storeAddress", "address"),
            "phone": ("phone",), "date": ("purchaseDate", "transactionDate", "date"),
            "payment_method": ("paymentMethod",), "card_brand": ("cardUsed",),
            "card_last_four": ("cardLast4", "lastFour"), "approval_code": ("approvalCode",),
            "invoice_number": ("invoiceNumber", "invoice"), "reference_number": ("referenceNumber",),
            "total": ("total",), "subtotal": ("subTotal", "subtotal"), "tax": ("tax",),
            "items": ("items",), "products": ("products",), "reasoning": (),
        }
        if key == "card_brand":
            return (parser.get("paymentCard") or {}).get("brand") or next((parser.get(name) for name in aliases[key] if parser.get(name)), "")
        if key == "card_last_four":
            return (parser.get("paymentCard") or {}).get("last4") or next((parser.get(name) for name in aliases[key] if parser.get(name)), "")
        return next((parser.get(name) for name in aliases.get(key, ()) if parser.get(name) not in (None, "")), "")

    @staticmethod
    def _different(left, right):
        return left not in (None, "", (), []) and right not in (None, "", (), []) and str(left).strip().lower() != str(right).strip().lower()

    @staticmethod
    def _score(value, default):
        try:
            score = float(value)
            return score / 100 if score > 1 else score
        except (TypeError, ValueError):
            return default

    @staticmethod
    def _to_dict(value):
        return asdict(value) if is_dataclass(value) else value

