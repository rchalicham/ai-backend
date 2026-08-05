from .diagnostics import factor

class TextResolutionDetector:
    def evaluate(self, cv2, np, gray, policy):
        binary = cv2.adaptiveThreshold(gray, 255, cv2.ADAPTIVE_THRESH_GAUSSIAN_C, cv2.THRESH_BINARY_INV, 31, 11)
        count, _, stats, _ = cv2.connectedComponentsWithStats(binary, 8)
        heights = [int(stats[i, cv2.CC_STAT_HEIGHT]) for i in range(1, count) if stats[i, cv2.CC_STAT_AREA] > 1]
        value = float(np.median(heights)) if heights else 0.0
        return factor("text_resolution", value, policy, diagnostics={"estimatedCharacterHeight": value, "componentCount": len(heights)})

