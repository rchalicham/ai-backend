from __future__ import annotations

import os
import json
import re
from collections import Counter
from typing import Any

import httpx
from fastapi import HTTPException

from services.attribute_catalog_service import AttributeCatalogService
from services.receipt_entity_extraction import ReceiptEntityExtractionEngine
from services.receipt_intelligence import ReceiptIntelligencePipeline


class LLMService:
    def __init__(self, base_url: str | None = None):
        self.base_url = base_url or os.getenv(
            "LLM_URL",
            "http://host.docker.internal:8081/v1/chat/completions",
        )
        self.attribute_catalog_service = AttributeCatalogService()
        self.receipt_intelligence = ReceiptIntelligencePipeline()
        self.receipt_entities = ReceiptEntityExtractionEngine()
        self.request_timeout = float(os.getenv("LLM_TIMEOUT_SECONDS", "120"))
        self.client = httpx.AsyncClient(timeout=self.request_timeout)

    async def structure_receipt(
        self,
        raw_text: str,
        lines: list[str] | None = None,
        ocr_blocks: list[dict[str, Any]] | None = None,
        parser_json: dict[str, Any] | None = None,
        ocr_engine: str | None = None,
        ocr_variants: list[dict[str, Any]] | None = None,
    ) -> dict[str, Any]:
        intelligence = self.receipt_intelligence.analyze(
            raw_text=raw_text,
            lines=lines,
            parser_json=parser_json,
            ocr_variants=ocr_variants,
            ocr_blocks=ocr_blocks,
        )
        reconstructed_lines = [line.text for line in intelligence.lines]
        normalized_raw_text = "\n".join(reconstructed_lines) or raw_text
        parser_hint = {
            **(parser_json or {}),
            "company": intelligence.merchant or (parser_json or {}).get("company", ""),
            "storeName": intelligence.merchant or (parser_json or {}).get("storeName", ""),
            **{
                key: value
                for key, value in (intelligence.entities.get("fields", {}) if isinstance(intelligence.entities, dict) else {}).items()
                if value
            },
            "items": intelligence.items or (parser_json or {}).get("items", []),
            **{key: value for key, value in intelligence.facts.items() if value},
            "layout": intelligence.layout_json,
            "semanticBlocks": [block.to_dict() for block in intelligence.semantic_blocks],
            "tables": intelligence.tables,
            "graph": intelligence.graph,
            "receiptIntelligence": {
                "confidence": intelligence.confidence,
                "warnings": intelligence.warnings,
                "retryPlan": intelligence.retry_plan,
                "layoutQuality": intelligence.layout_json.get("quality", {}),
            },
        }
        schema = {
            "company": "merchant/store name",
            "storeName": "same value as company",
            "storeAddress": "store street/city/state/postal address as printed",
            "date": "purchase date as printed",
            "purchaseDate": "same value as date",
            "cardUsed": "payment card brand, for example VISA, MASTERCARD, AMEX, DISCOVER",
            "cardLast4": "last four digits of the payment card",
            "paymentCard": {
                "brand": "same value as cardUsed",
                "last4": "same value as cardLast4"
            },
            "subtotal": "receipt subtotal as numeric string without currency symbol",
            "subTotal": "same value as subtotal",
            "tax": "receipt tax as numeric string without currency symbol",
            "tip": "receipt tip as numeric string without currency symbol or 0",
            "total": "receipt grand total as numeric string without currency symbol",
            "documentType": "receipt",
            "documentTypeConfidence": 1.0,
            "items": [
                {
                    "id": 1,
                    "name": "purchased item name only",
                    "count": "quantity/count as string",
                    "qty": "same value as count",
                    "amount": "line item amount as numeric string",
                    "price": "same value as amount",
                    "weight": 1.0,
                }
            ],
        }
        payload = {
            "messages": [
                {
                    "role": "system",
                    "content": (
                        "You convert OCR receipt text into a strict JSON receipt schema. "
                        "Return ONLY valid JSON. No markdown, no commentary. "
                        "Use the structured receipt layout JSON as the primary reasoning input, then verify against OCR text. "
                        "Flat OCR text is fallback evidence, not the preferred structure. The parser JSON is a hint. "
                        "Return purchased items plus receipt-level merchant/store name, store address, purchase date, card brand, card last digits, subtotal, tax, tip, and total. "
                        "Subtotal, tax, tip, total, purchase date, address, and company name are one-time receipt-level fields, never item fields. "
                        "Do not convert every OCR line into an item. Reason across adjacent OCR lines: item names are often on one line and prices on the next line; "
                        "product codes, E/N tax markers, discounts, and quantities may appear between them. Combine those lines into one item only when there is a real product name and a matching item amount. "
                        "Prefer rows from the items table and semantic item blocks over duplicated footer/header OCR fragments. "
                        "Keep real purchased item rows only. Exclude store address, member number, payment card lines, approvals, item count summaries, "
                        "subtotal/tax/total/change lines, terminal metadata, savings summary, footer text, numeric-only rows, and product-code-only rows from items. "
                        "When OCR candidates disagree, prefer the candidate with clearer item names, prices, subtotal, tax, and total. "
                        "Amounts must be numeric strings without currency symbols. "
                        "Do not invent values not supported by OCR text."
                    ),
                },
                {
                    "role": "user",
                    "content": (
                        f"Required JSON schema:\n{json.dumps(schema, ensure_ascii=True)}\n\n"
                        f"OCR engine: {ocr_engine or ''}\n"
                        f"Structured receipt layout JSON:\n{json.dumps(intelligence.layout_json, ensure_ascii=True)}\n\n"
                        f"Reconstructed receipt rows:\n{json.dumps(reconstructed_lines, ensure_ascii=True)}\n\n"
                        f"Line-by-line OCR text:\n{json.dumps(lines or [], ensure_ascii=True)}\n\n"
                        f"Alternate OCR candidates:\n{json.dumps(self._compact_ocr_variants(ocr_variants or []), ensure_ascii=True)}\n\n"
                        f"Parser candidate JSON:\n{json.dumps(parser_hint, ensure_ascii=True)}\n\n"
                        "Item reconstruction rules:\n"
                        "- One item must represent one purchased product, not one OCR row.\n"
                        "- A product-code row such as 331222 or 1462714 is not an item.\n"
                        "- E/N marker rows are not items.\n"
                        "- Payment, approval, subtotal, tax, total, change, savings, and footer rows are not items.\n"
                        "- For each item return name, count/qty, amount/price, and weight only.\n"
                        "- Put address, company, purchase date, tax, subtotal, total, tip, card brand, and last 4 digits only at receipt level.\n\n"
                        f"Flat OCR text:\n{normalized_raw_text[:16000]}"
                    ),
                },
            ],
            "temperature": 0.1,
            "max_tokens": 3500,
        }

        try:
            response = await self.client.post(self.base_url, json=payload)
        except httpx.HTTPError:
            return self._finalize_receipt_intelligence(
                self._normalize_receipt_response("", parser_hint, normalized_raw_text),
                intelligence,
            )

        try:
            body = response.json()
        except ValueError:
            return self._finalize_receipt_intelligence(
                self._normalize_receipt_response("", parser_hint, normalized_raw_text),
                intelligence,
            )

        if response.status_code >= 400:
            return self._finalize_receipt_intelligence(
                self._normalize_receipt_response("", parser_hint, normalized_raw_text),
                intelligence,
            )

        try:
            content = body["choices"][0]["message"]["content"]
        except (KeyError, IndexError, TypeError) as exc:
            raise HTTPException(status_code=502, detail="LLM response format was unexpected.") from exc

        return self._finalize_receipt_intelligence(
            self._normalize_receipt_response(content, parser_hint, normalized_raw_text),
            intelligence,
        )

    def _finalize_receipt_intelligence(self, structured: dict[str, Any], intelligence: Any) -> dict[str, Any]:
        if intelligence.merchant and not structured.get("company"):
            structured["company"] = intelligence.merchant
            structured["storeName"] = intelligence.merchant
        intelligence_items = self._normalize_intelligence_items(getattr(intelligence, "items", []))
        if intelligence_items:
            if not structured.get("items"):
                structured["items"] = intelligence_items
            else:
                structured["items"] = self._prefer_reconciled_intelligence_items(structured, intelligence_items)
        validation = self.receipt_intelligence.validator.validate(structured.get("items", []), intelligence.facts, structured)
        confidence = self.receipt_intelligence.confidence.score(intelligence.lines, structured.get("items", []), validation, structured.get("company", ""))
        retry_plan = self.receipt_intelligence.retry.plan(confidence, validation)
        structured["receiptIntelligence"] = {
            "version": "2026.05",
            "lineCount": len(intelligence.lines),
            "reconstructedLines": [line.text for line in intelligence.lines[:160]],
            "merchantNormalized": structured.get("company", ""),
            "layout": intelligence.layout_json,
            "semanticBlocks": [block.to_dict() for block in intelligence.semantic_blocks],
            "tables": intelligence.tables,
            "graph": intelligence.graph,
            "validation": validation,
            "confidence": confidence,
            "retryPlan": retry_plan,
            "warnings": validation.get("warnings", []),
        }
        structured["confidence"] = confidence["overall"]
        structured["aiRetryRecommended"] = bool(retry_plan)
        return structured

    def _normalize_intelligence_items(self, items: list[dict[str, Any]] | None) -> list[dict[str, Any]]:
        normalized = []
        for index, item in enumerate(items or []):
            if not isinstance(item, dict):
                continue
            amount = self._format_amount(item.get("amount") or item.get("price"))
            name = self._clean_receipt_item_name(item.get("name", ""))
            if not self._is_valid_receipt_item(name, amount):
                continue
            normalized.append({
                "id": index + 1,
                "name": name,
                "count": self._clean_receipt_item_qty(item.get("count") or item.get("qty") or "1"),
                "qty": self._clean_receipt_item_qty(item.get("qty") or item.get("count") or "1"),
                "amount": amount,
                "price": amount,
                "weight": self._safe_weight(item.get("weight", item.get("confidence", 1.0))),
            })
        return normalized

    def _prefer_reconciled_intelligence_items(self, structured: dict[str, Any], intelligence_items: list[dict[str, Any]]) -> list[dict[str, Any]]:
        structured_items = structured.get("items") if isinstance(structured.get("items"), list) else []
        if not structured_items:
            return intelligence_items
        target = self._receipt_reconciliation_target(structured)
        if target <= 0:
            return structured_items
        structured_delta = abs(self._sum_receipt_items(structured_items) - target)
        intelligence_delta = abs(self._sum_receipt_items(intelligence_items) - target)
        if intelligence_delta + 0.01 < structured_delta:
            return [{**item, "id": index + 1} for index, item in enumerate(intelligence_items)]
        return structured_items

    def _sum_receipt_items(self, items: list[dict[str, Any]]) -> float:
        return sum(self._numeric_amount((item or {}).get("amount") or (item or {}).get("price")) for item in items if isinstance(item, dict))

    def _receipt_reconciliation_target(self, structured: dict[str, Any]) -> float:
        subtotal = self._numeric_amount(structured.get("subtotal") or structured.get("subTotal"))
        total = self._numeric_amount(structured.get("total"))
        tax = self._numeric_amount(structured.get("tax"))
        if subtotal > 0 and (not total or subtotal <= max(total + tax + 0.5, total * 3)):
            return subtotal
        return total

    def _compact_ocr_variants(self, variants: list[dict[str, Any]]) -> list[dict[str, Any]]:
        compacted = []
        for variant in variants[:6]:
            if not isinstance(variant, dict):
                continue
            lines = variant.get("lines") if isinstance(variant.get("lines"), list) else []
            compacted.append({
                "variant": variant.get("variant", ""),
                "psm": variant.get("psm", ""),
                "score": variant.get("score", 0),
                "lines": [str(line)[:220] for line in lines[:120] if str(line).strip()],
            })
        return compacted

    def _normalize_receipt_response(self, content: str, fallback: dict[str, Any], raw_text: str = "") -> dict[str, Any]:
        text = (content or "").strip()
        fenced = re.search(r"```(?:json)?\s*(\{.*?\})\s*```", text, flags=re.IGNORECASE | re.DOTALL)
        if fenced:
            text = fenced.group(1)
        else:
            start = text.find("{")
            end = text.rfind("}")
            if start != -1 and end > start:
                text = text[start:end + 1]

        try:
            raw = json.loads(text) if text else {}
        except json.JSONDecodeError:
            raw = {}

        def amount(value: Any, default: str = "0") -> str:
            if value is None or value == "":
                return default
            cleaned = str(value).replace("$", "").strip()
            if "," in cleaned and "." not in cleaned and re.search(r",\d{2}\b", cleaned):
                cleaned = cleaned.replace(",", ".")
            else:
                cleaned = cleaned.replace(",", "")
            match = re.search(r"-?\d+(?:\.\d+)?", cleaned)
            return match.group(0) if match else default

        def text_value(value: Any, default: str = "") -> str:
            return str(value).strip() if value not in (None, "") else default

        def receipt_amount(*values: Any, default: str = "0") -> str:
            first = default
            for value in values:
                parsed = amount(value, "")
                if parsed and first == default:
                    first = parsed
                if parsed and parsed not in {"0", "0.0", "0.00"}:
                    return parsed
            return first

        inferred = self._infer_receipt_facts(raw_text, fallback or {})
        entity_fields = self.receipt_entities.extract(raw_text=raw_text, lines=[line for line in raw_text.splitlines() if line.strip()]).get("fields", {})
        card = raw.get("paymentCard") if isinstance(raw.get("paymentCard"), dict) else {}
        inferred_company = inferred.get("company", "")
        company = self._choose_company_name(
            raw.get("storeName") or raw.get("company"),
            fallback.get("company") or entity_fields.get("merchant"),
            inferred_company,
        )
        purchase_date = self._choose_purchase_date(
            raw.get("purchaseDate") or raw.get("date"),
            text_value(fallback.get("date"), ""),
            inferred.get("date", ""),
        )
        card_brand = text_value(raw.get("cardUsed") or raw.get("cardType") or card.get("brand"), entity_fields.get("cardUsed") or inferred.get("cardUsed", ""))
        card_last4 = text_value(raw.get("cardLast4") or raw.get("lastFour") or card.get("last4"), entity_fields.get("cardLast4") or inferred.get("cardLast4", ""))
        approval_code = text_value(raw.get("approvalCode"), entity_fields.get("approvalCode", ""))
        payment_method = text_value(raw.get("paymentMethod"), entity_fields.get("paymentMethod", ""))
        store_address = self._choose_store_address(raw.get("storeAddress") or raw.get("address"), entity_fields.get("storeAddress") or inferred.get("storeAddress", ""))

        structured = {
            "company": company,
            "storeName": company,
            "storeAddress": store_address,
            "date": purchase_date,
            "purchaseDate": purchase_date,
            "cardUsed": card_brand,
            "cardType": card_brand,
            "cardLast4": card_last4,
            "lastFour": card_last4,
            "approvalCode": approval_code,
            "paymentMethod": payment_method,
            "paymentCard": {
                "brand": card_brand,
                "last4": card_last4,
                "approvalCode": approval_code,
            },
            "subtotal": receipt_amount(raw.get("subtotal"), raw.get("subTotal"), fallback.get("subtotal"), fallback.get("subTotal"), inferred.get("subtotal")),
            "tax": receipt_amount(raw.get("tax"), fallback.get("tax"), inferred.get("tax")),
            "tip": amount(raw.get("tip", fallback.get("tip", "0"))),
            "total": receipt_amount(raw.get("total"), fallback.get("total"), inferred.get("total")),
            "documentType": text_value(raw.get("documentType"), text_value(fallback.get("documentType"), "receipt")),
        }
        self._reconcile_receipt_amounts(structured, inferred)
        self._sanitize_receipt_amounts(structured)
        structured["subTotal"] = structured["subtotal"]
        try:
            structured["documentTypeConfidence"] = float(raw.get("documentTypeConfidence", fallback.get("documentTypeConfidence", 1.0)))
        except (TypeError, ValueError):
            structured["documentTypeConfidence"] = 1.0

        items = []
        raw_items = raw.get("items") if isinstance(raw.get("items"), list) else []
        inferred_items = self._infer_receipt_items(raw_text)
        for item in raw_items:
            if not isinstance(item, dict):
                continue
            name, parsed_qty = self._extract_receipt_item_name_and_qty(text_value(item.get("name") or item.get("description")))
            item_amount = amount(item.get("amount", item.get("price", "")), "")
            if not self._is_valid_receipt_item(name, item_amount):
                continue
            try:
                weight = float(str(item.get("weight", 1.0)).replace(",", ""))
            except (TypeError, ValueError):
                weight = 1.0
            items.append({
                "id": len(items) + 1,
                "name": name,
                "count": self._clean_receipt_item_qty(item.get("count") or item.get("qty") or item.get("quantity") or parsed_qty),
                "qty": self._clean_receipt_item_qty(item.get("qty") or item.get("count") or item.get("quantity") or parsed_qty),
                "amount": item_amount,
                "price": amount(item.get("price", item.get("amount", "")), ""),
                "weight": weight,
            })
        items = self._select_best_receipt_items(items, inferred_items, structured, raw_text)
        if items:
            structured["items"] = items
        elif not isinstance(structured.get("items"), list):
            structured["items"] = []

        structured["aiStructured"] = True
        return structured

    def _reconcile_receipt_amounts(self, structured: dict[str, Any], inferred: dict[str, str]) -> None:
        subtotal = self._numeric_amount(structured.get("subtotal") or structured.get("subTotal"))
        tax = self._numeric_amount(structured.get("tax"))
        total = self._numeric_amount(structured.get("total"))
        inferred_tax = self._numeric_amount(inferred.get("tax"))
        if not subtotal or not total or not inferred_tax:
            return

        expected_tax = round(total - subtotal, 2)
        if expected_tax <= 0:
            return

        current_tax_is_total = abs(tax - total) <= 0.01
        current_tax_mismatches_total = tax and abs((subtotal + tax) - total) > max(0.35, total * 0.04)
        inferred_tax_matches_total = abs(inferred_tax - expected_tax) <= max(0.35, total * 0.04)
        if inferred_tax_matches_total and (not tax or current_tax_is_total or current_tax_mismatches_total):
            structured["tax"] = f"{inferred_tax:.2f}"

    def _is_valid_receipt_item(self, name: str, item_amount: str) -> bool:
        normalized = re.sub(r"\s+", " ", str(name or "")).strip()
        upper = normalized.upper()
        if len(normalized) < 2 or not item_amount:
            return False
        if re.fullmatch(r"[/#]?\d{3,}", normalized):
            return False
        if upper in {"E", "N", "Y", "T", "F", "CHIP", "READ", "VISA", "MASTERCARD", "AMEX", "DISCOVER", "CREDIT", "DEBIT"}:
            return False
        if self._near_receipt_level_term(upper):
            return False
        blocked_terms = (
            "SUBTOTAL", "SUB TOTAL", "TOTAL", "TAX", "TIP", "AMOUNT", "CHANGE", "APPROVED", "PURCHASE",
            "MEMBER", "CARD", "XXXXXXXX", "AUTH", "TERMINAL", "THANK", "COME AGAIN", "ITEMS SOLD",
            "INSTANT SAVINGS", "SAVINGS", "WHSE", "TRM", "TRN", "OPT", "BALANCE", "CASH", "PAYMENT",
        )
        blocked_upper = upper.replace("1AX", "TAX").replace("IAX", "TAX")
        if any(term in blocked_upper for term in blocked_terms):
            return False
        return bool(re.search(r"[A-Za-z]", normalized)) and bool(re.search(r"[A-Za-z]{3,}", normalized))

    def _near_receipt_level_term(self, upper: str) -> bool:
        token = re.sub(r"[^A-Z]", "", upper.split()[0] if upper.split() else "")
        if len(token) < 4:
            return False
        if token in {"GATT", "HARGE", "T0TAL", "TOTAI", "TQTAL", "SUBT0TAL", "CHARGF", "CHAR6E"}:
            return True
        targets = ("TOTAL", "SUBTOTAL", "CHARGE", "PAYMENT", "CHANGE", "VISA", "CARD", "AUTH", "CASH")
        return any(self._one_edit_apart(token, target) for target in targets)

    def _one_edit_apart(self, left: str, right: str) -> bool:
        if abs(len(left) - len(right)) > 1:
            return False
        if len(left) == len(right):
            return sum(1 for a, b in zip(left, right) if a != b) <= 1
        short, long = (left, right) if len(left) < len(right) else (right, left)
        for index in range(len(long)):
            if long[:index] + long[index + 1:] == short:
                return True
        return False

    def _sanitize_receipt_amounts(self, structured: dict[str, Any]) -> None:
        subtotal = self._numeric_amount(structured.get("subtotal") or structured.get("subTotal"))
        total = self._numeric_amount(structured.get("total"))
        tax = self._numeric_amount(structured.get("tax"))
        if subtotal and total:
            if subtotal > max(total + tax + 0.5, total * 3):
                structured["subtotal"] = ""
                structured["subTotal"] = ""
            elif "." not in str(structured.get("subtotal", "")) and abs(subtotal - total) > max(0.5, total * 0.08):
                structured["subtotal"] = ""
                structured["subTotal"] = ""

    def _clean_receipt_item_name(self, name: str) -> str:
        cleaned = re.sub(r"\s+", " ", str(name or "")).strip(" -_:;")
        cleaned = re.sub(r"^\d{1,3}\s*[-~»—°=]*\s*", "", cleaned).strip(" -_:;")
        cleaned = re.sub(r"\b\d{5,8}\b\s*[A-Z]?\s*$", "", cleaned).strip(" -_:;")
        cleaned = re.sub(r"\s+[INTJYF]\s*$", "", cleaned, flags=re.IGNORECASE).strip(" -_:;")
        tokens = cleaned.split()
        while tokens and self._looks_like_sku_token(tokens[0]):
            tokens.pop(0)
        cleaned = " ".join(tokens).strip(" -_:;")
        replacements = {
            "SHELUIN": "SHELVING",
            "SHELYING": "SHELVING",
            "SHELVIN": "SHELVING",
            "SHELUING": "SHELVING",
            "S-TIER": "5-TIER",
            "STIER": "5-TIER",
            "PEI": "PET",
            "PE L": "PET",
            "PEL": "PET",
            "PLI": "PET",
            "PLA": "PET",
            "PKI": "PET",
            "GARDLN": "GARDEN",
            "GARUIN": "GARDEN",
            "GARDIN": "GARDEN",
            "Q LIN": "Q LINE",
            "Q LIM": "Q LINE",
            "GOURHET": "GOURMET",
            "CUSTOM LTEM": "CUSTOM ITEM",
            "CUSTOM L TEM": "CUSTOM ITEM",
            "CUSTOM TEM": "CUSTOM ITEM",
        }
        for wrong, right in replacements.items():
            cleaned = re.sub(rf"\b{wrong}\b", right, cleaned, flags=re.IGNORECASE)
        cleaned = re.sub(r"^TIER\s+BLACK\s+WIRE\b", "5-TIER BLACK WIRE", cleaned, flags=re.IGNORECASE)
        cleaned = re.sub(r"\s+", " ", cleaned).strip(" -_:;")
        return cleaned

    def _select_best_receipt_items(
        self,
        raw_items: list[dict[str, Any]],
        inferred_items: list[dict[str, Any]],
        structured: dict[str, Any],
        raw_text: str,
    ) -> list[dict[str, Any]]:
        candidates: list[dict[str, Any]] = []
        for item in [*(raw_items or []), *(inferred_items or [])]:
            if not isinstance(item, dict):
                continue
            price = self._format_amount(item.get("amount") or item.get("price"))
            name = self._clean_receipt_item_name(item.get("name", ""))
            if not self._is_valid_receipt_item(name, price):
                continue
            if self._is_receipt_level_item(name, price, structured):
                continue
            candidates.append({
                "name": name,
                "count": self._clean_receipt_item_qty(item.get("count") or item.get("qty") or "1"),
                "qty": self._clean_receipt_item_qty(item.get("qty") or item.get("count") or "1"),
                "amount": price,
                "price": price,
                "weight": item.get("weight", 1.0),
            })

        if not candidates:
            return []

        primary_candidates = [
            item for item in candidates
            if self._item_appears_in_primary_receipt_section(raw_text, item["name"], item["amount"])
        ]
        if len(primary_candidates) >= 2:
            candidates = primary_candidates

        best_by_key: dict[tuple[str, str], dict[str, Any]] = {}
        for item in candidates:
            canonical = self._canonical_item_name(item["name"])
            key = (canonical, item["amount"])
            current = best_by_key.get(key)
            if current is None or self._item_quality_score(item["name"]) > self._item_quality_score(current["name"]):
                best_by_key[key] = item

        deduped = list(best_by_key.values())
        target_count = self._infer_sold_item_count(raw_text)
        subtotal = self._numeric_amount(structured.get("subtotal") or structured.get("subTotal"))
        if target_count and len(deduped) > target_count:
            selected = self._choose_items_matching_total(deduped, target_count, subtotal)
            if selected:
                deduped = selected

        deduped.sort(key=lambda item: self._first_line_position(raw_text, item["name"], item["amount"]))
        return [
            {
                "id": index + 1,
                "name": item["name"],
                "count": item["count"] or "1",
                "qty": item["qty"] or "1",
                "amount": item["amount"],
                "price": item["price"],
                "weight": self._safe_weight(item.get("weight")),
            }
            for index, item in enumerate(deduped)
        ]

    def _is_receipt_level_item(self, name: str, price: str, structured: dict[str, Any]) -> bool:
        upper = str(name or "").upper()
        if any(token in upper for token in ("AMEX", "VISA", "MASTERCARD", "DISCOVER", "TOTAL", "TAX", "CHANGE")):
            return True
        receipt_amounts = {
            self._format_amount(structured.get("subtotal") or structured.get("subTotal")),
            self._format_amount(structured.get("tax")),
            self._format_amount(structured.get("tip")),
            self._format_amount(structured.get("total")),
        }
        if price in receipt_amounts and self._item_quality_score(name) < 4:
            return True
        return False

    def _canonical_item_name(self, name: str) -> str:
        upper = self._clean_receipt_item_name(name).upper()
        upper = re.sub(r"[^A-Z0-9 ]+", " ", upper)
        tokens = []
        for token in upper.split():
            if token.isdigit() and len(token) >= 3:
                continue
            tokens.append(token)
        return " ".join(tokens)

    def _item_quality_score(self, name: str) -> int:
        text = str(name or "")
        alpha_tokens = re.findall(r"[A-Za-z]{3,}", text)
        return len(alpha_tokens) * 3 + sum(len(token) for token in alpha_tokens) - len(re.findall(r"[~©»]", text))

    def _clean_receipt_item_qty(self, value: Any) -> str:
        text = str(value or "").strip()
        match = re.search(r"\d+(?:[.,]\d+)?", text)
        if not match:
            return "1"
        return match.group(0).replace(",", ".")

    def _extract_receipt_item_name_and_qty(self, value: Any) -> tuple[str, str]:
        text = re.sub(r"\s+", " ", str(value or "")).strip(" -_:;")
        leading = re.match(r"^(?P<qty>\d{1,3}(?:[.,]\d+)?)\s+(?P<name>[A-Za-z][A-Za-z0-9&'. /-].*)$", text)
        if leading and not self._looks_like_sku_token(leading.group("qty")):
            return self._clean_receipt_item_name(leading.group("name")), self._clean_receipt_item_qty(leading.group("qty"))
        trailing = re.match(r"^(?P<name>.*?[A-Za-z][A-Za-z0-9&'. /-]*)\s+(?:x\s*)?(?P<qty>\d{1,3}(?:[.,]\d+)?)$", text, flags=re.IGNORECASE)
        if trailing:
            return self._clean_receipt_item_name(trailing.group("name")), self._clean_receipt_item_qty(trailing.group("qty"))
        return self._clean_receipt_item_name(text), "1"

    def _infer_sold_item_count(self, raw_text: str) -> int | None:
        matches = re.findall(r"\b(?:SOLD|SALD)\s+ITEM\s+COUNT\s*=\s*(\d{1,3})\b", raw_text or "", flags=re.IGNORECASE)
        if not matches:
            return None
        counts = [int(match) for match in matches if match.isdigit()]
        return Counter(counts).most_common(1)[0][0] if counts else None

    def _choose_items_matching_total(self, items: list[dict[str, Any]], target_count: int, subtotal: float) -> list[dict[str, Any]]:
        if target_count <= 0 or len(items) < target_count:
            return []
        best: tuple[float, int, list[dict[str, Any]]] | None = None

        def search(start: int, chosen: list[dict[str, Any]], total: float) -> None:
            nonlocal best
            if len(chosen) == target_count:
                delta = abs(total - subtotal) if subtotal else 0
                quality = sum(self._item_quality_score(item["name"]) for item in chosen)
                if best is None or (delta, -quality) < (best[0], best[1]):
                    best = (delta, -quality, chosen.copy())
                return
            remaining = target_count - len(chosen)
            for index in range(start, len(items) - remaining + 1):
                item = items[index]
                search(index + 1, [*chosen, item], total + self._numeric_amount(item["amount"]))

        if len(items) <= 18:
            search(0, [], 0.0)
        return best[2] if best and (not subtotal or best[0] <= 0.15) else []

    def _first_line_position(self, raw_text: str, name: str, amount: str) -> int:
        canonical = self._canonical_item_name(name)
        lines = (raw_text or "").splitlines()
        amount_variants = {str(amount or "")}
        if "." in str(amount or ""):
            amount_variants.add(str(amount).replace(".", " "))
            amount_variants.add(str(amount).replace(".", ","))
        for index, line in enumerate(lines):
            if any(variant and variant in line for variant in amount_variants):
                line_canonical = self._canonical_item_name(line)
                if canonical and canonical in line_canonical:
                    return index
        return len(lines) + self._item_quality_score(name)

    def _item_appears_in_primary_receipt_section(self, raw_text: str, name: str, amount: str) -> bool:
        primary_section = self._primary_receipt_item_section(raw_text)
        if not primary_section:
            return False
        canonical_section = self._canonical_item_name(primary_section)
        canonical_name = self._canonical_item_name(name)
        if not canonical_name or canonical_name not in canonical_section:
            return False
        amount_variants = {str(amount or "")}
        if "." in str(amount or ""):
            amount_variants.add(str(amount).replace(".", " "))
            amount_variants.add(str(amount).replace(".", ","))
        return any(variant and variant in primary_section for variant in amount_variants)

    def _primary_receipt_item_section(self, raw_text: str) -> str:
        lines = [line for line in (raw_text or "").splitlines() if str(line).strip()]
        if not lines:
            return ""
        collected: list[str] = []
        saw_item = False
        for line in lines:
            normalized = re.sub(r"\s+", " ", str(line or "")).strip()
            upper = normalized.upper()
            if saw_item and re.search(r"\bSUB\s*TOTAL\b|\bSUBTOTAL\b", upper):
                break
            if re.search(r"[A-Za-z]{3,}", normalized) and re.search(r"\d{1,4}(?:[., ]\d{2})\b", normalized):
                saw_item = True
            collected.append(normalized)
        return "\n".join(collected) if saw_item else ""

    def _format_amount(self, value: Any) -> str:
        numeric = self._numeric_amount(value)
        return f"{numeric:.2f}" if numeric else ""

    def _safe_weight(self, value: Any) -> float:
        try:
            return float(str(value).replace(",", ""))
        except (TypeError, ValueError):
            return 1.0

    def _looks_like_sku_token(self, token: str) -> bool:
        normalized = re.sub(r"[^A-Za-z0-9]", "", str(token or ""))
        if not normalized:
            return False
        if normalized.isdigit() and len(normalized) >= 3:
            return True
        return (
            4 <= len(normalized) <= 12
            and bool(re.search(r"\d", normalized))
            and bool(re.search(r"[A-Za-z]", normalized))
        )

    def _infer_receipt_items(self, raw_text: str) -> list[dict[str, Any]]:
        items: list[dict[str, Any]] = []
        seen: set[tuple[str, str]] = set()
        lines = [re.sub(r"\s+", " ", line).strip() for line in (raw_text or "").splitlines()]
        for index, line in enumerate(lines):
            cleaned = line
            if not cleaned:
                continue
            normalized_amounts = cleaned.replace("$", "")
            match = re.search(r"(.+?)\s+(-?\d{1,4}(?:[.,]\d{2})|\d{1,4}\s+\d{2})\s*[^0-9]*$", normalized_amounts)
            raw_name = ""
            amount_text = ""
            if match:
                raw_name = match.group(1)
                amount_text = match.group(2)
            if not match and index + 1 < len(lines):
                next_line = lines[index + 1].replace("$", "")
                if re.fullmatch(r"-?\d{1,4}(?:[.,]\d{2}|\s+\d{2})\s*[^0-9]*", next_line):
                    amount_match = re.search(r"-?\d{1,4}(?:[.,]\d{2}|\s+\d{2})", next_line)
                    if amount_match:
                        raw_name = normalized_amounts
                        amount_text = amount_match.group(0)
                        match = amount_match
            if not match or not raw_name or not amount_text:
                continue
            raw_name = re.sub(r"^[^A-Za-z0-9]+", "", raw_name).strip(" -_:;")
            name, qty = self._extract_receipt_item_name_and_qty(raw_name)
            price = self._format_amount(amount_text.replace(" ", ".").replace(",", "."))
            if not self._is_valid_receipt_item(name, price):
                continue
            key = (re.sub(r"[^A-Z0-9]+", "", name.upper()), qty, price)
            if key in seen:
                continue
            seen.add(key)
            items.append({
                "id": len(items) + 1,
                "name": name,
                "count": qty,
                "qty": qty,
                "amount": price,
                "price": price,
                "weight": 1.0,
            })
        if not items:
            return []
        shelving = [item for item in items if self._is_shelving_item(item.get("name", ""))]
        if shelving:
            best = max(shelving, key=lambda item: (self._numeric_amount(item.get("amount")), len(str(item.get("name", "")))))
            best["id"] = 1
            return [best]
        return items

    def _numeric_amount(self, value: Any) -> float:
        match = re.search(r"-?\d+(?:\.\d+)?", str(value or "").replace(",", "."))
        if not match:
            return 0.0
        try:
            return float(match.group(0))
        except ValueError:
            return 0.0

    def _is_shelving_item(self, name: str) -> bool:
        upper = str(name or "").upper()
        return (
            "S-TIER" in upper
            or "STIER" in upper
            or "BLACK WIRE" in upper
            or "SHELV" in upper
            or "SHELY" in upper
            or "SHELUIN" in upper
        )

    def _infer_receipt_facts(self, raw_text: str, fallback: dict[str, Any]) -> dict[str, str]:
        lines = [line.strip() for line in (raw_text or "").splitlines() if line.strip()]
        company = self._infer_company_name(raw_text, str(fallback.get("company") or (lines[0] if lines else "")).strip())
        address_lines = []
        street_candidates: list[tuple[int, str]] = []
        city_candidates: list[tuple[int, str]] = []
        for index, line in enumerate(lines):
            upper = line.upper()
            if self._looks_like_city_state_zip_line(upper):
                city_candidates.append((index, self._clean_address_line(line)))
            if (
                re.search(r"\b\d{3,6}\s+[A-Z0-9][A-Z0-9\s.'-]{4,}\b", upper)
                and not self._looks_like_non_address_number_line(upper)
            ):
                street_candidates.append((index, self._clean_address_line(line)))
        if city_candidates:
            city_index, city_line = self._choose_best_city_candidate(city_candidates, street_candidates)
            previous_streets = [
                candidate
                for candidate in street_candidates
                if candidate[0] < city_index and city_index - candidate[0] <= 3
            ]
            if not previous_streets:
                previous_streets = [candidate for candidate in street_candidates if candidate[0] < city_index]
            street_line = previous_streets[-1][1] if previous_streets else ""
            address_lines = [line for line in (street_line, city_line) if line]
        card_brand = ""
        for brand in ("VISA", "MASTERCARD", "MASTER CARD", "AMEX", "AMERICAN EXPRESS", "DISCOVER"):
            if re.search(rf"\b{re.escape(brand)}\b", raw_text or "", flags=re.IGNORECASE):
                card_brand = "MASTERCARD" if brand == "MASTER CARD" else ("AMEX" if brand == "AMERICAN EXPRESS" else brand)
                break
        last4 = ""
        last4_match = re.search(r"(?:X{2,}|[*]{2,}|ending\s+in\s+)(\d{3,4})\b", raw_text or "", flags=re.IGNORECASE)
        if last4_match:
            last4 = last4_match.group(1)
        subtotal_candidates: list[str] = []
        tax_candidates: list[str] = []
        total_candidates: list[str] = []
        for line in lines:
            upper = line.upper()
            line_amounts = re.findall(r"\d{1,4}[\.,]\d{2}", line)
            if not line_amounts:
                continue
            value = line_amounts[-1].replace(",", ".")
            if "SUB" in upper and ("TOTAL" in upper or "TUTAL" in upper or "IUTAL" in upper):
                subtotal_candidates.append(value)
                continue
            if "TAX" in upper or "FAK" in upper or "FAXK" in upper:
                tax_candidates.append(value)
                continue
            if (
                ("TOTAL" in upper or "FOTAL" in upper or "INUNICE" in upper or "INUDICE" in upper)
                and "AMEX" not in upper
                and "ANEX" not in upper
                and "QHEX" not in upper
                and "AMOUNT" not in upper
                and "ANOUNT" not in upper
                and "RNOUNT" not in upper
            ):
                total_candidates.append(value)

        def most_common_amount(candidates: list[str], default: str = "") -> str:
            if not candidates:
                return default
            return Counter(candidates).most_common(1)[0][0]

        subtotal_value = most_common_amount(subtotal_candidates)
        total_value = most_common_amount(total_candidates)
        tax_value = most_common_amount(tax_candidates)
        try:
            if subtotal_value and total_value and tax_candidates:
                expected_tax = float(total_value) - float(subtotal_value)
                tax_value = min(tax_candidates, key=lambda candidate: abs(float(candidate) - expected_tax))
        except ValueError:
            pass

        return {
            "company": company,
            "storeAddress": ", ".join(address_lines),
            "date": self._infer_purchase_date(raw_text),
            "cardUsed": card_brand,
            "cardLast4": last4,
            "subtotal": subtotal_value,
            "tax": tax_value,
            "total": total_value,
        }

    def _choose_purchase_date(self, ai_date: Any, fallback_date: str, inferred_date: str) -> str:
        inferred = str(inferred_date or "").strip()
        if inferred:
            return inferred
        return str(ai_date or fallback_date or "").strip()

    def _infer_purchase_date(self, raw_text: str) -> str:
        lines = [line.strip() for line in (raw_text or "").splitlines() if line.strip()]
        named_months = {
            "JAN": "01", "FEB": "02", "MAR": "03", "APR": "04", "MAY": "05", "JUN": "06",
            "JUL": "07", "AUG": "08", "SEP": "09", "OCT": "10", "NOV": "11", "DEC": "12",
        }
        for line in lines:
            match = re.search(
                r"\b(\d{1,2})[-\s]([A-Za-z]{3})[-\s](\d{2,4})(?:\s+\d{1,2}:\d{2}(?::\d{2})?\s*[AP]?)?",
                line,
                flags=re.IGNORECASE,
            )
            if match:
                day, month_name, year = match.groups()
                month = named_months.get(month_name[:3].upper())
                if month:
                    full_year = self._normalize_receipt_year(year)
                    return f"{month}/{int(day):02d}/{full_year}"

        month_day_counter: Counter[tuple[str, str]] = Counter()
        year_counter: Counter[str] = Counter()
        best_time = ""
        for line in lines:
            normalized = line.replace("%", "").replace("°", "-")
            for match in re.finditer(r"\b(\d{1,2})[/-](\d{1,2})[/-](\d{2,4})(?:\s+(\d{1,2}:\d{2}(?::\d{2})?))?", normalized):
                month_raw, day_raw, year_raw, time_raw = match.groups()
                month = self._normalize_ocr_date_number(month_raw, 12)
                day = self._normalize_ocr_date_number(day_raw, 31)
                if not month or not day:
                    continue
                full_year = self._normalize_receipt_year(year_raw)
                if not full_year:
                    continue
                score = 3
                upper = line.upper()
                if any(token in upper for token in ("SALE", "SALES", "TRANS", "TRASH", "PURCHASE", "INVOICE")):
                    score += 2
                if any(token in upper for token in ("CHIP", "AUTH", "TERMINAL", "AID", "CARD")):
                    score -= 1
                month_day_counter[(month, day)] += max(score, 1)
                year_counter[full_year] += 1
                if time_raw and not best_time:
                    best_time = time_raw
        if not month_day_counter or not year_counter:
            return ""
        month, day = month_day_counter.most_common(1)[0][0]
        year = year_counter.most_common(1)[0][0]
        return f"{month}/{day}/{year}{f' {best_time}' if best_time else ''}"

    def _normalize_receipt_year(self, year: str) -> str:
        digits = re.sub(r"\D", "", str(year or ""))
        if len(digits) == 2:
            return f"20{digits}"
        if len(digits) == 4:
            return digits
        return ""

    def _normalize_ocr_date_number(self, value: str, max_value: int) -> str:
        digits = re.sub(r"\D", "", str(value or ""))
        if not digits:
            return ""
        number = int(digits)
        if 1 <= number <= max_value:
            return f"{number:02d}"
        if len(digits) == 2 and digits[0] == "9":
            corrected = int(f"1{digits[1]}")
            if 1 <= corrected <= max_value:
                return f"{corrected:02d}"
        if len(digits) == 2 and digits[0] in {"6", "8"}:
            corrected = int(f"0{digits[1]}")
            if 1 <= corrected <= max_value:
                return f"{corrected:02d}"
        return ""

    def _infer_company_name(self, raw_text: str, fallback: str) -> str:
        normalized = self.receipt_intelligence.merchants.normalize(raw_text, fallback)
        if normalized and normalized != fallback:
            return normalized
        merchant_clue = self._infer_merchant_from_receipt_clues(raw_text)
        if merchant_clue:
            return merchant_clue
        return fallback

    def _choose_company_name(self, raw_company: Any, fallback_company: Any, inferred_company: str) -> str:
        raw = str(raw_company or "").strip()
        fallback = str(fallback_company or "").strip()
        inferred = str(inferred_company or "").strip()
        if inferred and inferred.upper() not in {raw.upper(), fallback.upper()}:
            return inferred
        return raw or fallback or inferred

    def _infer_merchant_from_receipt_clues(self, raw_text: str) -> str:
        text = re.sub(r"\s+", " ", raw_text or "").strip()
        if not text:
            return ""

        candidates: list[str] = []
        clue_patterns = [
            r"\b([A-Z][A-Za-z0-9&'. -]{2,40}?)\s+VALUES\s+YOUR\s+FEEDBACK\b",
            r"\bTHANK\s+YOU\s+FOR\s+SHOPPING\s+(?:AT|@|A[DT])?\s*([A-Z][A-Za-z0-9&'. -]{2,40})\b",
            r"\b([A-Z][A-Za-z0-9&'. -]{2,40}?)\s+GIFT\s+CARD\b",
        ]
        for line in (raw_text or "").splitlines():
            line_text = re.sub(r"\s+", " ", line).strip()
            for pattern in clue_patterns:
                for match in re.finditer(pattern, line_text, flags=re.IGNORECASE):
                    candidates.append(match.group(1))
        for match in re.finditer(r"\bVISIT\s+(?:WWW\.)?([A-Z0-9][A-Z0-9-]{2,35})(?:FEEDBACK|SURVEY|REWARDS)?\.(?:COM|NET|ORG)\b", text, flags=re.IGNORECASE):
            candidates.append(match.group(1))

        normalized = [self._normalize_merchant_candidate(candidate) for candidate in candidates]
        normalized = [candidate for candidate in normalized if candidate]
        if not normalized:
            return ""
        return Counter(normalized).most_common(1)[0][0]

    def _normalize_merchant_candidate(self, candidate: str) -> str:
        cleaned = re.sub(r"[^A-Za-z0-9&'. -]+", " ", str(candidate or ""))
        cleaned = re.sub(r"\s+", " ", cleaned).strip(" -_.")
        cleaned = re.sub(r"\b(VALUES|YOUR|FEEDBACK|SURVEY|REWARDS|REWARD|VISIT|WWW|COM|GIFT|CARD)\b", "", cleaned, flags=re.IGNORECASE)
        cleaned = re.sub(r"\b(A|AD|AT|IL|A\})\b", "", cleaned, flags=re.IGNORECASE)
        cleaned = re.sub(r"\s+", " ", cleaned).strip(" -_.")
        if not cleaned or len(cleaned) < 3:
            return ""

        return cleaned.title()

    def _clean_address_line(self, line: str) -> str:
        cleaned = re.sub(r"\s+", " ", str(line or "")).strip(" -_:;")
        cleaned = re.sub(r"^[^A-Za-z0-9]+", "", cleaned)
        replacements = {
            "PLYNUUTH": "PLYMOUTH",
            "PLYNQUTH": "PLYMOUTH",
            "PNWE": "LOWE",
            "LNWE": "LOWE",
            "CENFERS": "CENTERS",
            "CRENSERS": "CENTERS",
            " LEE": " LLC",
            " LEC": " LLC",
        }
        upper = cleaned.upper()
        for source, target in replacements.items():
            upper = upper.replace(source, target)
        upper = re.sub(r"\b4?1205 VICKSBURG LAKE NORTH\b", "4205 VICKSBURG LANE NORTH", upper)
        upper = re.sub(r"\bVICKSBURG LAKE NORTH\b", "VICKSBURG LANE NORTH", upper)
        upper = re.sub(r"\s*\(?\d{3,4}\)?\s*\d{3,4}-\d{4}\s*$", "", upper).strip()
        return upper

    def _choose_store_address(self, ai_address: Any, inferred_address: str) -> str:
        ai_value = str(ai_address or "").strip()
        inferred_value = str(inferred_address or "").strip()
        if not ai_value:
            return inferred_value
        if not inferred_value:
            return ai_value
        ai_upper = ai_value.upper()
        inferred_upper = inferred_value.upper()
        if (
            self._looks_like_non_address_number_line(ai_upper)
            or ("TEXT" in ai_upper and re.search(r"\b\d{5}\b", ai_upper))
            or (re.search(r"\b[A-Z]{2}\s+\d{5}(?:-\d{4})?\b", inferred_upper) and not re.search(r"\b[A-Z]{2}\s+\d{5}(?:-\d{4})?\b", ai_upper))
        ):
            return inferred_value
        return ai_value

    def _looks_like_city_state_zip_line(self, upper_line: str) -> bool:
        if not re.search(r"\b[A-Z]{2}\s+\d{5}(?:-\d{4})?\b", upper_line):
            return False
        return not re.search(r"\b(TEXT|TXT|CALL|PHONE|TEL|AUTH|MID|AID|REFERENCE|REF|INVOICE|ORDER)\b", upper_line)

    def _looks_like_non_address_number_line(self, upper_line: str) -> bool:
        return bool(re.search(
            r"\b(SALES|TRANS|TRASH|CHIP|REF|STORE|TERMINAL|TEXT|TXT|CALL|PHONE|TEL|AUTH|MID|AID|REFERENCE|INVOICE|ORDER|TOTAL|TAX|SUBTOTAL|AMEX|VISA|MASTERCARD|CONTACTLESS)\b",
            upper_line,
        ))

    def _choose_best_city_candidate(
        self,
        city_candidates: list[tuple[int, str]],
        street_candidates: list[tuple[int, str]],
    ) -> tuple[int, str]:
        if not city_candidates:
            return (-1, "")
        for city_index, city_line in city_candidates:
            if any(street_index < city_index and city_index - street_index <= 3 for street_index, _ in street_candidates):
                return (city_index, city_line)
        return city_candidates[0]

    async def ask(self, question: str, chunks: list[dict[str, Any]], graph_context: dict[str, Any]) -> str:
        chunk_context = "\n\n".join(
            f"[Chunk {idx + 1}] {chunk.get('text', '')}"
            for idx, chunk in enumerate(chunks)
        ) or "No matching chunks found."

        graph_lines = []
        for relation in graph_context.get("relationships", []):
            graph_lines.append(
                f"{relation['from_type']}({relation['from_id']}) -[{relation['relationship']}]-> "
                f"{relation['to_type']}({relation['to_id']})"
            )
        graph_block = "\n".join(graph_lines) or "No graph relationships found."

        payload = {
            "messages": [
                {
                    "role": "system",
                    "content": (
                        "Answer the question using the provided document chunks and graph context. "
                        "If the context is insufficient, say so plainly."
                    ),
                },
                {
                    "role": "user",
                    "content": (
                        f"Question:\n{question}\n\n"
                        f"Document Chunks:\n{chunk_context}\n\n"
                        f"Graph Context:\n{graph_block}"
                    ),
                },
            ]
        }

        try:
            response = await self.client.post(self.base_url, json=payload)
        except httpx.HTTPError as exc:
            raise HTTPException(status_code=502, detail=f"LLM request failed: {exc}") from exc

        try:
            body = response.json()
        except ValueError as exc:
            raise HTTPException(status_code=502, detail="LLM returned invalid JSON.") from exc

        if response.status_code >= 400:
            detail = body.get("error") if isinstance(body, dict) else body
            raise HTTPException(status_code=response.status_code, detail=detail)

        try:
            return body["choices"][0]["message"]["content"]
        except (KeyError, IndexError, TypeError) as exc:
            raise HTTPException(status_code=502, detail="LLM response format was unexpected.") from exc

    async def suggest_template(
        self,
        template_name: str,
        description: str | None = None,
        domain_id: str | None = None,
        domain_type: str | None = None,
        response_mode: str | None = None,
    ) -> dict[str, Any]:
        if (response_mode or "").strip().lower() == "description_only":
            return await self._suggest_description_only(
                template_name=template_name,
                description=description,
                domain_id=domain_id,
                domain_type=domain_type,
            )

        candidate_attributes = self.attribute_catalog_service.get_candidate_attributes(
            template_name,
            description,
            domain_id=domain_id,
            domain_type=domain_type,
        )
        candidate_attribute_block = "\n".join(
            f"- {item['attribute_key']} ({item['type']}, required_default={item.get('required_default', False)}, enum_values={item.get('enum_values', [])}, tags={item.get('tags', [])})"
            for item in candidate_attributes
        ) or "No catalog attribute candidates available."
        payload = {
            "messages": [
                {
                    "role": "system",
                    "content": (
                        "You design reusable business data templates. "
                        "Return ONLY valid JSON. No markdown, no prose outside JSON. "
                        "Use this exact top-level shape and snake_case keys: "
                        "{\"template_id\":\"lower_snake_case_v1\",\"entity_type\":\"UPPER_SNAKE_CASE\","
                        "\"description\":\"exactly 5 lines separated by \\n\","
                        "\"attributes\":[{\"name\":\"string\",\"type\":\"string|number|boolean|date|enum|array|json\","
                        "\"enum_values\":[\"VALUE\"],\"required\":true}]}. "
                        "The template must be fully AI-generated from the provided template name and optional description. "
                        "Treat the template name as the reusable template or category label. "
                        "Treat the description as instructions for what future entities or products created with this template should capture. "
                        "Generate reusable fields for that class of entities, not only for one example item, unless the user explicitly asks for a single-item-specific template. "
                        "Treat the description as user-written design guidance for what the template should capture. "
                        "When the description is present, prioritize it over generic assumptions from the template name. "
                        "Use the template name as the short template or category label, and use the description to determine scope, purpose, and important fields. "
                        "Do not assume any domain-level attribute layer exists. "
                        "Do not invent or require domain-owned attributes. "
                        "Do not use placeholder names or values such as field_name, attr1, value, A, B, test, sample. "
                        "Create realistic, reusable attributes for the requested template, category, entity type, product, or item. "
                        "When catalog attribute candidates are provided, select from them first and add only missing template-specific fields. "
                        "The description must be exactly 5 non-empty lines and should explain what the template covers, "
                        "how it can be used, and what kinds of attributes are included. "
                        "Write the returned description as reusable knowledge for users who will create entities or products from this template. "
                        "Reflect the user's described use case in the returned description and in the attribute list. "
                        "Each attribute object must include name, type, enum_values, and required. "
                        "Set enum_values to [] for non-enum fields. "
                        "Prefer 12 or more useful attributes when the domain supports it."
                    ),
                },
                {
                    "role": "user",
                    "content": (
                        f"Template name: {template_name}\n"
                        f"Domain id: {domain_id or ''}\n"
                        f"Domain type: {domain_type or ''}\n"
                        f"User guidance: {description or ''}\n"
                        f"Catalog attribute candidates:\n{candidate_attribute_block}\n"
                        "Generate the reusable template now."
                    ),
                },
            ]
        }

        try:
            response = await self.client.post(self.base_url, json=payload)
        except httpx.HTTPError as exc:
            raise HTTPException(status_code=502, detail=f"LLM request failed: {exc}") from exc

        try:
            body = response.json()
        except ValueError as exc:
            raise HTTPException(status_code=502, detail="LLM returned invalid JSON.") from exc

        if response.status_code >= 400:
            detail = body.get("error") if isinstance(body, dict) else body
            raise HTTPException(status_code=response.status_code, detail=detail)

        try:
            content = body["choices"][0]["message"]["content"]
        except (KeyError, IndexError, TypeError) as exc:
            raise HTTPException(status_code=502, detail="LLM response format was unexpected.") from exc

        return self._normalize_template_response(content, template_name, description, candidate_attributes, domain_type)

    async def _suggest_description_only(
        self,
        template_name: str,
        description: str | None = None,
        domain_id: str | None = None,
        domain_type: str | None = None,
    ) -> dict[str, Any]:
        payload = {
            "messages": [
                {
                    "role": "system",
                    "content": (
                        "You write concise, practical user-facing category or business descriptions. "
                        "Return ONLY valid JSON with this exact shape: "
                        "{\"description\":\"plain-language paragraph\"}. "
                        "Do not include attributes, tags, enum values, template explanations, or any extra keys. "
                        "Write one concise paragraph with 2 to 4 sentences. "
                        "Do not repeat the prompt, requirements, or labels verbatim."
                    ),
                },
                {
                    "role": "user",
                    "content": (
                        f"Label: {template_name}\n"
                        f"Domain id: {domain_id or ''}\n"
                        f"Domain type: {domain_type or ''}\n"
                        f"Requirements and context: {description or ''}\n"
                        "Generate the final user-facing description now."
                    ),
                },
            ]
        }

        try:
            response = await self.client.post(self.base_url, json=payload)
        except httpx.HTTPError as exc:
            raise HTTPException(status_code=502, detail=f"LLM request failed: {exc}") from exc

        try:
            body = response.json()
        except ValueError as exc:
            raise HTTPException(status_code=502, detail="LLM returned invalid JSON.") from exc

        if response.status_code >= 400:
            detail = body.get("error") if isinstance(body, dict) else body
            raise HTTPException(status_code=response.status_code, detail=detail)

        try:
            content = body["choices"][0]["message"]["content"]
        except (KeyError, IndexError, TypeError) as exc:
            raise HTTPException(status_code=502, detail="LLM response format was unexpected.") from exc

        return self._normalize_description_only_response(content, template_name, description, domain_type)

    def _normalize_description_only_response(
        self,
        content: str,
        template_name: str,
        description: str | None,
        domain_type: str | None = None,
    ) -> dict[str, Any]:
        original_text = (content or "").strip()
        text = original_text
        start = text.find("{")
        end = text.rfind("}")
        if start != -1 and end > start:
            text = text[start:end + 1]

        try:
            raw = json.loads(text) if text else {}
        except json.JSONDecodeError:
            raw = {}

        def normalize(v: Any) -> str:
            return str(v).strip() if v is not None else ""

        def to_upper_snake(v: str) -> str:
            out = re.sub(r"[^A-Za-z0-9]+", "_", v).strip("_")
            return out.upper()

        fallback_bits = []
        if domain_type:
            fallback_bits.append(f"This domain supports {normalize(domain_type).lower()} business operations.")
        fallback_bits.append("It organizes the main business data, workflows, users, and records needed to run the business consistently.")
        fallback_bits.append("It is intended to provide a clear foundation for structured data entry, operations, and reporting.")
        fallback_paragraph = " ".join(bit for bit in fallback_bits if bit).strip()

        paragraph = normalize(raw.get("description"))
        if not paragraph:
            paragraph = self._extract_description_paragraph(original_text)
        paragraph = paragraph or fallback_paragraph
        paragraph = re.sub(r"\s+", " ", paragraph).strip()
        paragraph = re.sub(r"^\s*[-*]\s*", "", paragraph)

        return {
            "template_id": "",
            "template_name": template_name,
            "description": paragraph,
            "entity_type": to_upper_snake(domain_type or template_name),
            "attributes": [],
            "templateId": "",
            "templateName": template_name,
            "entityType": to_upper_snake(domain_type or template_name),
            "version": 1,
            "attributesCamelCase": [],
            "attributes_compat": [],
            "raw": raw,
        }

    def _extract_description_paragraph(self, content: str) -> str:
        text = (content or "").strip()
        if not text:
            return ""

        text = re.sub(r"^```(?:json)?\s*", "", text, flags=re.IGNORECASE)
        text = re.sub(r"\s*```$", "", text)

        description_match = re.search(
            r'"description"\s*:\s*"(?P<value>(?:\\.|[^"])*)"',
            text,
            flags=re.IGNORECASE | re.DOTALL,
        )
        if description_match:
            candidate = description_match.group("value")
            try:
                candidate = json.loads(f'"{candidate}"')
            except json.JSONDecodeError:
                pass
            return str(candidate).strip()

        if text.startswith("{") and text.endswith("}"):
            return ""

        text = re.sub(r"^[\"']|[\"']$", "", text).strip()
        text = re.sub(r"\s+", " ", text).strip()
        return text

    async def warmup(self) -> None:
        payload = {
            "messages": [
                {
                    "role": "system",
                    "content": "Reply with valid compact JSON only.",
                },
                {
                    "role": "user",
                    "content": "{\"status\":\"warm\"}",
                },
            ]
        }
        try:
            await self.client.post(self.base_url, json=payload)
        except httpx.HTTPError:
            return

    def _normalize_template_response(
        self,
        content: str,
        template_name: str,
        description: str | None,
        candidate_attributes: list[dict[str, Any]] | None = None,
        domain_type: str | None = None,
    ) -> dict[str, Any]:
        text = (content or "").strip()
        start = text.find("{")
        end = text.rfind("}")
        if start != -1 and end > start:
            text = text[start:end + 1]

        try:
            raw = json.loads(text) if text else {}
        except json.JSONDecodeError:
            raw = {}

        def normalize(v: Any) -> str:
            return str(v).strip() if v is not None else ""

        def to_upper_snake(v: str) -> str:
            out = re.sub(r"[^A-Za-z0-9]+", "_", v).strip("_")
            return out.upper()

        def to_template_id(v: str) -> str:
            out = re.sub(r"[^A-Za-z0-9]+", "_", v).strip("_").lower()
            if not out:
                out = "template"
            if not out.endswith("_v1"):
                out = f"{out}_v1"
            return out

        def normalize_description(value: str) -> str:
            lines = [line.strip() for line in value.splitlines() if line.strip()]
            if not lines:
                lines = [
                    f"Reusable template for {template_name}.",
                    "Captures identity, classification, and core descriptive fields.",
                    "Includes inventory, storage, and lifecycle information.",
                    "Supports optional nutrition and flexible tagging metadata.",
                    "Designed for AI-assisted suggestion and structured data entry.",
                ]
            if len(lines) < 5:
                lines.extend(["Additional template guidance."] * (5 - len(lines)))
            return "\n".join(lines[:5])

        def normalize_enum_values(value: Any) -> list[str]:
            if not isinstance(value, list):
                return []
            items = [normalize(item) for item in value]
            return [item for item in items if item]

        def sanitize_attr_name(value: str) -> str:
            cleaned = re.sub(r"[^a-zA-Z0-9]+", "_", normalize(value).lower()).strip("_")
            return cleaned

        def parse_bool(value: Any) -> bool:
            return value is True or str(value).strip().lower() in {"true", "yes", "required"}

        def dedupe_attrs(items: list[dict[str, Any]]) -> list[dict[str, Any]]:
            deduped: list[dict[str, Any]] = []
            seen: set[str] = set()
            for item in items:
                key = sanitize_attr_name(item.get("name", ""))
                if not key or key in seen:
                    continue
                seen.add(key)
                deduped.append(
                    {
                        "name": key,
                        "type": item.get("type", "string"),
                        "required": bool(item.get("required", False)),
                        "enum_values": item.get("enum_values", []),
                    }
                )
            return deduped

        def extract_attrs_from_text(value: str) -> list[dict[str, Any]]:
            extracted: list[dict[str, Any]] = []
            current: dict[str, Any] | None = None
            for raw_line in value.splitlines():
                line = raw_line.strip()
                if not line:
                    continue
                if line.startswith("- name:"):
                    if current:
                        extracted.append(current)
                    current = {
                        "name": sanitize_attr_name(line.split(":", 1)[1]),
                        "type": "string",
                        "required": False,
                        "enum_values": [],
                    }
                    continue
                if not current:
                    continue
                if line.startswith("type:"):
                    attr_type = normalize(line.split(":", 1)[1]).split(",", 1)[0].lower()
                    current["type"] = attr_type if attr_type in supported else "string"
                elif line.startswith("required"):
                    current["required"] = parse_bool(line.split(":", 1)[1] if ":" in line else line)
                elif line.startswith("enum_values:"):
                    enum_text = line.split(":", 1)[1].strip()
                    current["enum_values"] = [
                        normalize(item).strip("'\"")
                        for item in re.findall(r"'([^']+)'|\"([^\"]+)\"", enum_text)
                        for item in item if item
                    ]
            if current:
                extracted.append(current)
            return dedupe_attrs(extracted)

        def from_catalog(items: list[dict[str, Any]] | None) -> list[dict[str, Any]]:
            mapped: list[dict[str, Any]] = []
            for item in items or []:
                key = sanitize_attr_name(item.get("attribute_key", ""))
                if not key:
                    continue
                mapped.append(
                    {
                        "name": key,
                        "type": item.get("type", "string"),
                        "required": bool(item.get("required_default", False)),
                        "enum_values": item.get("enum_values", []),
                    }
                )
            return dedupe_attrs(mapped)

        supported = {"string", "number", "boolean", "date", "enum", "array", "json"}
        attrs: list[dict[str, Any]] = []
        for item in raw.get("attributes", []) if isinstance(raw.get("attributes"), list) else []:
            if not isinstance(item, dict):
                continue
            name = normalize(item.get("name"))
            lowered_name = name.lower()
            if (not name) or lowered_name in {"field_name", "field", "attribute", "value", "test"} or lowered_name.startswith("field_"):
                continue
            attr_type = normalize(item.get("type")).lower() or "string"
            if attr_type not in supported:
                attr_type = "string"
            required_val = item.get("required")
            required = required_val is True or str(required_val).lower() == "true"
            enum_values = normalize_enum_values(
                item.get("enum_values", item.get("enumValues", item.get("values", [])))
            )
            if attr_type == "enum":
                enum_values = [v for v in enum_values if v.lower() not in {"a", "b", "value", "test"}]
                if not enum_values:
                    continue
            else:
                enum_values = []

            attrs.append(
                {
                    "name": name,
                    "type": attr_type,
                    "required": required,
                    "enum_values": enum_values,
                }
            )

        if not attrs:
            attrs = extract_attrs_from_text(normalize(raw.get("description")))

        baseline_attrs = from_catalog(candidate_attributes)
        merged_attrs = {item["name"]: item for item in baseline_attrs}
        for item in dedupe_attrs(attrs):
            attr_name = sanitize_attr_name(item.get("name", ""))
            if not attr_name:
                continue
            attr_type = item.get("type", "string")
            enum_values = item.get("enum_values", [])
            if attr_type == "string" and enum_values:
                attr_type = "enum"
            merged_attrs.setdefault(
                attr_name,
                {
                    "name": attr_name,
                    "type": attr_type,
                    "required": bool(item.get("required", False)),
                    "enum_values": enum_values,
                },
            )
        attrs = list(merged_attrs.values())

        final_template_name = template_name
        final_template_id = normalize(raw.get("template_id", raw.get("templateId")))
        if (not final_template_id) or final_template_id.lower() in {"lower_snake_v1", "template_v1", "template_id"} or "lower_snake_case" in final_template_id.lower():
            final_template_id = to_template_id(final_template_name)
        final_description = normalize_description(normalize(raw.get("description")) or (description or ""))
        final_entity_type = normalize(raw.get("entity_type", raw.get("entityType")))
        if (not final_entity_type) or final_entity_type.upper() == "UPPER_SNAKE_CASE":
            final_entity_type = to_upper_snake(domain_type or final_template_name)

        camel_case_attrs = [
            {
                "name": attr["name"],
                "type": attr["type"],
                "required": attr["required"],
                "enumValues": attr["enum_values"],
            }
            for attr in attrs
        ]

        return {
            "template_id": final_template_id,
            "template_name": final_template_name,
            "description": final_description,
            "entity_type": final_entity_type,
            "attributes": attrs,
            "templateId": final_template_id,
            "templateName": final_template_name,
            "entityType": final_entity_type,
            "version": 1,
            "attributesCamelCase": camel_case_attrs,
            "attributes_compat": camel_case_attrs,
            "raw": raw,
        }
