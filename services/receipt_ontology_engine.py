from __future__ import annotations

import hashlib
import re
from collections import defaultdict
from typing import Any


RECEIPT_ONTOLOGY_ENTITY_TYPES = (
    "MERCHANT",
    "ADDRESS",
    "PHONE",
    "DATE",
    "PRODUCT",
    "QUANTITY",
    "MONEY",
    "TOTAL",
    "TAX",
    "PAYMENT",
    "LAST_FOUR",
    "APPROVAL_CODE",
    "FOOTER",
)

STATE_ORDER = {"HEADER": 0, "ITEMS": 1, "TOTALS": 2, "PAYMENT": 3, "FOOTER": 4}


def compact(value: Any) -> str:
    return re.sub(r"\s+", " ", str(value or "")).strip()


def amount(value: Any) -> str:
    text = str(value or "").replace("$", "").replace(",", ".")
    match = re.search(r"-?\d{1,7}(?:\.\d{2})\b", text)
    return match.group(0) if match else ""


def numeric(value: Any) -> float:
    try:
        parsed = amount(value)
        return float(parsed) if parsed else 0.0
    except ValueError:
        return 0.0


def safe_confidence(value: Any, default: float = 0.0) -> float:
    try:
        return round(max(0.0, min(1.0, float(value))), 3)
    except (TypeError, ValueError):
        return default


def entity_id(entity_type: str, value: Any, index: int) -> str:
    digest = hashlib.sha1(f"{entity_type}:{compact(value)}:{index}".encode("utf-8")).hexdigest()[:12]
    return f"{entity_type.lower()}-{digest}"


