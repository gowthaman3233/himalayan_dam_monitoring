"""Lake-area time series and trend (brief, Section 7.8).

Series are hand-built so the right answer is known. The emphasis is on what
happens when data is missing: gaps must be recorded and never interpolated,
and too little data must give Unknown rather than Stable.
"""

from __future__ import annotations

from datetime import date, timedelta

import pytest

from analysis.change import (
    TREND_DECREASING,
    TREND_INCREASING,
    TREND_STABLE,
    TREND_UNKNOWN,
    TRENDS,
    AreaObservation,
    analyse_trend,
    endpoint_slope,
    theil_sen_slope,
)
from config.schema import Config

pytestmark = pytest.mark.synthetic

START = date(2023, 10, 1)


def replace_change_config(cfg: Config, **overrides) -> Config:
    data = cfg.model_dump(mode="python")
    data["analysis"]["temporal_change"].update(overrides)
    return Config.model_validate(data)


def series(areas, *, step_days=10, start=START):
    """A clean series of valid observations, evenly spaced."""
    return [
        AreaObservation(obs_date=start + timedelta(days=i * step_days), area_m2=float(a))
        for i, a in enumerate(areas)
    ]


# --------------------------------------------------------------------------- #
# Slope estimators
# --------------------------------------------------------------------------- #


class TestSlopes:
    def test_theil_sen_recovers_a_clean_slope(self) -> None:
        x = [0.0, 1.0, 2.0, 3.0, 4.0]
        y = [10.0, 12.0, 14.0, 16.0, 18.0]
        assert theil_sen_slope(x, y) == pytest.approx(2.0)

    def test_theil_sen_ignores_a_single_bad_point(self) -> None:
        """Why the median of pairwise slopes, not least squares (Sen 1968).

        One mis-segmented date -- a cloud edge counted as water -- should not
        decide the trend.
        """
        x = [0.0, 1.0, 2.0, 3.0, 4.0, 5.0]
        clean = [10.0, 12.0, 14.0, 16.0, 18.0, 20.0]
        corrupted = list(clean)
        corrupted[3] = 900.0

        robust = theil_sen_slope(x, corrupted)
        naive = endpoint_slope(x, corrupted)
        assert robust == pytest.approx(2.0)
        assert naive == pytest.approx(2.0)  # endpoints happen to survive here

        # But corrupt an endpoint and the difference is stark.
        corrupted_end = list(clean)
        corrupted_end[-1] = 900.0
        assert theil_sen_slope(x, corrupted_end) == pytest.approx(2.0, abs=2.0)
        assert endpoint_slope(x, corrupted_end) == pytest.approx(178.0)

    def test_theil_sen_handles_a_negative_slope(self) -> None:
        assert theil_sen_slope([0.0, 1.0, 2.0], [10.0, 8.0, 6.0]) == pytest.approx(-2.0)

    def test_no_time_span_has_no_slope(self) -> None:
        assert theil_sen_slope([3.0, 3.0, 3.0], [1.0, 2.0, 3.0]) is None
        assert endpoint_slope([3.0, 3.0], [1.0, 2.0]) is None

    def test_mismatched_lengths_are_refused(self) -> None:
        with pytest.raises(ValueError, match="differ in length"):
            theil_sen_slope([1.0, 2.0], [1.0])


# --------------------------------------------------------------------------- #
# Gaps
# --------------------------------------------------------------------------- #


class TestGaps:
    def test_a_valid_observation_needs_an_area(self) -> None:
        with pytest.raises(ValueError, match="marked valid but has no area"):
            AreaObservation(obs_date=START, area_m2=None, valid=True)

    def test_a_gap_keeps_its_reason(self) -> None:
        gap = AreaObservation.gap(START, "cloud cover 96%", cloud_fraction=96.0)
        assert not gap.valid
        assert gap.area_m2 is None
        assert "96%" in gap.describe()

    def test_gaps_are_counted_and_reported(self, cfg: Config) -> None:
        observations = series([1_000_000, 1_020_000, 1_040_000, 1_060_000])
        observations.insert(2, AreaObservation.gap(date(2023, 10, 15), "cloud"))
        result = analyse_trend(cfg, observations)

        assert result.n_gaps == 1
        assert result.n_valid == 4
        assert [g.reason for g in result.gaps] == ["cloud"]
        assert result.as_dict()["gaps"] == [{"date": "2023-10-15", "reason": "cloud"}]

    def test_a_gap_is_never_interpolated(self, cfg: Config) -> None:
        """The central rule: a gap contributes no value to the fit.

        The series with a gap inserted must give exactly the same rate as the
        series without that row, because the gap carries no measurement.
        """
        clean = series([1_000_000, 1_020_000, 1_040_000, 1_060_000])
        with_gap = list(clean)
        with_gap.insert(2, AreaObservation.gap(date(2023, 10, 15), "cloud"))

        without = analyse_trend(cfg, clean)
        withgap = analyse_trend(cfg, with_gap)

        assert withgap.rate_m2_per_day == pytest.approx(without.rate_m2_per_day)
        assert withgap.first_area_m2 == without.first_area_m2
        assert withgap.last_area_m2 == without.last_area_m2
        assert withgap.n_valid == without.n_valid

    def test_a_long_gap_does_not_create_a_phantom_point(self, cfg: Config) -> None:
        observations = [
            AreaObservation(obs_date=START, area_m2=1_000_000.0),
            AreaObservation.gap(START + timedelta(days=30), "monsoon cloud"),
            AreaObservation.gap(START + timedelta(days=60), "monsoon cloud"),
            AreaObservation(obs_date=START + timedelta(days=90), area_m2=1_300_000.0),
            AreaObservation(obs_date=START + timedelta(days=100), area_m2=1_330_000.0),
        ]
        result = analyse_trend(cfg, observations)
        assert result.n_valid == 3
        assert result.n_gaps == 2
        # Only the three measured areas appear anywhere in the result.
        assert result.first_area_m2 == 1_000_000.0
        assert result.last_area_m2 == 1_330_000.0


