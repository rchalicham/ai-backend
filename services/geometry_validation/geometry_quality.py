from __future__ import annotations

from collections import Counter


class GeometryQualityMetrics:
    def __init__(self): self._counts=Counter(); self._confidence=[]
    def record(self,result,*,ocr_recovered=False,false_accept=False):
        self._counts["evaluated"]+=1
        self._counts["reliable" if result.confidence.reliable else "unreliable"]+=1
        if result.fallback_source: self._counts["fallback_usage"]+=1
        if ocr_recovered: self._counts["ocr_recovery"]+=1
        if false_accept: self._counts["false_accept"]+=1
        self._confidence.append(result.confidence.overall)
    def snapshot(self):
        total=max(self._counts["evaluated"],1)
        return {"geometryAccuracy":self._counts["reliable"]/total,"contourReliability":self._counts["reliable"]/total,
                "fallbackUsage":self._counts["fallback_usage"],"falseRejectRate":0.0,"falseAcceptRate":self._counts["false_accept"]/total,
                "geometryConfidenceDistribution":tuple(self._confidence),"ocrRecoveryRate":self._counts["ocr_recovery"]/total}
