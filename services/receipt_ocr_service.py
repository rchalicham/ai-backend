from __future__ import annotations

import os
import re
from dataclasses import dataclass, field
from typing import Any


@dataclass
class ReceiptOcrResult:
    available: bool
    raw_text: str = ""
    lines: list[str] = field(default_factory=list)
    ocr_blocks: list[dict[str, Any]] = field(default_factory=list)
    variants: list[dict[str, Any]] = field(default_factory=list)
    warning: str = ""
    engine: str = "tesseract"

    def to_dict(self) -> dict[str, Any]:
        return {
            "available": self.available,
            "engine": self.engine,
            "rawText": self.raw_text,
            "rawLines": self.lines,
            "ocrBlocks": self.ocr_blocks,
            "ocrVariants": self.variants,
            "warning": self.warning,
        }


class ReceiptOcrService:
    """General OCR fallback for receipts when Donut returns no text."""

    def extract(self, image_bytes: bytes) -> ReceiptOcrResult:
        if not image_bytes:
            return ReceiptOcrResult(available=False, warning="empty_image")
        try:
            import cv2
            import numpy as np
            import pytesseract
        except Exception as exc:
            return ReceiptOcrResult(available=False, warning=f"ocr_unavailable:{exc.__class__.__name__}")

        try:
            data = np.frombuffer(image_bytes, dtype=np.uint8)
            image = cv2.imdecode(data, cv2.IMREAD_COLOR)
            if image is None:
                return ReceiptOcrResult(available=False, warning="unable_to_decode_image")
            candidates = self._ocr_candidates(cv2, image)
            attempts: list[dict[str, Any]] = []
            for name, candidate_image, psm in candidates:
                config = f"--oem 3 --psm {psm} -c preserve_interword_spaces=1"
                ocr_data = pytesseract.image_to_data(candidate_image, output_type=pytesseract.Output.DICT, config=config)
                blocks = self._blocks_from_tesseract(ocr_data)
                lines = self._lines_from_blocks(blocks)
                score = self._ocr_line_score(lines)
                attempts.append({
                    "name": name,
                    "psm": psm,
                    "image": candidate_image,
                    "config": config,
                    "score": score,
                    "blocks": blocks,
                    "lines": lines,
                })
            attempts.sort(key=lambda attempt: attempt["score"], reverse=True)
            for attempt in attempts[: self._string_variant_count()]:
                string_text = pytesseract.image_to_string(attempt["image"], config=attempt["config"])
                string_lines = [self._normalize_line(line) for line in string_text.splitlines() if self._normalize_line(line)]
                attempt["lines"] = self._merge_line_sets(attempt["lines"], string_lines)
                attempt["score"] = self._ocr_line_score(attempt["lines"])
            attempts.sort(key=lambda attempt: attempt["score"], reverse=True)
            best = attempts[0] if attempts else {"name": "none", "score": 0.0, "blocks": [], "lines": []}
            lines = self._merge_ocr_lines(attempts[:6])
            best_lines = best.get("lines") or []
            if self._ocr_line_score(lines) < float(best.get("score") or 0.0) * 0.75:
                lines = best_lines
            blocks = best.get("blocks") or []
            raw_text = "\n".join(lines)
            return ReceiptOcrResult(
                available=bool(raw_text.strip()),
                raw_text=raw_text,
                lines=lines,
                ocr_blocks=blocks,
                variants=[
                    {
                        "engine": "tesseract",
                        "variant": attempt["name"],
                        "psm": attempt["psm"],
                        "score": round(float(attempt["score"] or 0.0), 3),
                        "lines": attempt["lines"][:120],
                    }
                    for attempt in attempts[:6]
                ],
                warning="" if raw_text.strip() else "no_text_detected",
                engine=f"tesseract:{best.get('name', 'none')}",
            )
        except Exception as exc:
            return ReceiptOcrResult(available=False, warning=f"ocr_failed:{exc.__class__.__name__}")

    def _string_variant_count(self) -> int:
        try:
            return max(0, min(6, int(os.getenv("RECEIPT_OCR_STRING_VARIANTS", "3"))))
        except ValueError:
            return 3

    def _ocr_candidates(self, cv2: Any, image: Any) -> list[tuple[str, Any, int]]:
        gray = cv2.cvtColor(image, cv2.COLOR_BGR2GRAY)
        prepared = self._prepare_for_ocr(cv2, image)
        upscaled = self._upscale_for_ocr(cv2, gray)
        clahe = cv2.createCLAHE(clipLimit=2.8, tileGridSize=(8, 8)).apply(upscaled)
        background = cv2.medianBlur(upscaled, 31)
        flattened = cv2.divide(upscaled, background, scale=255)
        threshold = cv2.adaptiveThreshold(
            flattened,
            255,
            cv2.ADAPTIVE_THRESH_GAUSSIAN_C,
            cv2.THRESH_BINARY,
            41,
            9,
        )
        candidates: list[tuple[str, Any, int]] = []
        for name, candidate in (
            ("prepared", prepared),
            ("gray", upscaled),
            ("flattened", flattened),
            ("adaptive_threshold", threshold),
        ):
            for psm in (4, 6):
                candidates.append((name, candidate, psm))
        candidates.append(("gray", upscaled, 11))
        candidates.append(("flattened", flattened, 11))
        return candidates

    def _merge_ocr_lines(self, attempts: list[dict[str, Any]], max_lines: int = 180) -> list[str]:
        selected: list[str] = []
        seen: set[str] = set()
        for attempt in attempts:
            for raw_line in attempt.get("lines") or []:
                line = self._normalize_line(raw_line)
                if not line:
                    continue
                key = re.sub(r"[^a-z0-9.]+", "", line.lower())
                if not key or key in seen:
                    continue
                if self._line_quality_score(line) < 4:
                    continue
                seen.add(key)
                selected.append(line)
                if len(selected) >= max_lines:
                    return selected
        return selected

    def _merge_line_sets(self, *line_sets: list[str]) -> list[str]:
        selected: list[str] = []
        seen: set[str] = set()
        for lines in line_sets:
            for raw_line in lines:
                line = self._normalize_line(raw_line)
                key = re.sub(r"[^a-z0-9.]+", "", line.lower())
                if not line or not key or key in seen:
                    continue
                seen.add(key)
                selected.append(line)
        return selected

    def _normalize_line(self, line: Any) -> str:
        return re.sub(r"\s+", " ", str(line or "").replace("|", "I")).strip()

    def _line_quality_score(self, line: str) -> float:
        normalized = self._normalize_line(line)
        if not normalized:
            return 0.0
        alpha = sum(char.isalpha() for char in normalized)
        digits = sum(char.isdigit() for char in normalized)
        price = 18 if re.search(r"\$?\d+[\.,]\d{2}", normalized) else 0
        date = 14 if re.search(r"\d{1,2}/\d{1,2}/\d{2,4}", normalized) else 0
        noise_penalty = len(re.findall(r"[^A-Za-z0-9\s$.,:/#&()'@+-]", normalized)) * 4
        return len(normalized) + alpha + digits + price + date - noise_penalty

    def _prepare_for_ocr(self, cv2: Any, image: Any) -> Any:
        height, width = image.shape[:2]
        scale = max(1.0, min(2.4, 1200.0 / max(width, 1)))
        if scale > 1.01:
            image = cv2.resize(image, (int(width * scale), int(height * scale)), interpolation=cv2.INTER_CUBIC)
        gray = cv2.cvtColor(image, cv2.COLOR_BGR2GRAY)
        background = cv2.medianBlur(gray, 31)
        flattened = cv2.divide(gray, background, scale=255)
        denoised = cv2.fastNlMeansDenoising(flattened, None, 10, 7, 21)
        clahe = cv2.createCLAHE(clipLimit=2.2, tileGridSize=(8, 8))
        contrasted = clahe.apply(denoised)
        return cv2.adaptiveThreshold(
            contrasted,
            255,
            cv2.ADAPTIVE_THRESH_GAUSSIAN_C,
            cv2.THRESH_BINARY,
            41,
            9,
        )

    def _upscale_for_ocr(self, cv2: Any, image: Any) -> Any:
        height, width = image.shape[:2]
        scale = max(1.0, min(2.4, 1200.0 / max(width, 1)))
        if scale <= 1.01:
            return image
        return cv2.resize(image, (int(width * scale), int(height * scale)), interpolation=cv2.INTER_CUBIC)

    def _ocr_line_score(self, lines: list[str]) -> float:
        text = "\n".join(lines).upper()
        item_like = sum(
            1 for line in lines
            if any(char.isalpha() for char in line) and bool(re.search(r"\d{1,4}[.,]\d{2}", line))
        )
        department_hits = sum(1 for term in ("DAIRY", "GROCERY", "PRODUCE") if term in text)
        total_hits = sum(1 for term in ("BALANCE DUE", "TOTAL TAX", "ITEMS SOLD", "TOTAL NUMBER") if term in text)
        legal_penalty = text.count("SWEEPSTAKES") + text.count("NO PURCHASE") + text.count("SURVEY")
        return (item_like * 4.0) + (department_hits * 5.0) + (total_hits * 2.0) - (legal_penalty * 1.5) + min(len(lines), 90) * 0.02

    def _blocks_from_tesseract(self, data: dict[str, list[Any]]) -> list[dict[str, Any]]:
        count = len(data.get("text", []))
        blocks: list[dict[str, Any]] = []
        for index in range(count):
            text = str(data.get("text", [""])[index] or "").strip()
            if not text:
                continue
            try:
                confidence = float(data.get("conf", ["-1"])[index])
            except Exception:
                confidence = -1.0
            if confidence < 18:
                continue
            blocks.append({
                "text": text,
                "value": text,
                "confidence": max(0.0, min(1.0, confidence / 100.0)),
                "x": int(data.get("left", [0])[index] or 0),
                "y": int(data.get("top", [0])[index] or 0),
                "width": int(data.get("width", [0])[index] or 0),
                "height": int(data.get("height", [0])[index] or 0),
                "block": int(data.get("block_num", [0])[index] or 0),
                "paragraph": int(data.get("par_num", [0])[index] or 0),
                "line": int(data.get("line_num", [0])[index] or 0),
                "word": int(data.get("word_num", [0])[index] or 0),
                "source": "tesseract.word",
            })
        return blocks

    def _lines_from_blocks(self, blocks: list[dict[str, Any]]) -> list[str]:
        grouped: dict[tuple[int, int, int], list[dict[str, Any]]] = {}
        for block in blocks:
            key = (int(block.get("block") or 0), int(block.get("paragraph") or 0), int(block.get("line") or 0))
            grouped.setdefault(key, []).append(block)
        lines: list[tuple[int, str]] = []
        for words in grouped.values():
            words.sort(key=lambda item: int(item.get("x") or 0))
            text = " ".join(str(word.get("text") or "").strip() for word in words if str(word.get("text") or "").strip())
            if text:
                y = min(int(word.get("y") or 0) for word in words)
                lines.append((y, text))
        return [text for _, text in sorted(lines, key=lambda item: item[0])]