class ReceiptOntologyEngine:
    """Builds a generic receipt ontology from OCR, layout, state, and semantic outputs.

    The ontology intentionally contains only document-level semantics. It does not
    contain merchant lookup tables or merchant-specific correction rules.
    """

    def build(
        self,
        *,
        lines: list[Any] | None = None,
        items: list[dict[str, Any]] | None = None,
        facts: dict[str, Any] | None = None,
        entity_result: dict[str, Any] | None = None,
        section_extraction: dict[str, Any] | None = None,
        merchant_resolution: dict[str, Any] | None = None,
        duplicate_diagnostics: list[dict[str, Any]] | None = None,
    ) -> dict[str, Any]:
        lines = lines or []
        items = items or []
        facts = facts or {}
        entity_result = entity_result or {}
        section_extraction = section_extraction or {}
        merchant_resolution = merchant_resolution or {}
        duplicate_diagnostics = duplicate_diagnostics or []
        entities: list[dict[str, Any]] = []
        relationships: list[dict[str, Any]] = []
        state_machine = section_extraction.get("documentStateMachine", {}) or {}
        line_state = self._line_state_index(state_machine)
        regions = section_extraction.get("regions", []) or []
        region_index = self._region_index(regions)
        entity_fields = entity_result.get("fields", {}) or {}

        self._add_header_entities(entities, entity_fields, merchant_resolution, line_state, region_index)
        self._add_item_entities(entities, relationships, items, line_state, region_index)
        self._add_fact_entities(entities, facts, section_extraction, line_state, region_index)
        self._add_payment_entities(entities, entity_fields, section_extraction, line_state, region_index)
        self._add_footer_entities(entities, regions)
        line_classifications = self._line_classifications(lines, line_state, regions, section_extraction, entities)

        structural = self._structural_intelligence(lines, items, facts, section_extraction, entities, line_classifications)
        graph = self._graph(entities, relationships, structural)
        confidence = self._confidence(entities, structural, section_extraction)
        debug = self._debug_payload(section_extraction, graph, line_classifications, duplicate_diagnostics)
        learning = ReceiptPatternLearningEngine().build_learning_payload(
            lines=lines,
            entities=entities,
            structural=structural,
            section_extraction=section_extraction,
        )

        return {
            "schemaVersion": "receipt-ontology-v1",
            "architecture": "generalized-document-ontology",
            "entityTypes": list(RECEIPT_ONTOLOGY_ENTITY_TYPES),
            "entities": entities,
            "lineClassifications": line_classifications,
            "relationships": relationships,
            "structuralIntelligence": structural,
            "entityGraph": graph,
            "confidence": confidence,
            "debug": debug,
            "selfLearning": learning,
            "governance": {
                "merchantSpecificRules": False,
                "merchantSpecificTemplates": False,
                "lowConfidencePolicy": "unresolved",
                "parserIsolation": section_extraction.get("parserIsolation", {}),
            },
        }

    def _line_state_index(self, state_machine: dict[str, Any]) -> dict[int, dict[str, Any]]:
        index: dict[int, dict[str, Any]] = {}
        for entry in state_machine.get("lineStates", []) or []:
            try:
                index[int(entry.get("lineIndex"))] = entry
            except (TypeError, ValueError):
                continue
        return index

    def _region_index(self, regions: list[dict[str, Any]]) -> dict[str, list[dict[str, Any]]]:
        index: dict[str, list[dict[str, Any]]] = defaultdict(list)
        for region in regions:
            index[str(region.get("kind") or "unknown").lower()].append(region)
        return index

    def _add_entity(
        self,
        entities: list[dict[str, Any]],
        entity_type: str,
        value: Any,
        *,
        confidence: float,
        source: str,
        state: str = "",
        line_indexes: list[int] | None = None,
        bbox: dict[str, Any] | None = None,
        attributes: dict[str, Any] | None = None,
        unresolved_reason: str = "",
    ) -> dict[str, Any] | None:
        value_text = compact(value)
        confidence = safe_confidence(confidence)
        if not value_text and confidence >= 0.5:
            confidence = 0.0
        status = "resolved" if value_text and confidence >= 0.62 else "unresolved"
        entity = {
            "id": entity_id(entity_type, value_text or unresolved_reason, len(entities) + 1),
            "type": entity_type,
            "value": value_text,
            "confidence": confidence,
            "status": status,
            "source": source,
            "state": state,
            "lineIndexes": line_indexes or [],
            "bbox": bbox or {},
            "attributes": attributes or {},
        }
        if status == "unresolved":
            entity["unresolvedReason"] = unresolved_reason or "low_confidence_or_missing_value"
        entities.append(entity)
        return entity

    def _add_header_entities(
        self,
        entities: list[dict[str, Any]],
        fields: dict[str, Any],
        merchant_resolution: dict[str, Any],
        line_state: dict[int, dict[str, Any]],
        region_index: dict[str, list[dict[str, Any]]],
    ) -> None:
        merchant_confidence = safe_confidence(merchant_resolution.get("confidence", 0.0))
        merchant_value = merchant_resolution.get("merchant", "")
        if merchant_confidence < 0.62 and merchant_resolution.get("source") != "raw_ocr_preserved":
            merchant_value = ""
        self._add_entity(
            entities,
            "MERCHANT",
            merchant_value,
            confidence=merchant_confidence,
            source=merchant_resolution.get("source") or "ocr_header",
            state="HEADER",
            bbox=self._first_region_bbox(region_index, "header"),
            unresolved_reason="merchant_below_confidence_threshold",
        )
        for entity_type, field_name in (("ADDRESS", "storeAddress"), ("PHONE", "phone"), ("DATE", "date")):
            value = fields.get(field_name) or fields.get(field_name.lower()) or fields.get("address" if entity_type == "ADDRESS" else "purchaseDate")
            self._add_entity(
                entities,
                entity_type,
                value,
                confidence=0.82 if value else 0.0,
                source="generic_entity_extraction",
                state="HEADER",
                line_indexes=self._state_lines(line_state, "HEADER")[:3],
                unresolved_reason=f"{entity_type.lower()}_not_observed",
            )

    def _add_item_entities(
        self,
        entities: list[dict[str, Any]],
        relationships: list[dict[str, Any]],
        items: list[dict[str, Any]],
        line_state: dict[int, dict[str, Any]],
        region_index: dict[str, list[dict[str, Any]]],
    ) -> None:
        item_bbox = self._first_region_bbox(region_index, "items")
        item_lines = self._state_lines(line_state, "ITEMS")
        for index, item in enumerate(items):
            item_entity = self._add_entity(
                entities,
            "PRODUCT",
                item.get("name", ""),
                confidence=safe_confidence(item.get("confidence", item.get("weight", 0.74))),
                source="state_aware_item_parser",
                state="ITEMS",
                line_indexes=[item_lines[index]] if index < len(item_lines) else [],
                bbox=item_bbox,
                attributes={"ordinal": index + 1},
                unresolved_reason="product_name_below_confidence_threshold",
            )
            quantity_entity = self._add_entity(
                entities,
                "QUANTITY",
                item.get("qty") or item.get("count") or "1",
                confidence=0.84 if item.get("qty") or item.get("count") else 0.66,
                source="item_quantity_price_relationship",
                state="ITEMS",
                line_indexes=item_entity.get("lineIndexes", []) if item_entity else [],
                attributes={"itemOrdinal": index + 1},
            )
            money_entity = self._add_entity(
                entities,
                "MONEY",
                item.get("amount") or item.get("price"),
                confidence=safe_confidence(item.get("confidence", item.get("weight", 0.74))),
                source="right_aligned_item_amount",
                state="ITEMS",
                line_indexes=item_entity.get("lineIndexes", []) if item_entity else [],
                attributes={"role": "item_price", "itemOrdinal": index + 1},
                unresolved_reason="item_price_missing",
            )
            for child, relation in ((quantity_entity, "HAS_QUANTITY"), (money_entity, "HAS_PRICE")):
                if item_entity and child:
                    relationships.append({"from": item_entity["id"], "to": child["id"], "type": relation})

    def _add_fact_entities(
        self,
        entities: list[dict[str, Any]],
        facts: dict[str, Any],
        section_extraction: dict[str, Any],
        line_state: dict[int, dict[str, Any]],
        region_index: dict[str, list[dict[str, Any]]],
    ) -> None:
        totals_confidence = safe_confidence((section_extraction.get("totals") or {}).get("confidence", 0.0), 0.0)
        totals_bbox = self._first_region_bbox(region_index, "totals")
        for key, entity_type in (("subtotal", "TOTAL"), ("total", "TOTAL"), ("charge", "TOTAL"), ("tax", "TAX"), ("tip", "TOTAL")):
            if key not in facts and entity_type != "TAX":
                continue
            value = facts.get(key, "")
            self._add_entity(
                entities,
                entity_type,
                value,
                confidence=totals_confidence if value else 0.0,
                source="totals_region_parser",
                state="TOTALS",
                line_indexes=self._state_lines(line_state, "TOTALS"),
                bbox=totals_bbox,
                attributes={"role": key},
                unresolved_reason=f"{key}_not_observed",
            )

    def _add_payment_entities(
        self,
        entities: list[dict[str, Any]],
        fields: dict[str, Any],
        section_extraction: dict[str, Any],
        line_state: dict[int, dict[str, Any]],
        region_index: dict[str, list[dict[str, Any]]],
    ) -> None:
        payment_fields = ((section_extraction.get("payment") or {}).get("fields") or {})
        confidence = safe_confidence((section_extraction.get("payment") or {}).get("confidence", 0.0), 0.0)
        payment_bbox = self._first_region_bbox(region_index, "payment")
        for entity_type, field_names in (
            ("PAYMENT", ("paymentMethod", "cardUsed", "method")),
            ("LAST_FOUR", ("cardLast4", "lastFour", "last4")),
            ("APPROVAL_CODE", ("approvalCode", "approval")),
        ):
            value = next((payment_fields.get(name) or fields.get(name) for name in field_names if payment_fields.get(name) or fields.get(name)), "")
            self._add_entity(
                entities,
                entity_type,
                value,
                confidence=confidence if value else 0.0,
                source="payment_region_parser",
                state="PAYMENT",
                line_indexes=self._state_lines(line_state, "PAYMENT"),
                bbox=payment_bbox,
                unresolved_reason=f"{entity_type.lower()}_not_observed",
            )

    def _add_footer_entities(self, entities: list[dict[str, Any]], regions: list[dict[str, Any]]) -> None:
        for region in regions:
            if str(region.get("kind", "")).lower() != "footer":
                continue
            self._add_entity(
                entities,
                "FOOTER",
                region.get("text", ""),
                confidence=safe_confidence(region.get("confidence", 0.0)),
                source="footer_region_boundary",
                state="FOOTER",
                line_indexes=[line.get("index") for line in region.get("lines", []) if isinstance(line, dict)],
                bbox=region.get("bbox", {}),
            )

    def _structural_intelligence(
        self,
        lines: list[Any],
        items: list[dict[str, Any]],
        facts: dict[str, Any],
        section_extraction: dict[str, Any],
        entities: list[dict[str, Any]],
        line_classifications: list[dict[str, Any]],
    ) -> dict[str, Any]:
        state_machine = section_extraction.get("documentStateMachine", {}) or {}
        line_states = state_machine.get("lineStates", []) or []
        transitions = state_machine.get("transitions", []) or []
        state_sequence = [entry.get("state") for entry in line_states if entry.get("state")]
        rules = [
            self._rule_state_order(state_sequence),
            self._rule_transition(transitions, "ITEMS", "TOTALS", "totals_after_items"),
            self._rule_transition(transitions, "TOTALS", "PAYMENT", "payment_after_totals"),
            self._rule_transition(transitions, "PAYMENT", "FOOTER", "footer_after_payment", optional=True),
            self._rule_right_aligned_prices(section_extraction),
            self._rule_item_quantity_price_relationship(items),
            self._rule_arithmetic(facts, items, section_extraction),
            self._rule_impossible_product_rejection(line_classifications),
        ]
        score = sum(rule["confidence"] for rule in rules) / max(len(rules), 1)
        return {
            "schemaVersion": "receipt-structure-v1",
            "stateSequence": state_sequence,
            "transitions": transitions,
            "rules": rules,
            "confidence": round(score, 3),
            "constraints": {
                "totalsCannotContainProducts": True,
                "paymentCannotContainProducts": True,
                "footerIgnoredForItems": True,
                "productRowsRequireSemanticPriceRelationship": True,
                "impossibleProductRowsRejected": True,
            },
            "unresolvedEntities": [entity["id"] for entity in entities if entity.get("status") == "unresolved"],
        }

    def _rule_state_order(self, state_sequence: list[str]) -> dict[str, Any]:
        observed = [STATE_ORDER.get(state, -1) for state in state_sequence]
        monotonic = all(right >= left for left, right in zip(observed, observed[1:]) if left >= 0 and right >= 0)
        return {
            "name": "hierarchical_state_order",
            "valid": monotonic,
            "confidence": 0.96 if monotonic and observed else 0.42,
            "evidence": state_sequence,
        }

    def _rule_transition(self, transitions: list[dict[str, Any]], left: str, right: str, name: str, optional: bool = False) -> dict[str, Any]:
        found = any(item.get("from") == left and item.get("to") == right for item in transitions)
        confidence = 0.9 if found else (0.72 if optional else 0.44)
        return {"name": name, "valid": found or optional, "confidence": confidence, "evidence": transitions}

    def _rule_right_aligned_prices(self, section_extraction: dict[str, Any]) -> dict[str, Any]:
        regions = section_extraction.get("regions", []) or []
        item_lines = [line for region in regions if region.get("kind") == "items" for line in region.get("lines", [])]
        priced = [line for line in item_lines if amount(line.get("text", ""))]
        with_width = [line for line in priced if ((line.get("bbox") or {}).get("width") or 0) > 0]
        valid_ratio = len(with_width) / max(len(priced), 1) if priced else 0.0
        return {
            "name": "prices_align_right_or_have_price_geometry",
            "valid": valid_ratio >= 0.5 or not priced,
            "confidence": round(0.62 + (valid_ratio * 0.32), 3) if priced else 0.58,
            "evidence": {"pricedItemRows": len(priced), "rowsWithGeometry": len(with_width)},
        }

    def _rule_item_quantity_price_relationship(self, items: list[dict[str, Any]]) -> dict[str, Any]:
        valid = [item for item in items if compact(item.get("name")) and amount(item.get("amount") or item.get("price"))]
        ratio = len(valid) / max(len(items), 1) if items else 0.0
        return {
            "name": "product_rows_contain_name_quantity_price_relationship",
            "valid": ratio >= 0.8 if items else False,
            "confidence": round(0.38 + (ratio * 0.58), 3) if items else 0.28,
            "evidence": {"itemRows": len(items), "validRelationships": len(valid)},
        }

    def _rule_impossible_product_rejection(self, line_classifications: list[dict[str, Any]]) -> dict[str, Any]:
        impossible = [
            line for line in line_classifications
            if any(reason in line.get("reasons", []) for reason in (
                "receipt_level_total_keyword",
                "payment_semantics",
                "footer_or_policy_semantics",
                "currency_or_tender_semantics",
                "locked_non_item_region",
            ))
        ]
        bad_products = [line for line in impossible if line.get("entityType") == "PRODUCT"]
        return {
            "name": "impossible_product_rejection",
            "valid": not bad_products,
            "confidence": 0.96 if impossible and not bad_products else (0.62 if not bad_products else 0.18),
            "evidence": {
                "impossibleRows": len(impossible),
                "badProductRows": [line.get("text") for line in bad_products],
            },
        }

    def _rule_arithmetic(self, facts: dict[str, Any], items: list[dict[str, Any]], section_extraction: dict[str, Any]) -> dict[str, Any]:
        checks = ((section_extraction.get("validation") or {}).get("arithmeticChecks") or [])
        if checks:
            valid_ratio = sum(1 for check in checks if check.get("valid")) / max(len(checks), 1)
            return {
                "name": "totals_arithmetic_validation",
                "valid": valid_ratio >= 0.66,
                "confidence": round(0.42 + valid_ratio * 0.54, 3),
                "evidence": checks,
            }
        subtotal = numeric(facts.get("subtotal"))
        item_sum = sum(numeric(item.get("amount") or item.get("price")) for item in items)
        valid = bool(subtotal and item_sum and abs(subtotal - item_sum) <= max(0.35, subtotal * 0.05))
        return {
            "name": "totals_arithmetic_validation",
            "valid": valid,
            "confidence": 0.82 if valid else 0.48,
            "evidence": {"itemSum": round(item_sum, 2), "subtotal": round(subtotal, 2) if subtotal else None},
        }

    def _confidence(self, entities: list[dict[str, Any]], structural: dict[str, Any], section_extraction: dict[str, Any]) -> dict[str, Any]:
        resolved = [entity for entity in entities if entity.get("status") == "resolved"]
        entity_score = sum(entity.get("confidence", 0.0) for entity in entities) / max(len(entities), 1)
        section_confidence = section_extraction.get("confidence", {}) or {}
        arithmetic = safe_confidence(section_confidence.get("arithmetic", 0.0), 0.0)
        semantic = safe_confidence(section_confidence.get("semantic", structural.get("confidence", 0.0)), 0.0)
        overall = (entity_score * 0.38) + (structural.get("confidence", 0.0) * 0.32) + (arithmetic * 0.16) + (semantic * 0.14)
        return {
            "overall": round(overall, 3),
            "entity": round(entity_score, 3),
            "structural": safe_confidence(structural.get("confidence", 0.0)),
            "arithmetic": arithmetic,
            "semantic": semantic,
            "resolvedEntityRatio": round(len(resolved) / max(len(entities), 1), 3),
        }

    def _graph(self, entities: list[dict[str, Any]], relationships: list[dict[str, Any]], structural: dict[str, Any]) -> dict[str, Any]:
        nodes = [{"id": "receipt", "type": "RECEIPT", "properties": {"documentType": "receipt"}}]
        edges = []
        for entity in entities:
            nodes.append({
                "id": entity["id"],
                "type": entity["type"],
                "properties": {
                    "value": entity.get("value", ""),
                    "confidence": entity.get("confidence", 0.0),
                    "status": entity.get("status", "unresolved"),
                    "state": entity.get("state", ""),
                },
            })
            edges.append({"from": "receipt", "to": entity["id"], "type": f"HAS_{entity['type']}"})
        edges.extend(relationships)
        for rule in structural.get("rules", []):
            rule_id = entity_id("STRUCTURAL_RULE", rule.get("name"), len(nodes))
            nodes.append({"id": rule_id, "type": "STRUCTURAL_RULE", "properties": rule})
            edges.append({"from": "receipt", "to": rule_id, "type": "SATISFIES_RULE" if rule.get("valid") else "VIOLATES_RULE"})
        return {"nodes": nodes, "edges": edges}

    def _line_classifications(
        self,
        lines: list[Any],
        line_state: dict[int, dict[str, Any]],
        regions: list[dict[str, Any]],
        section_extraction: dict[str, Any],
        entities: list[dict[str, Any]],
    ) -> list[dict[str, Any]]:
        rejected_by_index = {
            row.get("lineIndex"): row
            for row in (((section_extraction.get("debug") or {}).get("rejectedItemRows")) or [])
            if isinstance(row, dict)
        }
        regions_by_line: dict[int, dict[str, Any]] = {}
        for region in regions:
            for line in region.get("lines", []) or []:
                if isinstance(line, dict) and isinstance(line.get("index"), int):
                    regions_by_line[line["index"]] = region
        output: list[dict[str, Any]] = []
        for index, line in enumerate(lines):
            text = compact(getattr(line, "text", line))
            state_entry = line_state.get(index, {})
            state = state_entry.get("state") or self._state_from_text(text)
            region = state_entry.get("region") or (regions_by_line.get(index, {}) or {}).get("kind", "")
            entity_type, confidence, reasons = self._classify_line_entity(text, state, region, rejected_by_index.get(index))
            matched_entities = [
                entity["id"] for entity in entities
                if index in (entity.get("lineIndexes") or [])
                or (entity.get("value") and entity.get("value") in text)
            ][:8]
            output.append({
                "lineIndex": index,
                "text": text,
                "state": state,
                "region": region,
                "entityType": entity_type,
                "confidence": confidence,
                "status": "rejected" if rejected_by_index.get(index) else "accepted",
                "reasons": reasons,
                "matchedEntityIds": matched_entities,
                "bbox": state_entry.get("bbox") or getattr(line, "bbox", {}),
            })
        return output

    def _classify_line_entity(self, text: str, state: str, region: str, rejection: dict[str, Any] | None) -> tuple[str, float, list[str]]:
        upper = text.upper()
        reasons: list[str] = []
        if rejection:
            reasons.extend(str(rejection.get("reason", "")).split(","))
        if re.search(r"\bNO\s+PURCHASE\s+NECESSARY\b|\bTHANK\b|\bSURVEY\b|\bRETURN\s+POLICY\b|\bWWW\.", upper):
            reasons.append("footer_or_policy_semantics")
            return "FOOTER", 0.92, sorted(set(filter(None, reasons)))
        if any(token in upper for token in ("VISA", "MASTERCARD", "MASTER CARD", "AMEX", "DISCOVER", "CREDIT", "DEBIT", "CARD", "APPROVAL", "AUTH")) or re.search(r"[*X]{4,}\s*\d{3,4}", upper):
            reasons.append("payment_semantics")
            if re.search(r"\b(?:LAST\s*(?:FOUR|4)|ENDING\s+IN)\D{0,12}\d{4}\b", upper) or re.search(r"[*X]{4,}\s*\d{3,4}\b", upper):
                return "LAST_FOUR", 0.92, sorted(set(reasons))
            if re.search(r"\b(?:APPROVAL|AUTH|APPR)", upper):
                return "APPROVAL_CODE", 0.88, sorted(set(reasons))
            return "PAYMENT", 0.88, sorted(set(reasons))
        if any(token in upper for token in ("SUBTOTAL", "SUB TOTAL", "TOTAL", "BALANCE", "CHANGE", "AMOUNT DUE", "CHARGE")):
            reasons.append("receipt_level_total_keyword")
            return "TOTAL", 0.9, sorted(set(reasons))
        if re.search(r"\bTAX\b", upper):
            reasons.append("tax_semantics")
            return "TAX", 0.88, sorted(set(reasons))
        if re.search(r"\b(?:USD|US DOLLAR|DOLLARS|TENDER|CURRENCY)\b", upper):
            reasons.append("currency_or_tender_semantics")
            return "MONEY", 0.78, sorted(set(reasons))
        if re.search(r"(?:\+?1[-.\s]?)?(?:\(?\d{3}\)?[-.\s]?)\d{3}[-.\s]?\d{4}", text):
            reasons.append("phone_regex")
            return "PHONE", 0.9, sorted(set(reasons))
        if re.search(r"\b(?:\d{4}[-/]\d{1,2}[-/]\d{1,2}|\d{1,2}[-/]\d{1,2}[-/]\d{2,4}|(?:JAN|FEB|MAR|APR|MAY|JUN|JUL|AUG|SEP|SEPT|OCT|NOV|DEC)[A-Z]*\.?\s+\d{1,2},?\s+\d{2,4})\b", text, flags=re.IGNORECASE):
            reasons.append("date_regex")
            return "DATE", 0.86, sorted(set(reasons))
        if re.search(r"\b\d{2,6}\b", upper) and any(re.search(rf"\b{term}\.?\b", upper) for term in ("ROAD", "RD", "STREET", "ST", "AVE", "AVENUE", "BLVD", "DR", "DRIVE", "HWY", "HIGHWAY", "WAY")):
            reasons.append("address_semantics")
            return "ADDRESS", 0.82, sorted(set(reasons))
        if state == "ITEMS" and re.search(r"[A-Z]{2,}", upper) and amount(text):
            reasons.append("product_quantity_money_relationship")
            return "PRODUCT", 0.84, sorted(set(reasons))
        if state == "HEADER" and re.search(r"[A-Z]{3,}", upper) and not re.search(r"\d{4,}", upper):
            reasons.append("header_text")
            return "MERCHANT", 0.58, sorted(set(reasons))
        if state == "FOOTER":
            reasons.append("footer_state")
            return "FOOTER", 0.72, sorted(set(reasons))
        return "MONEY" if amount(text) else "UNKNOWN", 0.42, sorted(set(reasons or ["low_semantic_confidence"]))

    def _state_from_text(self, text: str) -> str:
        upper = text.upper()
        if any(token in upper for token in ("TOTAL", "SUBTOTAL", "BALANCE", "TAX")):
            return "TOTALS"
        if any(token in upper for token in ("VISA", "CARD", "AUTH", "APPROVAL", "CREDIT", "DEBIT")):
            return "PAYMENT"
        if any(token in upper for token in ("THANK", "SURVEY", "NO PURCHASE")):
            return "FOOTER"
        return "HEADER"

    def _debug_payload(
        self,
        section_extraction: dict[str, Any],
        graph: dict[str, Any],
        line_classifications: list[dict[str, Any]],
        duplicate_diagnostics: list[dict[str, Any]],
    ) -> dict[str, Any]:
        section_debug = section_extraction.get("debug", {}) or {}
        rejected = [
            line for line in line_classifications
            if line.get("status") == "rejected" or line.get("entityType") in {"FOOTER", "PAYMENT", "TOTAL", "TAX"}
        ]
        return {
            "entityGraphVisualization": {
                "nodes": graph.get("nodes", []),
                "edges": graph.get("edges", []),
            },
            "layoutGraphVisualization": section_extraction.get("layoutGraph", {}),
            "visualSaliencyOverlays": ((section_extraction.get("visualHierarchy") or {}).get("debug") or {}).get("visualSaliencyOverlays", []),
            "regionImportanceHeatmap": ((section_extraction.get("visualHierarchy") or {}).get("debug") or {}).get("regionImportanceHeatmap", []),
            "merchantCandidateRanking": ((section_extraction.get("visualHierarchy") or {}).get("debug") or {}).get("merchantCandidateRanking", []),
            "parserStateTrace": (section_extraction.get("documentStateMachine") or {}).get("lineStates", []),
            "rejectedEntityLogs": rejected,
            "confidenceOverlays": [
                {
                    "lineIndex": line.get("lineIndex"),
                    "entityType": line.get("entityType"),
                    "confidence": line.get("confidence"),
                    "bbox": line.get("bbox", {}),
                }
                for line in line_classifications
            ],
            "sectionOverlays": section_debug.get("regionOverlays", []),
            "duplicateCollapseDiagnostics": [
                *duplicate_diagnostics,
                *(section_debug.get("duplicateSuppressionDiagnostics", []) or []),
            ],
        }

    def _first_region_bbox(self, region_index: dict[str, list[dict[str, Any]]], kind: str) -> dict[str, Any]:
        regions = region_index.get(kind, [])
        return regions[0].get("bbox", {}) if regions else {}

    def _state_lines(self, line_state: dict[int, dict[str, Any]], state: str) -> list[int]:
        return [index for index, entry in sorted(line_state.items()) if entry.get("state") == state]


