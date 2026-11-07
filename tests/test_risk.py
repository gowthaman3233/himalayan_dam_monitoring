"""Risk indicators and warnings (brief, Section 9).

No imagery is involved: these are scoring and reporting rules, and the values
below are hand-chosen inputs rather than measurements.
"""

from __future__ import annotations

import json

import pytest

from analysis.risk import (
    LEVEL_CRITICAL,
    LEVEL_HIGH,
    LEVEL_MONITOR,
    LEVEL_NORMAL,
    LEVELS,
    assess_risk,
    level_for_score,
    scale_score,
)
from config.schema import REQUIRED_DISCLAIMER_PHRASE, Config

pytestmark = pytest.mark.synthetic


def replace_risk_config(cfg: Config, **overrides) -> Config:
    """A re-validated copy with ``analysis.risk`` patched."""
    data = cfg.model_dump(mode="python")
    section = data["analysis"]["risk"]
    for key in ("weights", "scales", "levels"):
        patch = overrides.pop(key, None)
        if patch is not None:
            section[key].update(patch)
    section.update(overrides)
    return Config.model_validate(data)


def all_factors(**overrides):
    """A complete, benign set of inputs; override to raise individual factors."""
    inputs = {
        "lake_growth_rate_m2_per_day": 0.0,
        "lake_volume_m3": 0.0,
        "new_landslide_area_m2": 0.0,
        "blockage_confidence": 0.0,
        "slope_deg": 15.0,
        "rainfall_mm_24h": 0.0,
    }
    inputs.update(overrides)
    return inputs


# --------------------------------------------------------------------------- #
# Scaling
# --------------------------------------------------------------------------- #


class TestScaleScore:
    def test_ends_map_to_zero_and_one(self) -> None:
        assert scale_score(0.0, 0.0, 100.0) == 0.0
        assert scale_score(100.0, 0.0, 100.0) == 1.0

    def test_midpoint(self) -> None:
        assert scale_score(50.0, 0.0, 100.0) == pytest.approx(0.5)

    def test_clamped_outside_the_range(self) -> None:
        assert scale_score(-50.0, 0.0, 100.0) == 0.0
        assert scale_score(1e9, 0.0, 100.0) == 1.0

    def test_descending_scale_is_supported(self) -> None:
        """Some factors are worse when smaller."""
        assert scale_score(0.0, 100.0, 0.0) == 1.0
        assert scale_score(100.0, 100.0, 0.0) == 0.0

    def test_degenerate_scale_is_refused(self) -> None:
        with pytest.raises(ValueError, match="two distinct ends"):
            scale_score(5.0, 3.0, 3.0)


# --------------------------------------------------------------------------- #
# Levels
# --------------------------------------------------------------------------- #


class TestLevels:
    def test_thresholds_select_the_level(self, cfg: Config) -> None:
        levels = cfg.analysis.risk.levels
        assert level_for_score(0.0, cfg) == LEVEL_NORMAL
        assert level_for_score(levels.monitor, cfg) == LEVEL_MONITOR
        assert level_for_score(levels.high_risk, cfg) == LEVEL_HIGH
        assert level_for_score(levels.critical, cfg) == LEVEL_CRITICAL
        assert level_for_score(1.0, cfg) == LEVEL_CRITICAL

    def test_level_wording_is_the_brief_s_own(self) -> None:
        """Section 9's wording is hedged on purpose and must not drift."""
        assert LEVELS == (
            "NORMAL",
            "MONITOR",
            "HIGH RISK INDICATORS",
            "CRITICAL INDICATORS - verification recommended",
        )

    def test_no_level_predicts_failure(self) -> None:
        """The system never says a dam will fail."""
        forbidden = ("will fail", "imminent", "failure expected", "collapse")
        for level in LEVELS:
            lowered = level.lower()
            assert not any(word in lowered for word in forbidden)

    def test_unordered_thresholds_are_refused(self, cfg: Config) -> None:
        with pytest.raises(ValueError, match="must increase"):
            replace_risk_config(cfg, levels={"monitor": 0.8, "high_risk": 0.5})

    def test_thresholds_are_configurable(self, cfg: Config) -> None:
        strict = replace_risk_config(
            cfg, levels={"monitor": 0.05, "high_risk": 0.10, "critical": 0.15}
        )
        assert level_for_score(0.2, strict) == LEVEL_CRITICAL
        assert level_for_score(0.2, cfg) == LEVEL_NORMAL


# --------------------------------------------------------------------------- #
# Scoring
# --------------------------------------------------------------------------- #


