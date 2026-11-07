"""Risk indicators and warnings.

Brief, Section 9: a transparent weighted score built from lake area growth
rate, volume (when available), new landslide activity near the blockage,
blockage confidence and slope, with rainfall optional. All weights and
thresholds live in config, and **every warning lists the factors behind it**.

What this is not
----------------
These are **indicator levels, not predictions**. The system never states that
a dam will fail, or when, and the level wording is the brief's own and
deliberately hedged. Every assessment carries the mandatory disclaimer, which
``config/schema.py`` refuses to load without.

The rule that shapes the design: unavailable is not reassurance
---------------------------------------------------------------
Most factors here will be missing much of the time. Depth and volume are
``unavailable`` for every Branch B lake (Section 8), blockage confidence does
not exist until a blockage is detected, and rainfall is not wired in at all.

Scoring a missing factor as zero would make an unmeasured site look safe, and
a quiet NORMAL assembled from a fifth of the evidence would be the most
dangerous output this system could produce. So an unavailable factor is
excluded from **both** the numerator and the denominator -- it neither raises
nor lowers the score -- and the share of total weight that was actually
measurable is reported as ``data_coverage``, with ``insufficient_data`` set
below the configured floor.

The published alternative, and why it is not used
-------------------------------------------------
Ermini & Casagli (2003) define a Dimensionless Blockage Index for landslide
dam stability, with dams generally stable below 2.75 and unstable above 3.08.
It is not used here for two reasons: it needs dam height and volume, which
Branch B frequently makes unmeasurable, and it rates *dam stability* rather
than the broader indicator set the brief specifies. Noted in
docs/methods.md 11.5 rather than silently ignored.

References
----------
Ermini, L. & Casagli, N. (2003). Prediction of the behaviour of landslide
    dams using a geomorphological dimensionless index. *Earth Surface
    Processes and Landforms*, 28(1), 31-47. -- thresholds 2.75 / 3.08 are
    confirmed from secondary sources; the exact expression was not verified
    against the original paper, so it is not reproduced here.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import TYPE_CHECKING, Any

from utils.logging import get_logger

if TYPE_CHECKING:  # pragma: no cover
    from config.schema import Config

log = get_logger(__name__)

LEVEL_NORMAL = "NORMAL"
LEVEL_MONITOR = "MONITOR"
LEVEL_HIGH = "HIGH RISK INDICATORS"
LEVEL_CRITICAL = "CRITICAL INDICATORS - verification recommended"

#: Ordered from least to most concerning. The wording is the brief's own
#: (Section 9) and must not be softened or sharpened.
LEVELS = (LEVEL_NORMAL, LEVEL_MONITOR, LEVEL_HIGH, LEVEL_CRITICAL)

LEVEL_SYMBOLS = {
    LEVEL_NORMAL: "\N{LARGE GREEN CIRCLE}",
    LEVEL_MONITOR: "\N{LARGE YELLOW CIRCLE}",
    LEVEL_HIGH: "\N{LARGE ORANGE CIRCLE}",
    LEVEL_CRITICAL: "\N{LARGE RED CIRCLE}",
}

#: Shown instead of the green circle when a NORMAL level rests on too little
#: evidence. A dashboard may render only the symbol, and a green dot derived
#: from a tenth of the data is false reassurance -- the one failure this
#: module is most concerned to avoid. The level *text* is unchanged, because
#: the brief fixes the four levels; only the visual cue is withheld.
#:
#: It is applied only to NORMAL. Substituting it on a HIGH or CRITICAL level
#: would mute a real alarm, which is the opposite mistake.
INSUFFICIENT_DATA_SYMBOL = "\N{MEDIUM WHITE CIRCLE}"

#: Factor name -> (weight attribute, scale attribute, unit).
FACTOR_DEFINITIONS = {
    "lake_growth_rate": ("lake_growth_rate", "lake_growth_rate_m2_per_day", "m2/day"),
    "lake_volume": ("lake_volume", "lake_volume_m3", "m3"),
    "new_landslide_activity": (
        "new_landslide_activity",
        "new_landslide_area_m2",
        "m2",
    ),
    "blockage_confidence": ("blockage_confidence", "blockage_confidence", ""),
    "slope": ("slope", "slope_deg", "degrees"),
    "rainfall": ("rainfall", "rainfall_mm_24h", "mm/24h"),
}


def scale_score(value: float, low: float, high: float) -> float:
    """Map ``value`` onto 0-1 by linear interpolation, clamped at both ends.

    ``low`` may exceed ``high`` to express a factor where smaller is worse.
    """
    if low == high:
        raise ValueError(f"a scale needs two distinct ends, got low == high == {low}")
    fraction = (float(value) - low) / (high - low)
    return float(min(1.0, max(0.0, fraction)))


@dataclass(frozen=True)
class RiskFactor:
    """One contributing factor, and whether it could be measured at all."""

    name: str
    weight: float
    unit: str
    value: float | None = None
    score: float | None = None
    available: bool = False
    value_type: str = "unavailable"
    reason: str | None = None
    #: The value reached or passed the worse end of its scale, so the score can
    #: no longer distinguish it from a much larger one. Reported rather than
    #: hidden: a clamped factor looks identical to one that merely scored 1.0,
    #: and the difference matters when the scale is a convention. Measured on
    #: Baige 2018, where a 90,300 m2 deposit pinned a [0, 50000] m2 scale, so
    #: any larger dam would have scored the same.
    saturated: bool = False

    @property
    def contribution(self) -> float:
        """Weighted contribution to the score; zero when unavailable."""
        return self.weight * self.score if (self.available and self.score is not None) else 0.0

    def describe(self) -> str:
        if not self.available:
            return f"{self.name}: unavailable ({self.reason or 'not supplied'})"
        unit = f" {self.unit}" if self.unit else ""
        # "SATURATED" is appended rather than left to the score, because a
        # clamped factor is indistinguishable from one that merely scored 1.00
        # and the scales here are conventions, not calibrated measurements.
        pinned = " SATURATED (scale ceiling reached)" if self.saturated else ""
        return (
            f"{self.name}: {self.value:g}{unit} -> score {self.score:.2f} "
            f"x weight {self.weight:g} = {self.contribution:.2f} "
            f"[{self.value_type}]{pinned}"
        )

    def as_dict(self) -> dict[str, Any]:
        return {
            "name": self.name,
            "value": self.value,
            "unit": self.unit,
            "score": self.score,
            "saturated": self.saturated,
            "weight": self.weight,
            "contribution": self.contribution if self.available else None,
            "available": self.available,
            "value_type": self.value_type,
            "reason": self.reason,
        }


@dataclass(frozen=True)
class RiskAssessment:
    """A levelled indicator with the factors that produced it."""

    score: float
    level: str
    factors: list[RiskFactor]
    data_coverage: float
    insufficient_data: bool
    disclaimer: str
    assessed_at: str
    config_version: str
    config_hash: str | None = None
    notes: list[str] = field(default_factory=list)

    @property
    def symbol(self) -> str:
        """The indicator symbol, withholding green where evidence is thin.

        See :data:`INSUFFICIENT_DATA_SYMBOL`.
        """
        if self.insufficient_data and self.level == LEVEL_NORMAL:
            return INSUFFICIENT_DATA_SYMBOL
        return LEVEL_SYMBOLS[self.level]

    @property
    def available_factors(self) -> list[RiskFactor]:
        return [f for f in self.factors if f.available]

    @property
    def missing_factors(self) -> list[RiskFactor]:
        return [f for f in self.factors if not f.available]

    def contributing_factors(self) -> list[RiskFactor]:
        """Available factors, most influential first.

        This is what Section 9's "each warning must list the factors behind
        it" asks for.
        """
        return sorted(
            self.available_factors, key=lambda f: f.contribution, reverse=True
        )

    def warning_text(self) -> str:
        """A complete, self-contained warning, disclaimer included."""
        lines = [
            f"{self.symbol} {self.level}",
            f"Indicator score: {self.score:.2f} of 1.00 "
            f"(data coverage {self.data_coverage:.0%})",
        ]
        if self.insufficient_data:
            lines.append(
                "INSUFFICIENT DATA: this level rests on less than the configured "
                "minimum share of the evidence. Absence of a measurement is not "
                "evidence of safety."
            )
        pinned = [f for f in self.factors if f.saturated]
        if pinned:
            lines.append(
                "SCALE CEILING REACHED by "
                + ", ".join(f.name for f in pinned)
                + ": the score cannot distinguish these from larger values, "
                "and their scales are conventions rather than calibrated "
                "measurements."
            )
        lines.append("Contributing factors:")
        contributing = self.contributing_factors()
        if contributing:
            lines.extend(f"  - {f.describe()}" for f in contributing)
        else:
            lines.append("  - none could be measured")
        if self.missing_factors:
            lines.append("Not measured:")
            lines.extend(f"  - {f.describe()}" for f in self.missing_factors)
        lines.extend(self.notes)
        lines.append("")
        lines.append(self.disclaimer)
        return "\n".join(lines)

    def as_record(self, site_id: Any) -> dict[str, Any]:
        """A row for the ``risk_assessments`` table (brief, Section 10)."""
        return {
            "site_id": site_id,
            "assessed_at": self.assessed_at,
            "factors_json": json.dumps([f.as_dict() for f in self.factors]),
            "score": self.score,
            "level": self.level,
            "config_version": self.config_version,
            # Beyond the brief's minimum columns. A level stored without its
            # coverage reads as a verdict rather than as what it is; see
            # docs/methods.md 11.3.
            "data_coverage": self.data_coverage,
            "insufficient_data": int(self.insufficient_data),
        }


def _factor(
    name: str,
    cfg: "Config",
    value: float | None,
    *,
    value_type: str = "derived",
    reason: str | None = None,
) -> RiskFactor:
    weight_attr, scale_attr, unit = FACTOR_DEFINITIONS[name]
    settings = cfg.analysis.risk
    weight = float(getattr(settings.weights, weight_attr))
    low, high = getattr(settings.scales, scale_attr)

    if value is None:
        return RiskFactor(
            name=name,
            weight=weight,
            unit=unit,
            available=False,
            value_type="unavailable",
            reason=reason or "not supplied",
        )
    low_f, high_f = float(low), float(high)
    # The scale may run either way: ``low`` above ``high`` expresses a factor
    # where smaller is worse. Saturation is reaching the WORSE end, whichever
    # that is, because that is the end where information is lost.
    worse = max(low_f, high_f) if high_f > low_f else min(low_f, high_f)
    saturated = (
        float(value) >= worse if high_f > low_f else float(value) <= worse
    )
    return RiskFactor(
        name=name,
        weight=weight,
        unit=unit,
        value=float(value),
        score=scale_score(value, low_f, high_f),
        available=True,
        value_type=value_type,
        saturated=saturated,
        reason=(
            f"at or beyond the {worse:,.0f} {unit} end of its scale: the score "
            f"cannot distinguish this from a larger value"
            if saturated else None
        ),
    )


def level_for_score(score: float, cfg: "Config") -> str:
    """The indicator level for a score, by the configured thresholds."""
    levels = cfg.analysis.risk.levels
    if score >= levels.critical:
        return LEVEL_CRITICAL
    if score >= levels.high_risk:
        return LEVEL_HIGH
    if score >= levels.monitor:
        return LEVEL_MONITOR
    return LEVEL_NORMAL


def assess_risk(
    cfg: "Config",
    *,
    lake_growth_rate_m2_per_day: float | None = None,
    lake_volume_m3: float | None = None,
    volume_unavailable_reason: str | None = None,
    new_landslide_area_m2: float | None = None,
    blockage_confidence: float | None = None,
    slope_deg: float | None = None,
    rainfall_mm_24h: float | None = None,
    config_hash: str | None = None,
    notes: list[str] | None = None,
) -> RiskAssessment:
    """Assess indicator level for one site from whatever could be measured.

    Every argument is optional. A factor that is ``None`` is **excluded** from
    the score rather than scored as zero, because a missing measurement is not
    evidence of safety. The share of total weight that was measurable is
    reported as ``data_coverage``.

    Args:
        lake_volume_m3: pass ``None`` for a Branch B or C lake, with
            ``volume_unavailable_reason`` carrying the branch's reason so the
            warning can say *why* the volume is missing rather than just that
            it is.
        config_hash: recorded with the assessment for reproducibility.

    Returns:
        A :class:`RiskAssessment` whose ``warning_text`` is self-contained and
        carries the mandatory disclaimer.
    """
    settings = cfg.analysis.risk

    factors = [
        _factor("lake_growth_rate", cfg, lake_growth_rate_m2_per_day),
        _factor(
            "lake_volume",
            cfg,
            lake_volume_m3,
            value_type="estimated",
            reason=volume_unavailable_reason,
        ),
        _factor("new_landslide_activity", cfg, new_landslide_area_m2),
        _factor(
            "blockage_confidence", cfg, blockage_confidence, value_type="classified"
        ),
        _factor("slope", cfg, slope_deg, value_type="observed"),
        _factor("rainfall", cfg, rainfall_mm_24h, value_type="observed"),
    ]

    total_weight = settings.weights.total()
    available_weight = sum(f.weight for f in factors if f.available)
    contribution = sum(f.contribution for f in factors)

    # Renormalise over the weight that was actually measurable, so an absent
    # factor neither raises nor lowers the score.
    score = float(contribution / available_weight) if available_weight > 0 else 0.0
    coverage = float(available_weight / total_weight) if total_weight > 0 else 0.0
    insufficient = coverage < settings.min_data_coverage

    assessment = RiskAssessment(
        score=score,
        level=level_for_score(score, cfg),
        factors=factors,
        data_coverage=coverage,
        insufficient_data=insufficient,
        disclaimer=cfg.project.disclaimer,
        assessed_at=datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        config_version=cfg.project.version,
        config_hash=config_hash,
        notes=list(notes or []),
    )

    log.info(
        "risk assessment: %s (score %.2f, coverage %.0f%%%s)",
        assessment.level,
        assessment.score,
        assessment.data_coverage * 100,
        ", INSUFFICIENT DATA" if insufficient else "",
    )
    for factor in assessment.factors:
        log.info("  %s", factor.describe())
    return assessment
