from __future__ import annotations

import math
from typing import Any


class GeometryUtilities:
    @staticmethod
    def decode_image(cv2: Any, np: Any, image_bytes: bytes) -> Any:
        image = cv2.imdecode(np.frombuffer(image_bytes, dtype=np.uint8), cv2.IMREAD_COLOR)
        if image is None:
            raise ValueError("unable_to_decode_image")
        return image

    @staticmethod
    def encode_image(cv2: Any, image: Any, extension: str = ".jpg", quality: int = 94) -> bytes:
        options = [int(cv2.IMWRITE_JPEG_QUALITY), quality] if extension.lower() in {".jpg", ".jpeg"} else []
        success, encoded = cv2.imencode(extension, image, options)
        if not success:
            raise ValueError("unable_to_encode_image")
        return encoded.tobytes()

    @staticmethod
    def scale_for_detection(cv2: Any, image: Any, max_side: int = 1600) -> tuple[Any, float]:
        height, width = image.shape[:2]
        if max(width, height) <= max_side:
            return image.copy(), 1.0
        scale = max_side / float(max(width, height))
        resized = cv2.resize(
            image,
            (max(1, round(width * scale)), max(1, round(height * scale))),
            interpolation=cv2.INTER_AREA,
        )
        return resized, scale

    @staticmethod
    def order_quad(np: Any, points: Any) -> Any:
        ordered = np.zeros((4, 2), dtype="float32")
        sums = points.sum(axis=1)
        diffs = np.diff(points, axis=1)
        ordered[0] = points[np.argmin(sums)]
        ordered[2] = points[np.argmax(sums)]
        ordered[1] = points[np.argmin(diffs)]
        ordered[3] = points[np.argmax(diffs)]
        return ordered

    @staticmethod
    def quad_from_contour(cv2: Any, np: Any, contour: Any) -> Any:
        return GeometryUtilities.order_quad(np, cv2.boxPoints(cv2.minAreaRect(contour)).astype("float32"))

    @staticmethod
    def quad_area(quad: Any) -> float:
        area = 0.0
        for index in range(4):
            current, following = quad[index], quad[(index + 1) % 4]
            area += float(current[0] * following[1] - following[0] * current[1])
        return abs(area) / 2.0

    @staticmethod
    def target_dimensions(quad: Any) -> tuple[int, int]:
        tl, tr, br, bl = quad
        target_width = int(max(math.dist(br, bl), math.dist(tr, tl), 420))
        target_height = int(max(math.dist(tr, br), math.dist(tl, bl), 620))
        if target_width > target_height * 1.08:
            target_width, target_height = target_height, target_width
        if target_height > 3600:
            ratio = 3600 / target_height
            target_height = 3600
            target_width = max(420, int(target_width * ratio))
        return target_width, target_height

    @staticmethod
    def enhance_receipt(cv2: Any, image: Any) -> Any:
        gray = cv2.cvtColor(image, cv2.COLOR_BGR2GRAY)
        background = cv2.medianBlur(gray, 35)
        flattened = cv2.divide(gray, background, scale=255)
        contrasted = cv2.createCLAHE(clipLimit=2.2, tileGridSize=(8, 8)).apply(flattened)
        denoised = cv2.fastNlMeansDenoising(contrasted, None, h=8, templateWindowSize=7, searchWindowSize=21)
        return cv2.cvtColor(denoised, cv2.COLOR_GRAY2BGR)
