from .diagnostics import factor

class ShadowDetector:
    def evaluate(self, cv2, gray, policy):
        background = cv2.GaussianBlur(gray, (0, 0), sigmaX=max(1, min(gray.shape[:2]) / 20))
        variation = float(background.std())
        return factor("shadow", variation, policy, inverse=True, diagnostics={"metric": "background_luminance_variation"})

