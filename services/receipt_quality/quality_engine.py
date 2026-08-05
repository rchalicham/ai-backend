from __future__ import annotations

from .blur_detector import BlurDetector
from .contrast_detector import ContrastDetector
from .diagnostics import factor
from .lighting_detector import LightingDetector
from .models import ReceiptQualityResult, immutable_mapping
from .occlusion_detector import OcclusionDetector
from .orientation_engine import OrientationEngine
from .perspective_detector import PerspectiveDetector
from .receipt_coverage import ReceiptCoverageDetector
from .recommendation_engine import RecommendationEngine
from .resolution_detector import ResolutionDetector
from .shadow_detector import ShadowDetector
from .text_resolution import TextResolutionDetector
from .quality_score import QualityScoreEngine
from services.geometry_validation import (
    GeometryValidationEngine, GeometryValidationPolicyLoader, GeometryValidationSerializer,
)


class ReceiptCaptureQualityEngine:
    """OCR-free capture gate. All policy values are externally configured."""
    def __init__(self, policy_loader, geometry_engine, geometry_validation_engine=None) -> None:
        self.policy_loader = policy_loader
        self.geometry_engine = geometry_engine
        self.orientation = OrientationEngine()
        self.scorer = QualityScoreEngine()
        self.recommendations = RecommendationEngine()
        self.geometry_validation = geometry_validation_engine or GeometryValidationEngine(
            GeometryValidationPolicyLoader(policy_loader.configuration)
        )
        self.geometry_validation_serializer = GeometryValidationSerializer()

    def evaluate(self, image_bytes: bytes) -> ReceiptQualityResult:
        policy = self.policy_loader.load()
        try:
            import cv2
            import numpy as np
            image = cv2.imdecode(np.frombuffer(image_bytes, dtype=np.uint8), cv2.IMREAD_COLOR)
            if image is None:
                raise ValueError("capture_image_decode_failed")
            geometry = self.geometry_engine.analyze_image(cv2, np, image)
            initial_validation = self.geometry_validation.validate(cv2, np, image, geometry)
            normalized, orientation = self.orientation.normalize(cv2, np, image, initial_validation.effective_geometry)
            normalized_geometry = self.geometry_engine.analyze_image(cv2, np, normalized)
            geometry_validation = self.geometry_validation.validate(cv2, np, normalized, normalized_geometry)
            trusted_geometry = geometry_validation.effective_geometry
            gray = cv2.cvtColor(normalized, cv2.COLOR_BGR2GRAY)
            rotation_score = 1.0 if orientation.degrees in {0, 90, 180, 270} else 0.0
            factors = (
                factor("rotation", rotation_score, policy),
                PerspectiveDetector().evaluate(cv2, trusted_geometry, policy),
                BlurDetector().evaluate(cv2, gray, policy),
                ContrastDetector().evaluate(cv2, gray, policy),
                LightingDetector().evaluate(cv2, gray, policy),
                ShadowDetector().evaluate(cv2, gray, policy),
                ReceiptCoverageDetector().evaluate(cv2, trusted_geometry, policy),
                TextResolutionDetector().evaluate(cv2, np, gray, policy),
                ResolutionDetector().evaluate(cv2, normalized, policy),
                OcclusionDetector().evaluate(cv2, gray, policy),
                self._edge_clipping(trusted_geometry, policy),
                self._completeness(trusted_geometry, policy),
                self._noise(cv2, gray, policy),
                factor("skew", abs(float(trusted_geometry.skew)), policy, inverse=True),
            )
            overall, confidence = self.scorer.aggregate(factors, policy)
            geometry_policy = self.geometry_validation.policy_loader.load()
            critical = set(geometry_policy.critical_factors)
            passed = overall >= policy.minimum_overall_score and all(item.passed for item in factors if item.name in critical)
            success, encoded = cv2.imencode(".png", normalized)
            if not success:
                raise ValueError("capture_orientation_encode_failed")
            return ReceiptQualityResult(
                "pass" if passed else "quality_failure", passed, overall, confidence, factors,
                self.recommendations.build(factors, policy), orientation, policy.policy_id, policy.version,
                encoded.tobytes(), immutable_mapping({"ocrInvoked": False, "geometryOnly": True,
                    "criticalFactors": geometry_policy.critical_factors,
                    "advisoryFactors": geometry_policy.advisory_factors,
                    "advisoryFailures": tuple(item.name for item in factors if item.name in geometry_policy.advisory_factors and not item.passed)}),
                immutable_mapping(self.geometry_validation_serializer.to_dict(geometry_validation)),
            )
        except ValueError:
            raise
        except Exception as exc:
            raise ValueError(f"capture_quality_evaluation_failed:{type(exc).__name__}") from exc

    @staticmethod
    def _edge_clipping(geometry, policy):
        width, height = geometry.source_dimensions.width, geometry.source_dimensions.height
        margin = min(min(point.x, width-point.x, point.y, height-point.y) for point in geometry.receipt_boundary)
        return factor("edge_clipping", margin / max(min(width, height), 1), policy)

    @staticmethod
    def _completeness(geometry, policy):
        value = float(geometry.geometric_confidence)
        return factor("completeness", value, policy)

    @staticmethod
    def _noise(cv2, gray, policy):
        smooth = cv2.GaussianBlur(gray, (3, 3), 0)
        value = float(cv2.absdiff(gray, smooth).mean())
        return factor("noise", value, policy, inverse=True)
