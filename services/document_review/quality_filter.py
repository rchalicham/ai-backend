from .models import ResolvedQuality, frozen_map


class ResolvedQualityFilter:
    def resolve(self, context, configuration):
        quality = context.get("receiptQuality") or {}
        geometry = quality.get("geometryValidation") or quality.get("geometry_validation") or {}
        reliability = str(geometry.get("reliability") or "").lower()
        fallback = geometry.get("selectedSource") or geometry.get("selected_source") or ""
        reliable = reliability in set(configuration["qualityResolution"]["reliableStates"])
        advisory = set(configuration["qualityResolution"]["advisoryFactors"])
        unresolved, resolved = [], []
        for factor in quality.get("factors") or ():
            if factor.get("passed", True):
                continue
            warning = frozen_map({"code": factor.get("name"), "score": factor.get("score"), "reason": factor.get("reason", "")})
            if factor.get("name") in advisory and (quality.get("passed") is True or reliable):
                resolved.append(warning)
            else:
                unresolved.append(warning)
        factor_observations = quality.get("factors") or ()
        # A raw gate failure can be resolved when every failed observation was
        # advisory and trusted validation/fallback supplied the final geometry.
        passed = not unresolved and (quality.get("passed") is not False or bool(factor_observations))
        return ResolvedQuality(passed, quality.get("overallScore"), tuple(unresolved), tuple(resolved), str(fallback), float(geometry.get("overallConfidence") or geometry.get("overall_confidence") or 0.0))