class TestScoring:
    def test_all_benign_factors_give_normal(self, cfg: Config) -> None:
        assessment = assess_risk(cfg, **all_factors())
        assert assessment.score == pytest.approx(0.0)
        assert assessment.level == LEVEL_NORMAL
        assert not assessment.insufficient_data

    def test_all_severe_factors_give_critical(self, cfg: Config) -> None:
        assessment = assess_risk(
            cfg,
            **all_factors(
                lake_growth_rate_m2_per_day=10_000.0,
                lake_volume_m3=50_000_000.0,
                new_landslide_area_m2=200_000.0,
                blockage_confidence=1.0,
                slope_deg=70.0,
                rainfall_mm_24h=300.0,
            ),
        )
        assert assessment.score == pytest.approx(1.0)
        assert assessment.level == LEVEL_CRITICAL

    def test_score_is_the_weighted_mean_of_available_factors(
        self, cfg: Config
    ) -> None:
        assessment = assess_risk(cfg, **all_factors(blockage_confidence=1.0))
        weights = cfg.analysis.risk.weights
        expected = weights.blockage_confidence / weights.total()
        assert assessment.score == pytest.approx(expected)

    def test_a_single_growing_lake_raises_the_level(self, cfg: Config) -> None:
        """Required scenario 7: an expanding lake means higher concern."""
        stable = assess_risk(cfg, **all_factors(lake_growth_rate_m2_per_day=0.0))
        growing = assess_risk(cfg, **all_factors(lake_growth_rate_m2_per_day=2000.0))
        assert growing.score > stable.score
        assert LEVELS.index(growing.level) >= LEVELS.index(stable.level)

    def test_weights_are_configurable(self, cfg: Config) -> None:
        inputs = all_factors(slope_deg=45.0)
        default = assess_risk(cfg, **inputs)
        heavier = assess_risk(
            replace_risk_config(cfg, weights={"slope": 20.0}), **inputs
        )
        assert heavier.score > default.score

    def test_zero_weight_factor_does_not_contribute(self, cfg: Config) -> None:
        """Rainfall is weighted 0 by default, so it cannot move the score."""
        assert cfg.analysis.risk.weights.rainfall == 0.0
        dry = assess_risk(cfg, **all_factors(rainfall_mm_24h=0.0))
        soaked = assess_risk(cfg, **all_factors(rainfall_mm_24h=500.0))
        assert dry.score == pytest.approx(soaked.score)


# --------------------------------------------------------------------------- #
# Missing data -- the rule that shapes the design
# --------------------------------------------------------------------------- #


class TestMissingDataIsNotReassurance:
    def test_unavailable_factor_is_excluded_not_scored_zero(
        self, cfg: Config
    ) -> None:
        """The central integrity rule of this phase.

        A factor measured as benign (0) drags the mean down. A factor that
        could not be measured must not: it is excluded from both numerator
        and denominator, so the score reflects only what is known.
        """
        inputs = all_factors(blockage_confidence=1.0)

        measured_zero = assess_risk(cfg, **inputs)
        inputs_without_volume = dict(inputs)
        inputs_without_volume["lake_volume_m3"] = None
        unavailable = assess_risk(cfg, **inputs_without_volume)

        assert unavailable.score > measured_zero.score, (
            "an unmeasured factor must not act as good news"
        )

    def test_branch_b_volume_carries_its_reason(self, cfg: Config) -> None:
        """A Branch B lake has no volume, and the warning says why."""
        assessment = assess_risk(
            cfg,
            **{**all_factors(), "lake_volume_m3": None},
            volume_unavailable_reason="DEM records water surface; no bathymetry",
        )
        volume = next(f for f in assessment.factors if f.name == "lake_volume")
        assert not volume.available
        assert volume.value_type == "unavailable"
        assert "no bathymetry" in volume.reason
        assert "no bathymetry" in assessment.warning_text()

    def test_data_coverage_is_reported(self, cfg: Config) -> None:
        full = assess_risk(cfg, **all_factors())
        assert full.data_coverage == pytest.approx(1.0)

        partial = assess_risk(cfg, blockage_confidence=0.5)
        weights = cfg.analysis.risk.weights
        assert partial.data_coverage == pytest.approx(
            weights.blockage_confidence / weights.total()
        )

    def test_low_coverage_is_flagged_insufficient(self, cfg: Config) -> None:
        """A quiet NORMAL from a fifth of the evidence is the danger."""
        assessment = assess_risk(cfg, slope_deg=15.0)
        assert assessment.level == LEVEL_NORMAL
        assert assessment.insufficient_data
        assert "INSUFFICIENT DATA" in assessment.warning_text()
        assert "not evidence of safety" in assessment.warning_text()

    def test_full_coverage_is_not_flagged(self, cfg: Config) -> None:
        assert not assess_risk(cfg, **all_factors()).insufficient_data

    def test_no_factors_at_all_is_insufficient_not_normal_and_quiet(
        self, cfg: Config
    ) -> None:
        assessment = assess_risk(cfg)
        assert assessment.data_coverage == 0.0
        assert assessment.insufficient_data
        assert assessment.score == 0.0
        assert "INSUFFICIENT DATA" in assessment.warning_text()
        assert "none could be measured" in assessment.warning_text()

    def test_coverage_floor_is_configurable(self, cfg: Config) -> None:
        lenient = replace_risk_config(cfg, min_data_coverage=0.0)
        assert not assess_risk(lenient, slope_deg=15.0).insufficient_data


