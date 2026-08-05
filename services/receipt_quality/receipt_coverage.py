from .diagnostics import factor

class ReceiptCoverageDetector:
    def evaluate(self, cv2, geometry, policy):
        points = geometry.receipt_boundary
        area = 0.0
        for index, point in enumerate(points):
            nxt = points[(index + 1) % len(points)]
            area += point.x * nxt.y - nxt.x * point.y
        image_area = geometry.source_dimensions.width * geometry.source_dimensions.height
        coverage = abs(area) / 2 / max(image_area, 1)
        return factor("coverage", coverage, policy, diagnostics={"receiptArea": abs(area)/2, "imageArea": image_area})

