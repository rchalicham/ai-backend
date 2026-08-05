from .diagnostics import factor

class ResolutionDetector:
    def evaluate(self, cv2, image, policy):
        height, width = image.shape[:2]
        return factor("resolution", float(min(width, height)), policy, diagnostics={"width": width, "height": height})

