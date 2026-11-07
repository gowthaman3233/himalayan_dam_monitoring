"""Lake-area time series and trend classification.

Brief, Section 7.8: a time series of lake area with absolute change, percent
change and rate of change; a trend of Increasing / Decreasing / Stable /
Unknown with configurable thresholds and a minimum number of valid
observations; and **cloudy or missing dates recorded as gaps, never
interpolated**.

Three rules shape this module
-----------------------------
1. **A gap is recorded, never filled.** An observation that could not be made
   is carried through the series as a gap with its reason, counted, and
   reported -- but it never contributes a value to the trend fit. Interpolating
   across it would manufacture a measurement on a date nobody looked at, and
   the fabricated point would sit exactly where a reader most wants evidence.

2. **Too little data is Unknown, not Stable.** A series below
   ``min_valid_observations``, with no time span, or whose latest valid
   observation is stale, is ``Unknown`` with a reason. Reporting "Stable"
   because nothing was measured would be the temporal twin of the
   false-reassurance problem that shaped Phase 11.

3. **The rate is estimated robustly.** The default slope is Theil-Sen (Sen
   1968): the median of the slopes between every pair of valid observations.
   A single mis-segmented date -- a cloud edge counted as water, a shadowed
   shore lost -- moves a median far less than it moves a least-squares fit or
   an endpoint difference. This is the same reasoning as the MAD-based
   thresholds in Phase 5.

References
----------
Sen, P. K. (1968). Estimates of the regression coefficient based on Kendall's
    tau. *Journal of the American Statistical Association*, 63(324),
    1379-1389. -- "a simple and robust (point as well as interval) estimator
    of beta based on Kendall's rank correlation tau"; the point estimate is
    the median of the pairwise slopes. The estimator is usually called
    Theil-Sen, after Theil (1950) and Sen (1968).
"""

from __future__ import annotations

import statistics
from dataclasses import dataclass, field
from datetime import date
from typing import TYPE_CHECKING, Any, Sequence

from utils.logging import get_logger

if TYPE_CHECKING:  # pragma: no cover
    from config.schema import Config

log = get_logger(__name__)

TREND_INCREASING = "Increasing"
TREND_DECREASING = "Decreasing"
TREND_STABLE = "Stable"
TREND_UNKNOWN = "Unknown"

#: The four trends the brief enumerates (Section 7.8).
TRENDS = (TREND_INCREASING, TREND_DECREASING, TREND_STABLE, TREND_UNKNOWN)


@dataclass(frozen=True)
class AreaObservation:
    """One date in the series: a measured area, or a recorded gap.

    ``valid=False`` is a **gap**. It keeps its place in the series and its
    reason, so a reader can see that a date was attempted and why it yielded
    nothing, rather than seeing an unexplained absence.
    """

    obs_date: date
    area_m2: float | None = None
    valid: bool = True
    reason: str | None = None
    sensor: str | None = None
    cloud_fraction: float | None = None

    def __post_init__(self) -> None:
        if self.valid and self.area_m2 is None:
            raise ValueError(
                f"observation on {self.obs_date} is marked valid but has no area; "
                "a gap must be constructed with valid=False and a reason"
            )

    @classmethod
    def gap(
        cls,
        obs_date: date,
        reason: str,
        *,
        sensor: str | None = None,
        cloud_fraction: float | None = None,
    ) -> "AreaObservation":
        """A date that was attempted and yielded no usable measurement."""
        return cls(
            obs_date=obs_date,
            area_m2=None,
            valid=False,
            reason=reason,
            sensor=sensor,
            cloud_fraction=cloud_fraction,
        )

    def describe(self) -> str:
        if not self.valid:
            return f"{self.obs_date}: gap ({self.reason or 'no reason recorded'})"
        return f"{self.obs_date}: {self.area_m2:,.0f} m2"


@dataclass(frozen=True)
class TrendResult:
    """A classified trend, with the series and the gaps behind it."""

    trend: str
    n_valid: int
    n_gaps: int
    method: str
    reason: str | None = None
    first_date: date | None = None
    last_date: date | None = None
    span_days: int | None = None
    first_area_m2: float | None = None
    last_area_m2: float | None = None
    absolute_change_m2: float | None = None
    percent_change: float | None = None
    rate_m2_per_day: float | None = None
    fractional_rate_per_day: float | None = None
    observations: list[AreaObservation] = field(default_factory=list)

    @property
    def gaps(self) -> list[AreaObservation]:
        return [o for o in self.observations if not o.valid]

    @property
    def is_determinate(self) -> bool:
        return self.trend != TREND_UNKNOWN

    def describe(self) -> str:
        if not self.is_determinate:
            return f"trend {self.trend}: {self.reason}"
        # percent_change is None when the first area was zero: a percentage of
        # nothing is undefined, and "inf%" would be worse than saying so.
        percent = (
            f" ({self.percent_change:+.1f}%)"
            if self.percent_change is not None
            else " (percent change undefined: the first area was zero)"
        )
        return (
            f"trend {self.trend}: {self.absolute_change_m2:+,.0f} m2"
            f"{percent} over {self.span_days} days, "
            f"rate {self.rate_m2_per_day:+,.1f} m2/day "
            f"[{self.n_valid} valid, {self.n_gaps} gap(s)]"
        )

    def as_dict(self) -> dict[str, Any]:
        return {
            "trend": self.trend,
            "n_valid": self.n_valid,
            "n_gaps": self.n_gaps,
            "method": self.method,
            "reason": self.reason,
            "first_date": str(self.first_date) if self.first_date else None,
            "last_date": str(self.last_date) if self.last_date else None,
            "span_days": self.span_days,
            "first_area_m2": self.first_area_m2,
            "last_area_m2": self.last_area_m2,
            "absolute_change_m2": self.absolute_change_m2,
            "percent_change": self.percent_change,
            "rate_m2_per_day": self.rate_m2_per_day,
            "fractional_rate_per_day": self.fractional_rate_per_day,
            "gaps": [
                {"date": str(g.obs_date), "reason": g.reason} for g in self.gaps
            ],
        }