# --------------------------------------------------------------------------- #
# Trend classification
# --------------------------------------------------------------------------- #


class TestTrend:
    def test_the_four_trends_are_the_brief_s(self) -> None:
        assert TRENDS == ("Increasing", "Decreasing", "Stable", "Unknown")

    def test_an_expanding_lake_is_increasing(self, cfg: Config) -> None:
        """Required scenario 7."""
        result = analyse_trend(
            cfg, series([1_000_000, 1_100_000, 1_210_000, 1_330_000])
        )
        assert result.trend == TREND_INCREASING
        assert result.rate_m2_per_day > 0
        assert result.absolute_change_m2 == pytest.approx(330_000.0)
        assert result.percent_change == pytest.approx(33.0)

    def test_a_shrinking_lake_is_decreasing(self, cfg: Config) -> None:
        result = analyse_trend(cfg, series([1_330_000, 1_210_000, 1_100_000, 1_000_000]))
        assert result.trend == TREND_DECREASING
        assert result.rate_m2_per_day < 0
        assert result.absolute_change_m2 < 0

    def test_an_unchanging_lake_is_stable(self, cfg: Config) -> None:
        result = analyse_trend(cfg, series([1_600_000] * 5))
        assert result.trend == TREND_STABLE
        assert result.rate_m2_per_day == pytest.approx(0.0)

    def test_a_tiny_drift_is_still_stable(self, cfg: Config) -> None:
        """0.01% per day, well inside the configured band."""
        result = analyse_trend(
            cfg, series([1_600_000, 1_601_600, 1_603_200, 1_604_800])
        )
        assert result.trend == TREND_STABLE

    def test_rate_is_reported_in_m2_per_day(self, cfg: Config) -> None:
        """The brief asks for m2/day explicitly."""
        result = analyse_trend(cfg, series([1_000_000, 1_010_000, 1_020_000], step_days=10))
        assert result.rate_m2_per_day == pytest.approx(1000.0)

    def test_relative_metric_scales_with_lake_size(self, cfg: Config) -> None:
        """The same m2/day is decisive for a pond and trivial for a lake."""
        pond = analyse_trend(cfg, series([10_000, 11_000, 12_000, 13_000]))
        lake = analyse_trend(cfg, series([5_000_000, 5_001_000, 5_002_000, 5_003_000]))
        assert pond.rate_m2_per_day == pytest.approx(lake.rate_m2_per_day)
        assert pond.trend == TREND_INCREASING
        assert lake.trend == TREND_STABLE

    def test_absolute_metric_is_available(self, cfg: Config) -> None:
        absolute = replace_change_config(cfg, trend_metric="absolute")
        lake = analyse_trend(absolute, series([5_000_000, 5_001_000, 5_002_000, 5_003_000]))
        assert lake.rate_m2_per_day == pytest.approx(100.0)
        assert lake.trend == TREND_STABLE  # exactly at the 100 m2/day threshold

    def test_thresholds_are_configurable(self, cfg: Config) -> None:
        observations = series([1_600_000, 1_601_600, 1_603_200, 1_604_800])
        assert analyse_trend(cfg, observations).trend == TREND_STABLE
        strict = replace_change_config(cfg, stable_fraction_per_day=0.00001)
        assert analyse_trend(strict, observations).trend == TREND_INCREASING

    def test_endpoint_method_is_selectable(self, cfg: Config) -> None:
        tuned = replace_change_config(cfg, slope_method="endpoints")
        result = analyse_trend(tuned, series([1_000_000, 1_500_000, 1_020_000]))
        assert "endpoints" in result.method


