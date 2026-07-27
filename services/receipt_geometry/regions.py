from __future__ import annotations

from typing import Any

from .models import Region


class ReceiptRegionLocator:
    """Projection-based layout hints; it recognizes ink geometry, never text."""

    def locate(self, cv2: Any, np: Any, image: Any) -> tuple[list[Region], dict[str, Any], list[Region]]:
        gray = cv2.cvtColor(image, cv2.COLOR_BGR2GRAY)
        ink = cv2.threshold(gray, 0, 255, cv2.THRESH_BINARY_INV + cv2.THRESH_OTSU)[1] > 0
        height, width = gray.shape[:2]
        row_density = ink.mean(axis=1)
        column_density = ink.mean(axis=0)
        zones = self._bands(row_density, width, "reading_zone", 0.012, 0.006, 8)
        columns = self._bands(column_density, height, "column", 0.018, 0.009, 6, horizontal=False)
        whitespace_rows = self._runs(row_density <= 0.006)
        whitespace_columns = self._runs(column_density <= 0.009)
        whitespace = {
            "rowRuns": [{"start": start, "end": end} for start, end in whitespace_rows if end - start >= 3],
            "columnRuns": [{"start": start, "end": end} for start, end in whitespace_columns if end - start >= 3],
            "rowDensity": [round(float(value), 4) for value in row_density],
            "columnDensity": [round(float(value), 4) for value in column_density],
        }
        return columns[:20], whitespace, zones[:80]

    def section_boundaries(self, cv2: Any, image: Any) -> list[dict[str, Any]]:
        import numpy as np

        _, _, zones = self.locate(cv2, np, image)
        gray = cv2.cvtColor(image, cv2.COLOR_BGR2GRAY)
        ink = cv2.threshold(gray, 0, 255, cv2.THRESH_BINARY_INV + cv2.THRESH_OTSU)[1] > 0
        return [
            {
                "y1": zone.y,
                "y2": zone.y + zone.height,
                "inkDensity": round(float(ink[zone.y:zone.y + zone.height].mean()), 4),
            }
            for zone in zones
        ]

    def _bands(
        self, density: Any, cross_size: int, kind: str, enter: float, leave: float,
        minimum: int, horizontal: bool = True,
    ) -> list[Region]:
        regions, active, start = [], False, 0
        for index, value in enumerate(density):
            if value > enter and not active:
                start, active = index, True
            elif value <= leave and active:
                if index - start > minimum:
                    confidence = min(1.0, float(density[start:index].mean()) * 4.0)
                    regions.append(
                        Region(0, start, cross_size, index - start, kind, round(confidence, 4))
                        if horizontal else
                        Region(start, 0, index - start, cross_size, kind, round(confidence, 4))
                    )
                active = False
        if active and len(density) - start > minimum:
            regions.append(
                Region(0, start, cross_size, len(density) - start, kind, 0.5)
                if horizontal else Region(start, 0, len(density) - start, cross_size, kind, 0.5)
            )
        return regions

    @staticmethod
    def _runs(mask: Any) -> list[tuple[int, int]]:
        runs, start = [], None
        for index, value in enumerate(mask):
            if bool(value) and start is None:
                start = index
            elif not bool(value) and start is not None:
                runs.append((start, index))
                start = None
        if start is not None:
            runs.append((start, len(mask)))
        return runs
