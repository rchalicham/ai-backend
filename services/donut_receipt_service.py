from __future__ import annotations

import asyncio
import base64
import json
import os
import re
from dataclasses import dataclass
from io import BytesIO
from typing import Any

import httpx

from services.receipt_image_isolation import ReceiptImageIsolationService
from services.receipt_row_consolidation import ReceiptRowConsolidationPipeline


class DonutUnavailableError(RuntimeError):
    pass


@dataclass
class DonutReceiptResult:
    available: bool
    model: str
    merchant: str = ""
    date: str = ""
    items: list[dict[str, Any]] | None = None
    subtotal: str = ""
    tax: str = ""
    total: str = ""
    confidence: float = 0.0
    raw: dict[str, Any] | None = None
    warning: str = ""

    def to_dict(self) -> dict[str, Any]:
        return {
            "available": self.available,
            "model": self.model,
            "merchant": self.merchant,
            "date": self.date,
            "items": self.items or [],
            "subtotal": self.subtotal,
            "tax": self.tax,
            "total": self.total,
            "confidence": round(float(self.confidence or 0.0), 3),
            "raw": self.raw or {},
            "warning": self.warning,
        }


class DonutReceiptService:
    """Lazy Donut CORD-v2 inference wrapper.

    The model dependencies are intentionally lazy so CPU-only local development and
    CI can still import the app. Production GPU containers can install
    torch/transformers/Pillow and set DONUT_RECEIPT_ENABLED=true.
    """

    def __init__(self) -> None:
        self.model_name = os.getenv("DONUT_RECEIPT_MODEL", "naver-clova-ix/donut-base-finetuned-cord-v2")
        self.enabled = os.getenv("DONUT_RECEIPT_ENABLED", "false").lower() in {"1", "true", "yes", "on"}
        self.max_concurrency = int(os.getenv("DONUT_RECEIPT_MAX_CONCURRENCY", "2"))
        self.max_new_tokens = int(os.getenv("DONUT_RECEIPT_MAX_NEW_TOKENS", "768"))
        self._processor = None
        self._model = None
        self._torch = None
        self._device = "cpu"
        self._load_lock = asyncio.Lock()
        self._inference_semaphore = asyncio.Semaphore(max(1, self.max_concurrency))
        self.row_consolidation = ReceiptRowConsolidationPipeline()
        self.image_isolation = ReceiptImageIsolationService(
            debug_preview=os.getenv("RECEIPT_ISOLATION_DEBUG_PREVIEW", "false").lower() in {"1", "true", "yes", "on"}
        )

    def decode_base64_image(self, image_base64: str) -> bytes:
        value = (image_base64 or "").strip()
        if not value:
            return b""
        if "," in value and value.lower().startswith("data:"):
            value = value.split(",", 1)[1]
        try:
            return base64.b64decode(value, validate=True)
        except Exception as exc:
            raise ValueError("image_base64 is not valid base64 image data.") from exc

    async def fetch_image_url(self, image_url: str) -> bytes:
        value = (image_url or "").strip()
        if not value:
            return b""
        async with httpx.AsyncClient(timeout=float(os.getenv("DONUT_RECEIPT_IMAGE_TIMEOUT_SECONDS", "45"))) as client:
            response = await client.get(value)
            response.raise_for_status()
            content_type = response.headers.get("content-type", "")
            if content_type and not content_type.lower().startswith(("image/", "application/octet-stream")):
                raise ValueError(f"image_url did not return an image content type: {content_type}")
            return response.content

    async def analyze_image_bytes(self, image_bytes: bytes) -> dict[str, Any]:
        if not image_bytes:
            return DonutReceiptResult(
                available=False,
                model=self.model_name,
                warning="No processed receipt image was provided to Donut.",
            ).to_dict()
        isolation = self.image_isolation.isolate(image_bytes)
        isolated_image_bytes = isolation.image_bytes
        if not self.enabled:
            return DonutReceiptResult(
                available=False,
                model=self.model_name,
                warning="Donut receipt model is disabled. Set DONUT_RECEIPT_ENABLED=true in the model service container.",
            ).to_dict() | {"receiptIsolation": isolation.diagnostics}
        async with self._inference_semaphore:
            await self._ensure_loaded()
            loop = asyncio.get_running_loop()
            result = await loop.run_in_executor(None, self._infer_sync, isolated_image_bytes)
            logo_candidates = await loop.run_in_executor(None, self._logo_header_candidates, isolated_image_bytes)
            result["receiptIsolation"] = isolation.diagnostics
            result["logoCandidates"] = logo_candidates
            result["visualIdentity"] = {
                "schemaVersion": "receipt-visual-identity-v1",
                "strategy": "isolated_receipt_header_logo_crop",
                "candidateCount": len(logo_candidates),
                "candidates": logo_candidates,
            }
            return result

    async def _ensure_loaded(self) -> None:
        if self._model is not None and self._processor is not None:
            return
        async with self._load_lock:
            if self._model is not None and self._processor is not None:
                return
            try:
                import torch
                from transformers import DonutProcessor, VisionEncoderDecoderModel
            except Exception as exc:
                raise DonutUnavailableError(
                    "Donut dependencies are not installed. Install torch, transformers, and Pillow in the AI backend image."
                ) from exc
            self._torch = torch
            self._device = "cuda" if torch.cuda.is_available() else "cpu"
            self._processor = DonutProcessor.from_pretrained(self.model_name)
            self._model = VisionEncoderDecoderModel.from_pretrained(self.model_name)
            self._model.to(self._device)
            self._model.eval()

    def _infer_sync(self, image_bytes: bytes) -> dict[str, Any]:
        try:
            from PIL import Image
        except Exception as exc:
            raise DonutUnavailableError("Pillow is required for Donut image decoding.") from exc

        image = Image.open(BytesIO(image_bytes)).convert("RGB")
        task_prompt = "<s_cord-v2>"
        decoder_input_ids = self._processor.tokenizer(
            task_prompt,
            add_special_tokens=False,
            return_tensors="pt",
        ).input_ids.to(self._device)
        pixel_values = self._processor(image, return_tensors="pt").pixel_values.to(self._device)
        with self._torch.no_grad():
            outputs = self._model.generate(
                pixel_values,
                decoder_input_ids=decoder_input_ids,
                early_stopping=True,
                pad_token_id=self._processor.tokenizer.pad_token_id,
                eos_token_id=self._processor.tokenizer.eos_token_id,
                use_cache=True,
                num_beams=1,
                bad_words_ids=[[self._processor.tokenizer.unk_token_id]],
                return_dict_in_generate=True,
                output_scores=True,
                max_new_tokens=self.max_new_tokens,
            )
        sequence = self._processor.batch_decode(outputs.sequences)[0]
        sequence = sequence.replace(self._processor.tokenizer.eos_token, "").replace(self._processor.tokenizer.pad_token, "")
        sequence = re.sub(r"<.*?>", "", sequence, count=1).strip()
        parsed = self._parse_donut_sequence(sequence)
        return DonutReceiptResult(
            available=True,
            model=self.model_name,
            merchant=parsed.get("merchant", ""),
            date=parsed.get("date", ""),
            items=parsed.get("items", []),
            subtotal=parsed.get("subtotal", ""),
            tax=parsed.get("tax", ""),
            total=parsed.get("total", ""),
            confidence=self._score(parsed),
            raw=parsed,
        ).to_dict()

    def _logo_header_candidates(self, image_bytes: bytes) -> list[dict[str, Any]]:
        crops = self._logo_header_crops(image_bytes)
        candidates: list[dict[str, Any]] = []
        normalizer = self.row_consolidation.merchants
        for crop in crops:
            try:
                result = self._infer_sync(crop["imageBytes"])
            except Exception:
                continue
            merchant = str(result.get("merchant") or "").strip()
            if not merchant:
                continue
            if not normalizer._looks_like_header_merchant(merchant):
                continue
            if normalizer._looks_like_generic_business_fragment(merchant):
                continue
            confidence = max(0.62, min(0.9, float(result.get("confidence") or 0.0) + 0.1))
            candidates.append({
                "merchant": merchant,
                "confidence": round(confidence, 3),
                "source": "logo_header_crop",
                "crop": crop["crop"],
                "model": result.get("model", self.model_name),
                "evidence": [
                    {
                        "type": "visual_logo_crop",
                        "value": merchant,
                        "confidence": round(confidence, 3),
                        "bbox": crop["crop"],
                    }
                ],
            })
        return self._dedupe_logo_candidates(candidates)

    def _logo_header_crops(self, image_bytes: bytes) -> list[dict[str, Any]]:
        try:
            import cv2
            import numpy as np
        except Exception:
            return []
        try:
            image = self.image_isolation._decode(cv2, np, image_bytes)
        except Exception:
            return []
        height, width = image.shape[:2]
        if height <= 0 or width <= 0:
            return []
        crop_specs = [
            {"x": 0.0, "y": 0.0, "width": 1.0, "height": 0.28, "name": "top_full"},
            {"x": 0.0, "y": 0.0, "width": 1.0, "height": 0.4, "name": "top_header"},
            {"x": 0.05, "y": 0.0, "width": 0.9, "height": 0.25, "name": "top_center"},
        ]
        crops: list[dict[str, Any]] = []
        for spec in crop_specs:
            left = max(0, int(width * spec["x"]))
            top = max(0, int(height * spec["y"]))
            right = min(width, int(width * (spec["x"] + spec["width"])))
            bottom = min(height, int(height * (spec["y"] + spec["height"])))
            if right - left < 20 or bottom - top < 20:
                continue
            crop = image[top:bottom, left:right]
            crop = self._prepare_logo_crop(cv2, crop)
            try:
                crops.append({
                    "imageBytes": self.image_isolation._encode(cv2, crop),
                    "crop": {
                        "name": spec["name"],
                        "x": round(left / width, 4),
                        "y": round(top / height, 4),
                        "width": round((right - left) / width, 4),
                        "height": round((bottom - top) / height, 4),
                    },
                })
            except Exception:
                continue
        return crops

    def _prepare_logo_crop(self, cv2: Any, crop: Any) -> Any:
        height, width = crop.shape[:2]
        scale = 2.0 if max(height, width) < 900 else 1.4
        enlarged = cv2.resize(crop, (max(1, int(width * scale)), max(1, int(height * scale))), interpolation=cv2.INTER_CUBIC)
        gray = cv2.cvtColor(enlarged, cv2.COLOR_BGR2GRAY)
        background = cv2.medianBlur(gray, 21)
        flattened = cv2.divide(gray, background, scale=255)
        clahe = cv2.createCLAHE(clipLimit=2.6, tileGridSize=(8, 8))
        contrasted = clahe.apply(flattened)
        return cv2.cvtColor(contrasted, cv2.COLOR_GRAY2BGR)

    def _dedupe_logo_candidates(self, candidates: list[dict[str, Any]]) -> list[dict[str, Any]]:
        output: list[dict[str, Any]] = []
        seen: set[str] = set()
        for candidate in sorted(candidates, key=lambda item: float(item.get("confidence") or 0.0), reverse=True):
            key = re.sub(r"[^A-Z0-9]+", "", str(candidate.get("merchant") or "").upper())
            if not key or key in seen:
                continue
            seen.add(key)
            output.append(candidate)
        return output[:5]

    def _parse_donut_sequence(self, sequence: str) -> dict[str, Any]:
        try:
            parsed = self._processor.token2json(sequence)
        except Exception:
            try:
                parsed = json.loads(sequence)
            except Exception:
                parsed = {"rawText": sequence}
        return self._normalize_cord_json(parsed if isinstance(parsed, dict) else {"raw": parsed})

    def _normalize_cord_json(self, value: dict[str, Any]) -> dict[str, Any]:
        menu = value.get("menu") or value.get("items") or []
        if isinstance(menu, dict):
            menu = [menu]
        items = []
        for index, item in enumerate(menu if isinstance(menu, list) else []):
            if not isinstance(item, dict):
                continue
            name = self._first_text(item, "nm", "name", "description", "item")
            amount = self._first_amount(item, "price", "amount", "totalprice", "subtotal")
            qty = self._first_text(item, "cnt", "qty", "quantity", default="1")
            if name or amount:
                items.append({
                    "id": index + 1,
                    "name": name,
                    "qty": qty or "1",
                    "count": qty or "1",
                    "amount": amount,
                    "price": amount,
                    "confidence": 0.82,
                })
        total_block = value.get("total") if isinstance(value.get("total"), dict) else {}
        subtotal_block = value.get("sub_total") if isinstance(value.get("sub_total"), dict) else {}
        return {
            "merchant": self._first_text(value, "store_name", "merchant", "company", "storeName"),
            "date": self._first_text(value, "date", "purchaseDate"),
            "items": items,
            "subtotal": self._first_amount(subtotal_block, "subtotal_price", "subtotal", "sub_total") or self._first_amount(value, "subtotal"),
            "tax": self._first_amount(subtotal_block, "tax_price", "tax"),
            "total": self._first_amount(total_block, "total_price", "total") or self._first_amount(value, "total"),
            "raw": value,
        }

    def consolidate_receipt_rows(
        self,
        donut_json: dict[str, Any],
        raw_text: str = "",
        lines: list[str] | None = None,
        ocr_blocks: list[dict[str, Any]] | None = None,
        parser_json: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        has_ocr_text = bool(str(raw_text or "").strip() or any(str(line).strip() for line in (lines or [])) or ocr_blocks)
        if not donut_json.get("available") and not has_ocr_text:
            return donut_json
        return self.row_consolidation.normalize(
            donut=donut_json,
            raw_text=raw_text,
            lines=lines,
            ocr_blocks=ocr_blocks,
            parser_json=parser_json,
        )

    def _first_text(self, data: dict[str, Any], *keys: str, default: str = "") -> str:
        for key in keys:
            value = data.get(key)
            if isinstance(value, dict):
                value = value.get("text") or value.get("value")
            if value not in (None, ""):
                return str(value).strip()
        return default

    def _first_amount(self, data: dict[str, Any], *keys: str) -> str:
        text = self._first_text(data, *keys)
        match = re.search(r"-?\d+(?:[.,]\d{2})?", text.replace(",", "."))
        return match.group(0) if match else ""

    def _score(self, parsed: dict[str, Any]) -> float:
        score = 0.0
        if parsed.get("merchant"):
            score += 0.22
        if parsed.get("date"):
            score += 0.12
        if parsed.get("items"):
            score += min(0.34, len(parsed["items"]) * 0.08)
        if parsed.get("total"):
            score += 0.2
        if parsed.get("subtotal") or parsed.get("tax"):
            score += 0.12
        return min(1.0, score)
