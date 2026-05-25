from __future__ import annotations

import base64
import math
from dataclasses import dataclass, field
from typing import Any


@dataclass
class ReceiptIsolationResult:
    image_bytes: bytes
    diagnostics: dict[str, Any] = field(default_factory=dict)


class ReceiptImageIsolationService:
    """Isolates the physical receipt before any OCR or Donut model sees pixels."""

    def __init__(self, debug_preview: bool = False) -> None:
        self.debug_preview = debug_preview

    def isolate(self, image_bytes: bytes, debug: bool | None = None) -> ReceiptIsolationResult:
        diagnostics: dict[str, Any] = {
            "schemaVersion": "receipt-image-isolation-v1",
            "applied": False,
            "engine": "opencv",
            "ocrInputPolicy": "raw_image_never_forwarded",
            "warnings": [],
            "contours": [],
            "selectedContour": None,
            "receiptMask": {},
            "sectionBoundaries": [],
        }
        if not image_bytes:
            diagnostics["warnings"].append("empty_image")
            return ReceiptIsolationResult(image_bytes=b"", diagnostics=diagnostics)
        try:
            import cv2
            import numpy as np
        except Exception as exc:
            diagnostics["engine"] = "unavailable"
            diagnostics["warnings"].append(f"opencv_unavailable:{exc.__class__.__name__}")
            return ReceiptIsolationResult(image_bytes=image_bytes, diagnostics=diagnostics)

        try:
            source = self._decode(cv2, np, image_bytes)
            original_height, original_width = source.shape[:2]
            working, scale = self._scale_for_detection(cv2, source)
            candidates = self._detect_receipt_candidates(cv2, np, working)
            diagnostics["source"] = {"width": original_width, "height": original_height}
            diagnostics["working"] = {"width": working.shape[1], "height": working.shape[0], "scale": round(scale, 4)}
            diagnostics["contours"] = [candidate["diagnostic"] for candidate in candidates[:10]]
            if not candidates:
                diagnostics["warnings"].append("receipt_contour_not_found")
                normalized = self._enhance_receipt(cv2, source)
                return ReceiptIsolationResult(
                    image_bytes=self._encode(cv2, normalized),
                    diagnostics={
                        **diagnostics,
                        "applied": True,
                        "receiptIsolated": False,
                        "backgroundRemoved": False,
                        "strategy": "full_image_enhancement_no_raw_passthrough",
                    },
                )

            selected = candidates[0]
            quad = (selected["quad"] / scale).astype("float32")
            warped = self._warp_receipt(cv2, np, source, quad)
            cleaned = self._clean_receipt_pixels(cv2, warped)
            output_bytes = self._encode(cv2, cleaned)
            diagnostics["applied"] = True
            diagnostics["receiptIsolated"] = True
            diagnostics["backgroundRemoved"] = True
            diagnostics["strategy"] = "largest_document_contour_perspective_warp"
            diagnostics["selectedContour"] = {
                **selected["diagnostic"],
                "quad": [{"x": round(float(point[0] / scale), 2), "y": round(float(point[1] / scale), 2)} for point in selected["quad"]],
            }
            diagnostics["output"] = {"width": cleaned.shape[1], "height": cleaned.shape[0], "bytes": len(output_bytes)}
            diagnostics["receiptMask"] = self._mask_diagnostics(cv2, np, working, selected["quad"])
            diagnostics["sectionBoundaries"] = self._section_boundaries(cv2, cleaned)
            include_debug_preview = self.debug_preview if debug is None else debug
            if include_debug_preview:
                diagnostics["previews"] = self._debug_previews(cv2, source, working, selected["quad"], cleaned)
            return ReceiptIsolationResult(image_bytes=output_bytes, diagnostics=diagnostics)
        except Exception as exc:
            diagnostics["engine"] = "opencv_error"
            diagnostics["warnings"].append(f"receipt_isolation_failed:{exc.__class__.__name__}")
            return ReceiptIsolationResult(image_bytes=image_bytes, diagnostics=diagnostics)

    def _decode(self, cv2: Any, np: Any, image_bytes: bytes) -> Any:
        data = np.frombuffer(image_bytes, dtype=np.uint8)
        image = cv2.imdecode(data, cv2.IMREAD_COLOR)
        if image is None:
            raise ValueError("unable_to_decode_image")
        return image

    def _encode(self, cv2: Any, image: Any) -> bytes:
        success, encoded = cv2.imencode(".jpg", image, [int(cv2.IMWRITE_JPEG_QUALITY), 94])
        if not success:
            raise ValueError("unable_to_encode_isolated_receipt")
        return encoded.tobytes()

    def _scale_for_detection(self, cv2: Any, image: Any) -> tuple[Any, float]:
        height, width = image.shape[:2]
        max_side = max(width, height)
        if max_side <= 1600:
            return image.copy(), 1.0
        scale = 1600.0 / max_side
        resized = cv2.resize(image, (max(1, round(width * scale)), max(1, round(height * scale))), interpolation=cv2.INTER_AREA)
        return resized, scale

    def _detect_receipt_candidates(self, cv2: Any, np: Any, image: Any) -> list[dict[str, Any]]:
        candidates = self._detect_bright_paper_candidates(cv2, np, image)
        candidates.extend(self._detect_edge_receipt_candidates(cv2, np, image))
        candidates.sort(key=lambda item: item["score"], reverse=True)
        return self._dedupe_candidates(candidates)

    def _detect_bright_paper_candidates(self, cv2: Any, np: Any, image: Any) -> list[dict[str, Any]]:
        height, width = image.shape[:2]
        gray = cv2.cvtColor(image, cv2.COLOR_BGR2GRAY)
        blurred = cv2.GaussianBlur(gray, (7, 7), 0)
        _, threshold = cv2.threshold(blurred, 0, 255, cv2.THRESH_BINARY + cv2.THRESH_OTSU)
        if cv2.countNonZero(threshold) > threshold.size * 0.82:
            threshold = cv2.adaptiveThreshold(
                blurred,
                255,
                cv2.ADAPTIVE_THRESH_GAUSSIAN_C,
                cv2.THRESH_BINARY,
                61,
                -5,
            )
        kernel = cv2.getStructuringElement(cv2.MORPH_RECT, (17, 17))
        mask = cv2.morphologyEx(threshold, cv2.MORPH_CLOSE, kernel, iterations=2)
        mask = cv2.morphologyEx(mask, cv2.MORPH_OPEN, cv2.getStructuringElement(cv2.MORPH_RECT, (5, 5)), iterations=1)
        contours, _ = cv2.findContours(mask, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
        image_area = float(width * height)
        candidates: list[dict[str, Any]] = []
        for contour in contours:
            area = float(cv2.contourArea(contour))
            if area < image_area * 0.10 or area > image_area * 0.96:
                continue
            x, y, rect_width, rect_height = cv2.boundingRect(contour)
            if rect_width < width * 0.18 or rect_height < height * 0.22:
                continue
            aspect = max(rect_width, rect_height) / max(1, min(rect_width, rect_height))
            if aspect < 1.15:
                continue
            quad = self._quad_from_contour(cv2, np, contour)
            quad_area = self._quad_area(quad)
            if quad_area < image_area * 0.10 or quad_area > image_area * 0.96:
                continue
            rectangularity = min(1.0, area / max(quad_area, 1.0))
            paper_region = gray[y:y + rect_height, x:x + rect_width]
            mean_inside = float(paper_region.mean()) if paper_region.size else 0.0
            outside_mask = np.ones(gray.shape, dtype=np.uint8) * 255
            cv2.drawContours(outside_mask, [contour], -1, 0, thickness=cv2.FILLED)
            outside_pixels = gray[outside_mask > 0]
            mean_outside = float(outside_pixels.mean()) if outside_pixels.size else mean_inside
            brightness_contrast = max(0.0, min(0.28, (mean_inside - mean_outside) / 255.0))
            center_x = x + rect_width / 2
            center_offset = abs(center_x - width / 2) / max(width / 2, 1)
            center_bonus = max(0.0, 0.12 * (1.0 - center_offset))
            long_receipt_bonus = 0.18 if aspect >= 1.55 else 0.0
            score = (quad_area / image_area) + (rectangularity * 0.42) + long_receipt_bonus + brightness_contrast + center_bonus
            candidates.append({
                "quad": quad,
                "score": score,
                "diagnostic": {
                    "strategy": "bright_paper_region",
                    "areaRatio": round(quad_area / image_area, 4),
                    "contourAreaRatio": round(area / image_area, 4),
                    "rectangularity": round(rectangularity, 4),
                    "aspectRatio": round(aspect, 4),
                    "meanInside": round(mean_inside, 2),
                    "meanOutside": round(mean_outside, 2),
                    "score": round(score, 4),
                },
            })
        return candidates

    def _detect_edge_receipt_candidates(self, cv2: Any, np: Any, image: Any) -> list[dict[str, Any]]:
        height, width = image.shape[:2]
        gray = cv2.cvtColor(image, cv2.COLOR_BGR2GRAY)
        gray = cv2.bilateralFilter(gray, 7, 45, 45)
        background = cv2.medianBlur(gray, 31)
        shadow_suppressed = cv2.divide(gray, background, scale=255)
        adaptive = cv2.adaptiveThreshold(
            shadow_suppressed,
            255,
            cv2.ADAPTIVE_THRESH_GAUSSIAN_C,
            cv2.THRESH_BINARY,
            41,
            7,
        )
        edges = cv2.Canny(shadow_suppressed, 36, 120)
        mask = cv2.bitwise_or(edges, cv2.bitwise_not(adaptive))
        kernel = cv2.getStructuringElement(cv2.MORPH_RECT, (9, 9))
        mask = cv2.morphologyEx(mask, cv2.MORPH_CLOSE, kernel, iterations=2)
        mask = cv2.dilate(mask, kernel, iterations=1)
        contours, _ = cv2.findContours(mask, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
        image_area = float(width * height)
        candidates: list[dict[str, Any]] = []
        for contour in contours:
            area = float(cv2.contourArea(contour))
            if area < image_area * 0.04:
                continue
            perimeter = cv2.arcLength(contour, True)
            approx = cv2.approxPolyDP(contour, 0.025 * perimeter, True)
            if len(approx) >= 4:
                quad = self._quad_from_contour(cv2, np, approx if len(approx) == 4 else contour)
            else:
                quad = self._quad_from_contour(cv2, np, contour)
            quad_area = self._quad_area(quad)
            if quad_area < image_area * 0.05 or quad_area > image_area * 0.96:
                continue
            x, y, rect_width, rect_height = cv2.boundingRect(contour)
            aspect = max(rect_width, rect_height) / max(1, min(rect_width, rect_height))
            rectangularity = min(1.0, area / max(quad_area, 1.0))
            long_receipt_bonus = 0.18 if aspect >= 1.55 else 0.0
            score = (quad_area / image_area) + (rectangularity * 0.35) + long_receipt_bonus
            candidates.append({
                "quad": quad,
                "score": score,
                "diagnostic": {
                    "strategy": "edge_document_contour",
                    "areaRatio": round(quad_area / image_area, 4),
                    "contourAreaRatio": round(area / image_area, 4),
                    "rectangularity": round(rectangularity, 4),
                    "aspectRatio": round(aspect, 4),
                    "score": round(score, 4),
                },
            })
        return candidates

    def _dedupe_candidates(self, candidates: list[dict[str, Any]]) -> list[dict[str, Any]]:
        output: list[dict[str, Any]] = []
        seen: set[tuple[int, int, int, int]] = set()
        for candidate in candidates:
            quad = candidate.get("quad")
            if quad is None:
                continue
            xs = [float(point[0]) for point in quad]
            ys = [float(point[1]) for point in quad]
            key = (
                round(min(xs) / 20),
                round(min(ys) / 20),
                round(max(xs) / 20),
                round(max(ys) / 20),
            )
            if key in seen:
                continue
            seen.add(key)
            output.append(candidate)
        return output

    def _quad_from_contour(self, cv2: Any, np: Any, contour: Any) -> Any:
        rect = cv2.minAreaRect(contour)
        box = cv2.boxPoints(rect)
        return self._order_quad(np, box.astype("float32"))

    def _order_quad(self, np: Any, points: Any) -> Any:
        rect = np.zeros((4, 2), dtype="float32")
        sums = points.sum(axis=1)
        diffs = np.diff(points, axis=1)
        rect[0] = points[np.argmin(sums)]
        rect[2] = points[np.argmax(sums)]
        rect[1] = points[np.argmin(diffs)]
        rect[3] = points[np.argmax(diffs)]
        return rect

    def _quad_area(self, quad: Any) -> float:
        area = 0.0
        for index in range(4):
            current = quad[index]
            next_point = quad[(index + 1) % 4]
            area += float(current[0] * next_point[1] - next_point[0] * current[1])
        return abs(area) / 2.0

    def _warp_receipt(self, cv2: Any, np: Any, image: Any, quad: Any) -> Any:
        tl, tr, br, bl = quad
        width_a = math.dist(br, bl)
        width_b = math.dist(tr, tl)
        height_a = math.dist(tr, br)
        height_b = math.dist(tl, bl)
        target_width = int(max(width_a, width_b, 420))
        target_height = int(max(height_a, height_b, 620))
        if target_width > target_height * 1.08:
            target_width, target_height = target_height, target_width
        if target_height > 3600:
            ratio = 3600 / target_height
            target_height = 3600
            target_width = max(420, int(target_width * ratio))
        destination = np.array([
            [0, 0],
            [target_width - 1, 0],
            [target_width - 1, target_height - 1],
            [0, target_height - 1],
        ], dtype="float32")
        matrix = cv2.getPerspectiveTransform(quad, destination)
        return cv2.warpPerspective(image, matrix, (target_width, target_height), borderMode=cv2.BORDER_REPLICATE)

    def _clean_receipt_pixels(self, cv2: Any, image: Any) -> Any:
        enhanced = self._enhance_receipt(cv2, image)
        gray = cv2.cvtColor(enhanced, cv2.COLOR_BGR2GRAY)
        border = max(8, min(gray.shape[:2]) // 80)
        gray[:border, :] = 255
        gray[-border:, :] = 255
        gray[:, :border] = 255
        gray[:, -border:] = 255
        return cv2.cvtColor(gray, cv2.COLOR_GRAY2BGR)

    def _enhance_receipt(self, cv2: Any, image: Any) -> Any:
        gray = cv2.cvtColor(image, cv2.COLOR_BGR2GRAY)
        background = cv2.medianBlur(gray, 35)
        flattened = cv2.divide(gray, background, scale=255)
        clahe = cv2.createCLAHE(clipLimit=2.2, tileGridSize=(8, 8))
        contrasted = clahe.apply(flattened)
        denoised = cv2.fastNlMeansDenoising(contrasted, None, h=8, templateWindowSize=7, searchWindowSize=21)
        return cv2.cvtColor(denoised, cv2.COLOR_GRAY2BGR)

    def _mask_diagnostics(self, cv2: Any, np: Any, image: Any, quad: Any) -> dict[str, Any]:
        mask = np.zeros(image.shape[:2], dtype=np.uint8)
        cv2.fillConvexPoly(mask, quad.astype("int32"), 255)
        pixels = mask.size
        covered = int(cv2.countNonZero(mask))
        return {
            "width": int(mask.shape[1]),
            "height": int(mask.shape[0]),
            "coverageRatio": round(covered / max(pixels, 1), 4),
        }

    def _section_boundaries(self, cv2: Any, image: Any) -> list[dict[str, Any]]:
        gray = cv2.cvtColor(image, cv2.COLOR_BGR2GRAY)
        threshold = cv2.threshold(gray, 0, 255, cv2.THRESH_BINARY_INV + cv2.THRESH_OTSU)[1]
        row_density = (threshold > 0).mean(axis=1)
        boundaries = []
        in_band = False
        start = 0
        for index, density in enumerate(row_density):
            if density > 0.012 and not in_band:
                start = index
                in_band = True
            elif density <= 0.006 and in_band:
                if index - start > 8:
                    boundaries.append({"y1": start, "y2": index, "inkDensity": round(float(row_density[start:index].mean()), 4)})
                in_band = False
        return boundaries[:80]

    def _debug_previews(self, cv2: Any, source: Any, working: Any, quad: Any, cleaned: Any) -> dict[str, str]:
        overlay = working.copy()
        cv2.polylines(overlay, [quad.astype("int32")], True, (0, 255, 0), 4)
        return {
            "contourOverlayJpegBase64": self._preview_b64(cv2, overlay),
            "ocrInputJpegBase64": self._preview_b64(cv2, cleaned),
        }

    def _preview_b64(self, cv2: Any, image: Any) -> str:
        success, encoded = cv2.imencode(".jpg", image, [int(cv2.IMWRITE_JPEG_QUALITY), 70])
        return base64.b64encode(encoded.tobytes()).decode("ascii") if success else ""
