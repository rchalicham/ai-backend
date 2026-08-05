from .diagnostics import factor

class LightingDetector:
    def evaluate(self, cv2, gray, policy):
        return factor("brightness", float(gray.mean()), policy, diagnostics={"metric": "mean_luminance"})