# --------------------------------------------------------------------------- #
# Unknown is not Stable
# --------------------------------------------------------------------------- #


class TestUnknownIsNotStable:
    def test_too_few_observations_is_unknown(self, cfg: Config) -> None:
        result = analyse_trend(cfg, series([1_000_000, 1_100_000]))
        assert result.trend == TREND_UNKNOWN
        assert "not evidence of stability" in result.reason
        assert result.rate_m2_per_day is None

    def test_no_observations_at_all_is_unknown(self, cfg: Config) -> None:
        result = analyse_trend(cfg, [])
        assert result.trend == TREND_UNKNOWN
        assert "no observations" in result.reason

    def test_a_cloudy_only_window_is_unknown_and_does_not_crash(
        self, cfg: Config
    ) -> None:
        """Required scenario 9: graceful 'no valid observation', no crash."""
        observations = [
            AreaObservation.gap(START + timedelta(days=i * 5), "cloud cover 98%")
            for i in range(6)
        ]
        result = analyse_trend(cfg, observations)
        assert result.trend == TREND_UNKNOWN
        assert result.n_valid == 0
        assert result.n_gaps == 6
        assert result.rate_m2_per_day is None
        assert "0 valid observation" in result.reason

    def test_observations_on_one_date_have_no_rate(self, cfg: Config) -> None:
        observations = [
            AreaObservation(obs_date=START, area_m2=1_000_000.0),
            AreaObservation(obs_date=START, area_m2=1_010_000.0),
            AreaObservation(obs_date=START, area_m2=1_020_000.0),
        ]
        result = analyse_trend(cfg, observations)
        assert result.trend == TREND_UNKNOWN
        assert "no rate" in result.reason

    def test_a_stale_series_is_unknown_not_stable(self, cfg: Config) -> None:
        """A month-old 'Stable' is not a current assessment."""
        observations = series([1_600_000] * 4)
        fresh = analyse_trend(cfg, observations, reference_date=observations[-1].obs_date)
        stale = analyse_trend(
            cfg, observations, reference_date=observations[-1].obs_date + timedelta(days=90)
        )
        assert fresh.trend == TREND_STABLE
        assert stale.trend == TREND_UNKNOWN
        assert "stale rather than stable" in stale.reason

    def test_staleness_limit_is_configurable(self, cfg: Config) -> None:
        observations = series([1_600_000] * 4)
        patient = replace_change_config(cfg, max_age_days=365)
        result = analyse_trend(
            patient,
            observations,
            reference_date=observations[-1].obs_date + timedelta(days=90),
        )
        assert result.trend == TREND_STABLE

    def test_unknown_carries_no_numbers(self, cfg: Config) -> None:
        result = analyse_trend(cfg, series([1_000_000]))
        assert result.absolute_change_m2 is None
        assert result.percent_change is None
        assert result.rate_m2_per_day is None
        assert not result.is_determinate

    def test_percent_change_from_zero_is_none_not_infinite(self, cfg: Config) -> None:
        result = analyse_trend(cfg, series([0.0, 1000.0, 2000.0, 3000.0]))
        assert result.percent_change is None
        assert result.absolute_change_m2 == pytest.approx(3000.0)


# --------------------------------------------------------------------------- #
# Feeding Phase 11
# --------------------------------------------------------------------------- #


class TestFeedsRiskAssessment:
    def test_a_growth_rate_unlocks_the_risk_factor(self, cfg: Config) -> None:
        """Phase 11's lake_growth_rate is unavailable until Phase 9 supplies it."""
        from analysis.risk import assess_risk

        trend = analyse_trend(cfg, series([1_000_000, 1_100_000, 1_210_000, 1_330_000]))
        assert trend.trend == TREND_INCREASING

        without = assess_risk(cfg, slope_deg=40.0)
        with_rate = assess_risk(
            cfg, slope_deg=40.0, lake_growth_rate_m2_per_day=trend.rate_m2_per_day
        )

        growth = next(
            f for f in with_rate.factors if f.name == "lake_growth_rate"
        )
        assert growth.available
        assert with_rate.data_coverage > without.data_coverage

    def test_an_unknown_trend_leaves_the_factor_unavailable(self, cfg: Config) -> None:
        """Unknown must not be passed on as a rate of zero."""
        from analysis.risk import assess_risk

        trend = analyse_trend(cfg, series([1_000_000, 1_100_000]))
        assert trend.trend == TREND_UNKNOWN
        assert trend.rate_m2_per_day is None

        assessment = assess_risk(
            cfg, slope_deg=40.0, lake_growth_rate_m2_per_day=trend.rate_m2_per_day
        )
        growth = next(f for f in assessment.factors if f.name == "lake_growth_rate")
        assert not growth.available