class ReceiptPatternLearningEngine:
    """Produces generalized learning payloads for embedding stores and clustering.

    This class prepares Qdrant-ready records. It does not require a live Qdrant
    connection during parsing, so receipt extraction can remain deterministic and
    available when vector infrastructure is down.
    """

    def build_learning_payload(
        self,
        *,
        lines: list[Any],
        entities: list[dict[str, Any]],
        structural: dict[str, Any],
        section_extraction: dict[str, Any],
    ) -> dict[str, Any]:
        state_groups: dict[str, list[str]] = defaultdict(list)
        state_machine = (section_extraction.get("documentStateMachine") or {}).get("lineStates", []) or []
        line_text_by_index = {index: compact(getattr(line, "text", line)) for index, line in enumerate(lines)}
        for entry in state_machine:
            state = entry.get("state") or "UNKNOWN"
            line_index = entry.get("lineIndex")
            if line_index in line_text_by_index:
                state_groups[state].append(line_text_by_index[line_index])
        semantic_clusters = [
            {
                "clusterId": f"receipt-{state.lower()}",
                "state": state,
                "text": "\n".join(texts)[:1200],
                "entityTypes": sorted({entity["type"] for entity in entities if entity.get("state") == state}),
            }
            for state, texts in state_groups.items()
        ]
        pattern_signature = self._pattern_signature(state_groups, structural)
        qdrant_payloads = [
            {
                "id": hashlib.sha1(f"{pattern_signature}:{cluster['clusterId']}".encode("utf-8")).hexdigest(),
                "collection": "receipt_document_patterns",
                "text": cluster["text"],
                "metadata": {
                    "documentType": "receipt",
                    "clusterId": cluster["clusterId"],
                    "state": cluster["state"],
                    "entityTypes": cluster["entityTypes"],
                    "patternSignature": pattern_signature,
                    "structuralConfidence": structural.get("confidence", 0.0),
                },
            }
            for cluster in semantic_clusters
            if compact(cluster.get("text"))
        ]
        return {
            "schemaVersion": "receipt-pattern-learning-v1",
            "enabled": True,
            "strategy": "embedding_similarity_and_semantic_clustering",
            "uses": ["Qdrant", "Llama", "Donut", "OCR bounding boxes"],
            "patternSignature": pattern_signature,
            "semanticClusters": semantic_clusters,
            "qdrantPayloads": qdrant_payloads,
            "feedbackSignals": {
                "acceptedEntities": [entity["id"] for entity in entities if entity.get("status") == "resolved"],
                "unresolvedEntities": [entity["id"] for entity in entities if entity.get("status") == "unresolved"],
                "structuralRules": structural.get("rules", []),
            },
        }

    def _pattern_signature(self, state_groups: dict[str, list[str]], structural: dict[str, Any]) -> str:
        state_shape = "|".join(f"{state}:{len(lines)}" for state, lines in sorted(state_groups.items()))
        valid_rules = ",".join(rule.get("name", "") for rule in structural.get("rules", []) if rule.get("valid"))
        return hashlib.sha1(f"{state_shape}:{valid_rules}".encode("utf-8")).hexdigest()[:16]