def theil_sen_slope(x: Sequence[float], y: Sequence[float]) -> float | None:
    """The median of the slopes between every pair of points (Sen 1968).

    Returns ``None`` when no pair has a distinct ``x``, which is the honest
    answer: without a time span there is no rate.
    """
    if len(x) != len(y):
        raise ValueError(f"x and y differ in length: {len(x)} vs {len(y)}")

    slopes = [
        (y[j] - y[i]) / (x[j] - x[i])
        for i in range(len(x))
        for j in range(i + 1, len(x))
        if x[j] != x[i]
    ]
    return float(statistics.median(slopes)) if slopes else None


def endpoint_slope(x: Sequence[float], y: Sequence[float]) -> float | None:
    """Slope between the first and last points. Not robust; offered for
    comparison and for series too short for a median to mean anything."""
    if len(x) < 2 or x[-1] == x[0]:
        return None
    return float((y[-1] - y[0]) / (x[-1] - x[0]))


def analyse_trend(
    cfg: "Config",
    observations: Sequence[AreaObservation],
    *,
    reference_date: date | None = None,
) -> TrendResult:
    """Classify the trend in lake area across a series of observations.

    Args:
        observations: in any order; sorted here. Gaps are kept and reported
            but never contribute a value.
        reference_date: "today" for the staleness check. Defaults to the
            latest date in the series, which disables staleness -- pass a real
            date when assessing whether an assessment is current.

    Returns:
        A :class:`TrendResult`. ``Unknown`` carries the reason it could not be
        determined; it never means "Stable".
    """
    settings = cfg.analysis.temporal_change
    ordered = sorted(observations, key=lambda o: o.obs_date)
    valid = [o for o in ordered if o.valid and o.area_m2 is not None]
    gaps = [o for o in ordered if not o.valid]

    def unknown(reason: str) -> TrendResult:
        result = TrendResult(
            trend=TREND_UNKNOWN,
            n_valid=len(valid),
            n_gaps=len(gaps),
            method=settings.slope_method,
            reason=reason,
            observations=list(ordered),
        )
        log.info("%s", result.describe())
        return result

    if not ordered:
        return unknown("no observations were supplied")

    if len(valid) < settings.min_valid_observations:
        return unknown(
            f"only {len(valid)} valid observation(s) and {len(gaps)} gap(s); "
            f"{settings.min_valid_observations} valid are required. Too little "
            "data is not evidence of stability"
        )

    first, last = valid[0], valid[-1]
    span_days = (last.obs_date - first.obs_date).days
    if span_days <= 0:
        return unknown(
            f"all {len(valid)} valid observations fall on {first.obs_date}; "
            "without a time span there is no rate"
        )

    # Staleness: an old trend is not a current assessment.
    reference = reference_date or last.obs_date
    age_days = (reference - last.obs_date).days
    if age_days > settings.max_age_days:
        return unknown(
            f"the most recent valid observation is {age_days} days old "
            f"({last.obs_date}), beyond the {settings.max_age_days}-day limit; "
            "the series is stale rather than stable"
        )

    days = [float((o.obs_date - first.obs_date).days) for o in valid]
    areas = [float(o.area_m2) for o in valid]

    slope = (
        theil_sen_slope(days, areas)
        if settings.slope_method == "theil_sen"
        else endpoint_slope(days, areas)
    )
    if slope is None:
        return unknown("no pair of valid observations has a distinct date")

    mean_area = statistics.fmean(areas)
    fractional_rate = slope / mean_area if mean_area > 0 else None

    absolute_change = areas[-1] - areas[0]
    percent_change = (
        100.0 * absolute_change / areas[0] if areas[0] > 0 else None
    )

    if settings.trend_metric == "relative":
        if fractional_rate is None:
            return unknown(
                "the mean area is zero, so a relative rate is undefined; set "
                "trend_metric to 'absolute' to classify this series"
            )
        magnitude, threshold = abs(fractional_rate), settings.stable_fraction_per_day
        metric = f"|{fractional_rate:.5f}|/day vs {threshold}/day of mean area"
    else:
        magnitude, threshold = abs(slope), settings.stable_rate_m2_per_day
        metric = f"|{slope:.1f}| m2/day vs {threshold} m2/day"

    if magnitude <= threshold:
        trend = TREND_STABLE
    elif slope > 0:
        trend = TREND_INCREASING
    else:
        trend = TREND_DECREASING

    result = TrendResult(
        trend=trend,
        n_valid=len(valid),
        n_gaps=len(gaps),
        method=(
            f"{settings.slope_method} slope, {settings.trend_metric} threshold "
            f"({metric})"
        ),
        first_date=first.obs_date,
        last_date=last.obs_date,
        span_days=span_days,
        first_area_m2=areas[0],
        last_area_m2=areas[-1],
        absolute_change_m2=absolute_change,
        percent_change=percent_change,
        rate_m2_per_day=slope,
        fractional_rate_per_day=fractional_rate,
        observations=list(ordered),
    )
    log.info("%s", result.describe())
    if gaps:
        log.info(
            "  %d gap(s) recorded and excluded from the fit: %s",
            len(gaps),
            ", ".join(str(g.obs_date) for g in gaps),
        )
    return result
