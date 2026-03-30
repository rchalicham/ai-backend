from __future__ import annotations

import os
import json
import re
from typing import Any

import httpx
from fastapi import HTTPException

from services.attribute_catalog_service import AttributeCatalogService


class LLMService:
    def __init__(self, base_url: str | None = None):
        self.base_url = base_url or os.getenv(
            "LLM_URL",
            "http://host.docker.internal:8081/v1/chat/completions",
        )
        self.attribute_catalog_service = AttributeCatalogService()

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
            async with httpx.AsyncClient(timeout=60.0) as client:
                response = await client.post(self.base_url, json=payload)
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
    ) -> dict[str, Any]:
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
                        "Use the template name as the short domain label, and use the description to determine scope, purpose, and important fields. "
                        "Always include the configured domain attributes when catalog candidates are provided. "
                        "Do not invent replacements for configured domain attributes. "
                        "Do not use placeholder names or values such as field_name, attr1, value, A, B, test, sample. "
                        "Create realistic, reusable attributes for the requested domain. "
                        "When catalog attribute candidates are provided, select from them first and add only missing category-specific fields. "
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
            async with httpx.AsyncClient(timeout=60.0) as client:
                response = await client.post(self.base_url, json=payload)
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
