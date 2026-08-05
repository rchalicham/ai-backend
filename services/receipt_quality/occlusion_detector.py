from .diagnostics import factor

class OcclusionDetector:
    def evaluate(self, cv2, gray, policy):
        dark_ratio = float((gray < float(policy.scoring_ranges["occlusion"]["darkPixelLevel"])).mean())
        return factor("occlusion", dark_ratio, policy, inverse=True, diagnostics={"metric": "dark_pixel_ratio"})

