from .diagnostics import factor

class ContrastDetector:
    def evaluate(self, cv2, gray, policy):
        return factor("contrast", float(gray.std()), policy, diagnostics={"metric": "luminance_standard_deviation"})