# --------------------------------------------------------------------------- #
# The warning itself
# --------------------------------------------------------------------------- #


class TestWarningOutput:
    def test_every_warning_lists_its_factors(self, cfg: Config) -> None:
        """Brief, Section 9: each warning must list the factors behind it."""
        assessment = assess_risk(
            cfg, **all_factors(blockage_confidence=0.8, lake_growth_rate_m2_per_day=900.0)
        )
        text = assessment.warning_text()
        assert "Contributing factors:" in text
        for factor in assessment.available_factors:
            assert factor.name in text

    def test_factors_are_ordered_most_influential_first(self, cfg: Config) -> None:
        assessment = assess_risk(
            cfg,
            **all_factors(
                blockage_confidence=1.0,
                lake_growth_rate_m2_per_day=200.0,
            ),
        )
        contributions = [f.contribution for f in assessment.contributing_factors()]
        assert contributions == sorted(contributions, reverse=True)
        assert assessment.contributing_factors()[0].name == "blockage_confidence"

    def test_every_warning_carries_the_disclaimer(self, cfg: Config) -> None:
        text = assess_risk(cfg, **all_factors()).warning_text()
        assert REQUIRED_DISCLAIMER_PHRASE in text
        assert cfg.project.disclaimer in text

    def test_disclaimer_is_present_even_at_normal(self, cfg: Config) -> None:
        """Not just on alarming outputs."""
        assessment = assess_risk(cfg, **all_factors())
        assert assessment.level == LEVEL_NORMAL
        assert REQUIRED_DISCLAIMER_PHRASE in assessment.warning_text()

    def test_missing_factors_are_listed_too(self, cfg: Config) -> None:
        assessment = assess_risk(cfg, slope_deg=20.0)
        text = assessment.warning_text()
        assert "Not measured:" in text
        assert "lake_volume" in text

    def test_each_level_has_a_symbol(self) -> None:
        from analysis.risk import LEVEL_SYMBOLS

        assert set(LEVEL_SYMBOLS) == set(LEVELS)

    def test_contribution_is_none_for_unavailable_factors(self, cfg: Config) -> None:
        """Not 0.0 -- the same distinction Phase 10 enforces for volume."""
        assessment = assess_risk(cfg, slope_deg=20.0)
        volume = next(f for f in assessment.factors if f.name == "lake_volume")
        assert volume.as_dict()["contribution"] is None


# --------------------------------------------------------------------------- #
# Persistence
# --------------------------------------------------------------------------- #


class TestRecord:
    def test_record_maps_to_the_database_columns(self, cfg: Config) -> None:
        """Section 10's risk_assessments table."""
        record = assess_risk(cfg, **all_factors()).as_record(site_id=7)
        assert set(record) == {
            "site_id",
            "assessed_at",
            "factors_json",
            "score",
            "level",
            "config_version",
            # Beyond the brief's minimum, so a stored level cannot be read
            # without its coverage.
            "data_coverage",
            "insufficient_data",
        }
        assert record["site_id"] == 7
        assert record["level"] in LEVELS

    def test_factors_json_round_trips(self, cfg: Config) -> None:
        record = assess_risk(cfg, **all_factors(blockage_confidence=0.6)).as_record(1)
        factors = json.loads(record["factors_json"])
        assert len(factors) == 6
        names = {f["name"] for f in factors}
        assert "blockage_confidence" in names
        assert all("available" in f and "value_type" in f for f in factors)

    def test_assessment_is_timestamped_and_versioned(self, cfg: Config) -> None:
        assessment = assess_risk(cfg, **all_factors(), config_hash="abc123")
        assert assessment.assessed_at.endswith("Z")
        assert assessment.config_version == cfg.project.version
        assert assessment.config_hash == "abc123"


# --------------------------------------------------------------------------- #
# The symbol must not say "fine" on thin evidence
# --------------------------------------------------------------------------- #


