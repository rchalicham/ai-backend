from .diagnostics import factor

class PerspectiveDetector:
    def evaluate(self, cv2, geometry, policy):
        points = geometry.receipt_boundary
        if len(points) < 4:
            distortion = 1.0
        else:
            top = ((points[1].x-points[0].x)**2 + (points[1].y-points[0].y)**2) ** .5
            bottom = ((points[2].x-points[3].x)**2 + (points[2].y-points[3].y)**2) ** .5
            left = ((points[3].x-points[0].x)**2 + (points[3].y-points[0].y)**2) ** .5
            right = ((points[2].x-points[1].x)**2 + (points[2].y-points[1].y)**2) ** .5
            distortion = max(abs(top-bottom)/max(top,bottom,1), abs(left-right)/max(left,right,1))
        return factor("perspective", distortion, policy, inverse=True, diagnostics={"metric": "opposing_edge_distortion"})

