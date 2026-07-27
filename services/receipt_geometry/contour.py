from __future__ import annotations

from typing import Any

from .utilities import GeometryUtilities


class ReceiptContourDetector:
    """The existing isolation contour algorithms exposed as a reusable detector."""

    def detect(self, cv2: Any, np: Any, image: Any) -> list[dict[str, Any]]:
        candidates = self._bright_paper_candidates(cv2, np, image)
        candidates.extend(self._edge_candidates(cv2, np, image))
        candidates.sort(key=lambda item: item["score"], reverse=True)
        return self._dedupe(candidates)

    def _bright_paper_candidates(self, cv2: Any, np: Any, image: Any) -> list[dict[str, Any]]:
        height, width = image.shape[:2]
        gray = cv2.cvtColor(image, cv2.COLOR_BGR2GRAY)
        blurred = cv2.GaussianBlur(gray, (7, 7), 0)
        _, threshold = cv2.threshold(blurred, 0, 255, cv2.THRESH_BINARY + cv2.THRESH_OTSU)
        if cv2.countNonZero(threshold) > threshold.size * 0.82:
            threshold = cv2.adaptiveThreshold(
                blurred, 255, cv2.ADAPTIVE_THRESH_GAUSSIAN_C, cv2.THRESH_BINARY, 61, -5
            )
        kernel = cv2.getStructuringElement(cv2.MORPH_RECT, (17, 17))
        mask = cv2.morphologyEx(threshold, cv2.MORPH_CLOSE, kernel, iterations=2)
        mask = cv2.morphologyEx(
            mask, cv2.MORPH_OPEN, cv2.getStructuringElement(cv2.MORPH_RECT, (5, 5)), iterations=1
        )
        contours, _ = cv2.findContours(mask, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
        image_area = float(width * height)
        candidates = []
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
            quad = GeometryUtilities.quad_from_contour(cv2, np, contour)
            quad_area = GeometryUtilities.quad_area(quad)
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
            center_offset = abs((x + rect_width / 2) - width / 2) / max(width / 2, 1)
            center_bonus = max(0.0, 0.12 * (1.0 - center_offset))
            score = (
                (quad_area / image_area)
                + (rectangularity * 0.42)
                + (0.18 if aspect >= 1.55 else 0.0)
                + brightness_contrast
                + center_bonus
            )
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

    def _edge_candidates(self, cv2: Any, np: Any, image: Any) -> list[dict[str, Any]]:
        height, width = image.shape[:2]
        gray = cv2.bilateralFilter(cv2.cvtColor(image, cv2.COLOR_BGR2GRAY), 7, 45, 45)
        background = cv2.medianBlur(gray, 31)
        shadow_suppressed = cv2.divide(gray, background, scale=255)
        adaptive = cv2.adaptiveThreshold(
            shadow_suppressed, 255, cv2.ADAPTIVE_THRESH_GAUSSIAN_C, cv2.THRESH_BINARY, 41, 7
        )
        edges = cv2.Canny(shadow_suppressed, 36, 120)
        mask = cv2.bitwise_or(edges, cv2.bitwise_not(adaptive))
        kernel = cv2.getStructuringElement(cv2.MORPH_RECT, (9, 9))
        mask = cv2.morphologyEx(mask, cv2.MORPH_CLOSE, kernel, iterations=2)
        mask = cv2.dilate(mask, kernel, iterations=1)
        contours, _ = cv2.findContours(mask, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
        image_area = float(width * height)
        candidates = []
        for contour in contours:
            area = float(cv2.contourArea(contour))
            if area < image_area * 0.04:
                continue
            perimeter = cv2.arcLength(contour, True)
            approx = cv2.approxPolyDP(contour, 0.025 * perimeter, True)
            quad = GeometryUtilities.quad_from_contour(
                cv2, np, approx if len(approx) == 4 else contour
            )
            quad_area = GeometryUtilities.quad_area(quad)
            if quad_area < image_area * 0.05 or quad_area > image_area * 0.96:
                continue
            _, _, rect_width, rect_height = cv2.boundingRect(contour)
            aspect = max(rect_width, rect_height) / max(1, min(rect_width, rect_height))
            rectangularity = min(1.0, area / max(quad_area, 1.0))
            score = (quad_area / image_area) + (rectangularity * 0.35) + (0.18 if aspect >= 1.55 else 0.0)
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

    @staticmethod
    def _dedupe(candidates: list[dict[str, Any]]) -> list[dict[str, Any]]:
        output, seen = [], set()
        for candidate in candidates:
            quad = candidate.get("quad")
            if quad is None:
                continue
            xs, ys = [float(p[0]) for p in quad], [float(p[1]) for p in quad]
            key = (round(min(xs) / 20), round(min(ys) / 20), round(max(xs) / 20), round(max(ys) / 20))
            if key not in seen:
                seen.add(key)
                output.append(candidate)
        return output
