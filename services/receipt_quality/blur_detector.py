from .diagnostics import factor

class BlurDetector:
    def evaluate(self, cv2, gray, policy):
        value = float(cv2.Laplacian(gray, cv2.CV_64F).var())
        return factor("blur", value, policy, diagnostics={"metric": "laplacian_variance"})

