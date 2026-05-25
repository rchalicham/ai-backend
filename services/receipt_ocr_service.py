from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass
class ReceiptOcrResult:
    available: bool
    raw_text: str = ""
    lines: list[str] = field(default_factory=list)
    ocr_blocks: list[dict[str, Any]] = field(default_factory=list)
    warning: str = ""
    engine: str = "tesseract"

    def to_dict(self) -> dict[str, Any]:
        return {
            "available": self.available,
            "engine": self.engine,
            "rawText": self.raw_text,
            "rawLines": self.lines,
            "ocrBlocks": self.ocr_blocks,
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
            prepared = self._prepare_for_ocr(cv2, image)
            config = "--oem 3 --psm 6 -c preserve_interword_spaces=1"
            ocr_data = pytesseract.image_to_data(prepared, output_type=pytesseract.Output.DICT, config=config)
            blocks = self._blocks_from_tesseract(ocr_data)
            lines = self._lines_from_blocks(blocks)
            raw_text = "\n".join(lines)
            return ReceiptOcrResult(
                available=bool(raw_text.strip()),
                raw_text=raw_text,
                lines=lines,
                ocr_blocks=blocks,
                warning="" if raw_text.strip() else "no_text_detected",
            )
        except Exception as exc:
            return ReceiptOcrResult(available=False, warning=f"ocr_failed:{exc.__class__.__name__}")

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