class TestSymbolWithholding:
    def test_green_is_withheld_when_normal_rests_on_thin_evidence(
        self, cfg: Config
    ) -> None:
        """A dashboard may render only the symbol."""
        from analysis.risk import INSUFFICIENT_DATA_SYMBOL, LEVEL_SYMBOLS

        thin = assess_risk(cfg, slope_deg=15.0)
        assert thin.level == LEVEL_NORMAL
        assert thin.insufficient_data
        assert thin.symbol == INSUFFICIENT_DATA_SYMBOL
        assert thin.symbol != LEVEL_SYMBOLS[LEVEL_NORMAL]

    def test_green_is_shown_when_normal_is_well_evidenced(self, cfg: Config) -> None:
        from analysis.risk import LEVEL_SYMBOLS

        full = assess_risk(cfg, **all_factors())
        assert full.level == LEVEL_NORMAL
        assert not full.insufficient_data
        assert full.symbol == LEVEL_SYMBOLS[LEVEL_NORMAL]

    def test_a_real_alarm_is_never_muted_by_thin_evidence(self, cfg: Config) -> None:
        """The opposite mistake: withholding red would be worse."""
        from analysis.risk import INSUFFICIENT_DATA_SYMBOL, LEVEL_SYMBOLS

        alarming = assess_risk(cfg, blockage_confidence=1.0)
        assert alarming.insufficient_data
        assert alarming.level == LEVEL_CRITICAL
        assert alarming.symbol == LEVEL_SYMBOLS[LEVEL_CRITICAL]
        assert alarming.symbol != INSUFFICIENT_DATA_SYMBOL


# --------------------------------------------------------------------------- #
# Saturation -- a clamped factor must say so
# --------------------------------------------------------------------------- #
class TestScaleSaturationIsReported:
    """A value past its scale's end loses information, silently.

    `scale_score` clamps, so 90,300 m2 and 900,000 m2 both score 1.00 on a
    [0, 50000] m2 scale. Measured on Baige 2018: the merged deposit pinned
    that ceiling, so any larger dam would have contributed identically. The
    scales here are conventions rather than calibrated measurements, which is
    exactly when a reader needs to know the ceiling was hit.
    """

    def test_a_value_past_the_scale_is_flagged(self, cfg: Config) -> None:
        high = cfg.analysis.risk.scales.new_landslide_area_m2[1]
        result = assess_risk(cfg, new_landslide_area_m2=high * 2.0)
        factor = next(
            f for f in result.factors if f.name == "new_landslide_activity"
        )
        assert factor.saturated
        assert factor.score == pytest.approx(1.0)
        assert "cannot distinguish" in (factor.reason or "")

    def test_a_value_inside_the_scale_is_not_flagged(self, cfg: Config) -> None:
        high = cfg.analysis.risk.scales.new_landslide_area_m2[1]
        result = assess_risk(cfg, new_landslide_area_m2=high * 0.5)
        factor = next(
            f for f in result.factors if f.name == "new_landslide_activity"
        )
        assert not factor.saturated
        assert factor.reason is None

    def test_exactly_at_the_ceiling_counts_as_saturated(self, cfg: Config) -> None:
        """At the ceiling, the next larger value is already indistinguishable."""
        high = cfg.analysis.risk.scales.new_landslide_area_m2[1]
        result = assess_risk(cfg, new_landslide_area_m2=high)
        factor = next(
            f for f in result.factors if f.name == "new_landslide_activity"
        )
        assert factor.saturated

    def test_the_warning_text_names_the_saturated_factors(
        self, cfg: Config
    ) -> None:
        high = cfg.analysis.risk.scales.new_landslide_area_m2[1]
        result = assess_risk(cfg, new_landslide_area_m2=high * 3.0)
        text = result.warning_text()
        assert "SCALE CEILING REACHED" in text
        assert "new_landslide_activity" in text
        assert "conventions" in text

    def test_saturation_travels_into_the_stored_record(self, cfg: Config) -> None:
        """A stored assessment must carry it, or the database loses it."""
        high = cfg.analysis.risk.scales.new_landslide_area_m2[1]
        result = assess_risk(cfg, new_landslide_area_m2=high * 2.0)
        factor = next(
            f.as_dict() for f in result.factors
            if f.name == "new_landslide_activity"
        )
        assert factor["saturated"] is True

    def test_an_unavailable_factor_is_never_saturated(self, cfg: Config) -> None:
        result = assess_risk(cfg)
        for f in result.factors:
            assert not f.saturated

    def test_the_baige_deposit_saturates_the_shipped_scale(
        self, cfg: Config
    ) -> None:
        """The measurement that prompted this: 90,300 m2 pins [0, 50000]."""
        result = assess_risk(cfg, new_landslide_area_m2=90_300.0)
        factor = next(
            f for f in result.factors if f.name == "new_landslide_activity"
        )
        assert factor.saturated, (
            "the real Baige deposit no longer saturates the scale; if the "
            "scale was widened deliberately, update this test and say so in "
            "docs/validation.md"
        )
