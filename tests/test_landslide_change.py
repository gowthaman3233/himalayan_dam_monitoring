"""Bi-temporal landslide change detection.

All arrays here are SYNTHETIC (brief, Section 2): hand-made pre/post pairs
where the right answer follows from the physics being encoded. The real-data
gate for this phase needs imagery of a confirmed event (docs/validation.md §2)
and is not run here.
"""

from __future__ import annotations

import numpy as np
import pytest
from affine import Affine

from config.schema import Config
from detection.landslide_change import (
    MAD_TO_SIGMA,
    detect_change,
    landslide_polygons,
    ndsi,
    ndvi,
    robust_change_threshold,
    snow_mask,
)

pytestmark = pytest.mark.synthetic

CELLSIZE = 10.0
UTM45N = "EPSG:32645"
TRANSFORM = Affine(CELLSIZE, 0.0, 450000.0, 0.0, -CELLSIZE, 3085000.0)


def replace_landslide_config(cfg: Config, **overrides) -> Config:
    """A re-validated copy with ``detection.landslide_change`` patched."""
    data = cfg.model_dump(mode="python")
    section = data["detection"]["landslide_change"]
    for key in ("optical", "sar", "gating", "polygons"):
        patch = overrides.pop(key, None)
        if patch is not None:
            section[key].update(patch)
    section.update(overrides)
    return Config.model_validate(data)


def scene(shape=(30, 30)):
    """A vegetated, steep, unchanged hillside on both dates.

    NDVI 0.7 (vegetated), brightness 0.15, backscatter -9 dB, slope 35 deg.
    """
    return {
        "ndvi_pre": np.full(shape, 0.70),
        "ndvi_post": np.full(shape, 0.70),
        "brightness_pre": np.full(shape, 0.15),
        "brightness_post": np.full(shape, 0.15),
        "sar_db_pre": np.full(shape, -9.0),
        "sar_db_post": np.full(shape, -9.0),
        "slope_deg": np.full(shape, 35.0),
    }


def add_landslide(layers, where, *, ndvi_after=0.10, brightness_after=0.35, sar_after=-4.0):
    """Stamp a landslide into the post-event arrays: vegetation stripped,
    fresh bare material brighter, backscatter changed."""
    layers["ndvi_post"][where] = ndvi_after
    layers["brightness_post"][where] = brightness_after
    layers["sar_db_post"][where] = sar_after
    return layers


# --------------------------------------------------------------------------- #
# Indices
# --------------------------------------------------------------------------- #


class TestIndices:
    def test_ndvi_is_high_for_vegetation(self) -> None:
        # Vegetation: high NIR, low red.
        assert ndvi(np.array([3000.0]), np.array([500.0]))[0] > 0.6

    def test_ndvi_is_near_zero_for_bare_rock(self) -> None:
        value = ndvi(np.array([2000.0]), np.array([1900.0]))[0]
        assert abs(value) < 0.1

    def test_ndsi_is_the_same_expression_as_mndwi(self) -> None:
        """Pinned because it is why the NIR test is needed alongside it."""
        from detection.water import mndwi

        green, swir1 = np.array([7000.0]), np.array([600.0])
        assert ndsi(green, swir1)[0] == mndwi(green, swir1)[0]

    def test_snow_needs_both_ndsi_and_nir(self) -> None:
        """NDSI alone also selects water, so Hall et al. add the NIR test."""
        # Snow: high NDSI, bright NIR.
        snow = snow_mask(
            np.array([7000.0]), np.array([600.0]), np.array([0.55])
        )
        # Water: high NDSI, but dark in NIR.
        water = snow_mask(
            np.array([900.0]), np.array([100.0]), np.array([0.05])
        )
        assert snow[0]
        assert not water[0]

    def test_bare_rock_is_not_snow(self) -> None:
        rock = snow_mask(np.array([2000.0]), np.array([2200.0]), np.array([0.25]))
        assert not rock[0]


# --------------------------------------------------------------------------- #
# Robust thresholds
# --------------------------------------------------------------------------- #


class TestRobustThreshold:
    def test_threshold_is_median_plus_z_sigma(self) -> None:
        rng = np.random.default_rng(0)
        data = rng.normal(0.0, 1.0, 20000)
        threshold, median, sigma = robust_change_threshold(data, 3.0)
        assert median == pytest.approx(0.0, abs=0.05)
        assert sigma == pytest.approx(1.0, rel=0.05)
        assert threshold == pytest.approx(median + 3.0 * sigma, rel=1e-9)

    def test_mad_scaling_matches_the_normal_case(self) -> None:
        rng = np.random.default_rng(1)
        data = rng.normal(5.0, 2.0, 50000)
        _, _, sigma = robust_change_threshold(data, 3.0)
        assert sigma == pytest.approx(2.0, rel=0.05)
        assert MAD_TO_SIGMA == pytest.approx(1.4826)

    def test_outliers_do_not_drag_the_threshold(self) -> None:
        """The reason for MAD rather than a standard deviation."""
        rng = np.random.default_rng(2)
        clean = rng.normal(0.0, 1.0, 10000)
        contaminated = np.concatenate([clean, np.full(300, 500.0)])

        robust, _, _ = robust_change_threshold(contaminated, 3.0)
        classical = contaminated.mean() + 3.0 * contaminated.std()

        assert robust < 10.0
        assert classical > 50.0

    def test_absolute_mode_is_centred_on_zero(self) -> None:
        rng = np.random.default_rng(3)
        data = rng.normal(0.0, 1.0, 20000)
        signed, _, sigma = robust_change_threshold(data, 3.0)
        absolute, _, _ = robust_change_threshold(data, 3.0, absolute=True)
        assert absolute == pytest.approx(3.0 * sigma, rel=1e-9)
        assert absolute != signed or abs(signed) < 1e-6

    def test_constant_scene_is_refused(self) -> None:
        with pytest.raises(ValueError, match="median absolute deviation is zero"):
            robust_change_threshold(np.full(100, 4.0), 3.0)

    def test_no_finite_samples_is_refused(self) -> None:
        with pytest.raises(ValueError, match="no finite samples"):
            robust_change_threshold(np.full(10, np.nan), 3.0)


# --------------------------------------------------------------------------- #
# Change detection
# --------------------------------------------------------------------------- #


class TestDetectChange:
    def test_unchanged_hillside_shows_no_change(self, cfg: Config) -> None:
        tuned = replace_landslide_config(
            cfg, optical={"brightness_method": "fixed", "brightness_fixed_increase": 0.05},
            sar={"change_method": "fixed", "fixed_min_abs_db": 2.0},
        )
        result = detect_change(tuned, **scene())
        assert result.changed_pixels == 0

    def test_a_landslide_is_detected(self, cfg: Config) -> None:
        patch = (slice(10, 20), slice(10, 20))
        layers = add_landslide(scene(), patch)
        tuned = replace_landslide_config(
            cfg, optical={"brightness_method": "fixed", "brightness_fixed_increase": 0.05},
            sar={"change_method": "fixed", "fixed_min_abs_db": 2.0},
        )
        result = detect_change(tuned, **layers)
        assert result.change[patch].all()
        assert result.changed_pixels == 100

    def test_all_three_signals_agree_on_a_real_landslide(self, cfg: Config) -> None:
        patch = (slice(10, 20), slice(10, 20))
        layers = add_landslide(scene(), patch)
        tuned = replace_landslide_config(
            cfg, optical={"brightness_method": "fixed", "brightness_fixed_increase": 0.05},
            sar={"change_method": "fixed", "fixed_min_abs_db": 2.0},
        )
        result = detect_change(tuned, **layers)
        assert set(result.signals) == {"ndvi_drop", "brightness_increase", "sar_change"}
        assert (result.agreeing[patch] == 3).all()

    def test_one_signal_alone_is_not_enough(self, cfg: Config) -> None:
        """NDVI drops but nothing else changes -- could be seasonal."""
        patch = (slice(10, 20), slice(10, 20))
        layers = scene()
        layers["ndvi_post"][patch] = 0.10  # vegetation loss only
        tuned = replace_landslide_config(
            cfg, optical={"brightness_method": "fixed", "brightness_fixed_increase": 0.05},
            sar={"change_method": "fixed", "fixed_min_abs_db": 2.0},
        )
        result = detect_change(tuned, **layers)
        assert (result.agreeing[patch] == 1).all()
        assert result.changed_pixels == 0

    def test_required_agreement_is_configurable(self, cfg: Config) -> None:
        patch = (slice(10, 20), slice(10, 20))
        layers = scene()
        layers["ndvi_post"][patch] = 0.10
        permissive = replace_landslide_config(
            cfg,
            min_agreeing_signals=1,
            optical={"brightness_method": "fixed", "brightness_fixed_increase": 0.05},
            sar={"change_method": "fixed", "fixed_min_abs_db": 2.0},
        )
        result = detect_change(permissive, **layers)
        assert result.change[patch].all()

    def test_sar_change_is_detected_in_both_directions(self, cfg: Config) -> None:
        """Backscatter rises on some parts of a landslide and falls on others.

        A signed threshold would systematically miss one of these two cases
        (Burrows et al. 2022; Mondini et al. 2021), so both must be flagged.
        """
        tuned = replace_landslide_config(
            cfg,
            min_agreeing_signals=1,
            sar={"change_method": "fixed", "fixed_min_abs_db": 2.0},
        )

        def sar_only(post_db: float):
            layers = scene()
            layers["sar_db_post"][:] = post_db
            return detect_change(
                tuned,
                sar_db_pre=layers["sar_db_pre"],
                sar_db_post=layers["sar_db_post"],
                slope_deg=layers["slope_deg"],
            )

        brighter = sar_only(-4.0)  # +5 dB
        darker = sar_only(-14.0)  # -5 dB
        assert brighter.signals["sar_change"].indicates_landslide.all()
        assert darker.signals["sar_change"].indicates_landslide.all()

    def test_flat_ground_is_excluded(self, cfg: Config) -> None:
        """Landslides require a slope (Notti et al. 2023: slope > 15 deg)."""
        patch = (slice(10, 20), slice(10, 20))
        layers = add_landslide(scene(), patch)
        layers["slope_deg"][:] = 3.0  # valley floor
        tuned = replace_landslide_config(
            cfg, optical={"brightness_method": "fixed", "brightness_fixed_increase": 0.05},
            sar={"change_method": "fixed", "fixed_min_abs_db": 2.0},
        )
        result = detect_change(tuned, **layers)
        assert result.changed_pixels == 0
        assert result.excluded["slope_below_minimum"].all()

    def test_snow_on_either_date_is_excluded(self, cfg: Config) -> None:
        """Fresh snow mimics a landslide: NDVI falls, brightness rises."""
        patch = (slice(10, 20), slice(10, 20))
        layers = add_landslide(scene(), patch)
        snow_post = np.zeros(layers["ndvi_pre"].shape, dtype=bool)
        snow_post[patch] = True

        tuned = replace_landslide_config(
            cfg, optical={"brightness_method": "fixed", "brightness_fixed_increase": 0.05},
            sar={"change_method": "fixed", "fixed_min_abs_db": 2.0},
        )
        result = detect_change(tuned, snow_post=snow_post, **layers)
        assert result.changed_pixels == 0
        assert result.excluded["snow_post"][patch].all()

    def test_snow_exclusion_can_be_disabled(self, cfg: Config) -> None:
        patch = (slice(10, 20), slice(10, 20))
        layers = add_landslide(scene(), patch)
        snow_post = np.zeros(layers["ndvi_pre"].shape, dtype=bool)
        snow_post[patch] = True
        tuned = replace_landslide_config(
            cfg,
            gating={"exclude_snow": False},
            optical={"brightness_method": "fixed", "brightness_fixed_increase": 0.05},
            sar={"change_method": "fixed", "fixed_min_abs_db": 2.0},
        )
        result = detect_change(tuned, snow_post=snow_post, **layers)
        assert result.change[patch].all()

    def test_cloud_on_either_date_is_excluded(self, cfg: Config) -> None:
        patch = (slice(10, 20), slice(10, 20))
        layers = add_landslide(scene(), patch)
        cloud = np.zeros(layers["ndvi_pre"].shape, dtype=bool)
        cloud[patch] = True
        tuned = replace_landslide_config(
            cfg, optical={"brightness_method": "fixed", "brightness_fixed_increase": 0.05},
            sar={"change_method": "fixed", "fixed_min_abs_db": 2.0},
        )
        result = detect_change(tuned, invalid_pre=cloud, **layers)
        assert result.changed_pixels == 0
        assert not result.valid[patch].any()

    def test_terrain_shadow_is_excluded(self, cfg: Config) -> None:
        patch = (slice(10, 20), slice(10, 20))
        layers = add_landslide(scene(), patch)
        shadow = np.zeros(layers["ndvi_pre"].shape, dtype=bool)
        shadow[patch] = True
        tuned = replace_landslide_config(
            cfg, optical={"brightness_method": "fixed", "brightness_fixed_increase": 0.05},
            sar={"change_method": "fixed", "fixed_min_abs_db": 2.0},
        )
        result = detect_change(tuned, terrain_shadow_post=shadow, **layers)
        assert result.changed_pixels == 0

    def test_a_missing_signal_is_absent_not_disagreeing(self, cfg: Config) -> None:
        """A pair with no SAR still works on the two optical signals."""
        patch = (slice(10, 20), slice(10, 20))
        layers = add_landslide(scene(), patch)
        layers.pop("sar_db_pre")
        layers.pop("sar_db_post")
        tuned = replace_landslide_config(
            cfg, optical={"brightness_method": "fixed", "brightness_fixed_increase": 0.05}
        )
        result = detect_change(tuned, **layers)
        assert set(result.signals) == {"ndvi_drop", "brightness_increase"}
        assert result.change[patch].all()

    def test_too_few_signals_to_meet_the_requirement_flags_nothing(
        self, cfg: Config
    ) -> None:
        """Not 'no change' -- undecidable, because the evidence is absent."""
        patch = (slice(10, 20), slice(10, 20))
        layers = add_landslide(scene(), patch)
        only_ndvi = {
            "ndvi_pre": layers["ndvi_pre"],
            "ndvi_post": layers["ndvi_post"],
            "slope_deg": layers["slope_deg"],
        }
        result = detect_change(cfg, **only_ndvi)  # default requires 2
        assert result.changed_pixels == 0
        assert not result.valid.any()

    def test_no_signals_at_all_is_refused(self, cfg: Config) -> None:
        with pytest.raises(ValueError, match="no change signal"):
            detect_change(cfg, slope_deg=np.full((5, 5), 30.0))

    def test_mismatched_shapes_are_refused(self, cfg: Config) -> None:
        with pytest.raises(ValueError, match="mismatched shapes"):
            detect_change(
                cfg, ndvi_pre=np.zeros((4, 4)), ndvi_post=np.zeros((5, 5))
            )

    def test_data_driven_thresholds_are_reported(self, cfg: Config) -> None:
        """The derived threshold must be visible, not hidden in the result."""
        patch = (slice(10, 20), slice(10, 20))
        layers = add_landslide(scene(), patch)
        # mad_zscore needs variation, so add a little noise.
        rng = np.random.default_rng(4)
        layers["brightness_post"] += rng.normal(0.0, 0.005, layers["brightness_post"].shape)
        layers["sar_db_post"] += rng.normal(0.0, 0.2, layers["sar_db_post"].shape)

        result = detect_change(cfg, **layers)
        brightness = result.signals["brightness_increase"]
        assert "MAD sigma" in brightness.method
        assert np.isfinite(brightness.threshold)
        assert "MAD sigma" in result.signals["sar_change"].method

    def test_fixed_methods_require_a_value(self, cfg: Config) -> None:
        with pytest.raises(ValueError, match="does not invent"):
            replace_landslide_config(
                cfg, sar={"change_method": "fixed", "fixed_min_abs_db": None}
            )
        with pytest.raises(ValueError, match="does not invent"):
            replace_landslide_config(
                cfg,
                optical={
                    "brightness_method": "fixed",
                    "brightness_fixed_increase": None,
                },
            )


# --------------------------------------------------------------------------- #
# Polygons
# --------------------------------------------------------------------------- #


class TestPolygons:
    def result_with_patch(self, cfg: Config, patch, slope=35.0):
        layers = add_landslide(scene((40, 40)), patch)
        layers["slope_deg"][:] = slope
        tuned = replace_landslide_config(
            cfg, optical={"brightness_method": "fixed", "brightness_fixed_increase": 0.05},
            sar={"change_method": "fixed", "fixed_min_abs_db": 2.0},
        )
        return detect_change(tuned, **layers), tuned, layers

    def test_area_is_exact_for_a_square(self, cfg: Config) -> None:
        patch = (slice(10, 20), slice(10, 20))
        result, tuned, layers = self.result_with_patch(cfg, patch)
        polygons = landslide_polygons(
            result, TRANSFORM, UTM45N, tuned, slope_deg=layers["slope_deg"]
        )
        assert len(polygons) == 1
        assert polygons["area_m2"].iloc[0] == pytest.approx(10_000.0)
        assert polygons["pixel_count"].iloc[0] == 100

    def test_median_slope_is_recorded_and_filters(self, cfg: Config) -> None:
        """Notti et al. filter polygons by median slope as well as pixel slope."""
        patch = (slice(10, 20), slice(10, 20))
        result, tuned, layers = self.result_with_patch(cfg, patch, slope=16.0)
        # 16 deg passes the pixel gate (>15) but fails the polygon gate (>=17).
        polygons = landslide_polygons(
            result, TRANSFORM, UTM45N, tuned, slope_deg=layers["slope_deg"]
        )
        assert len(polygons) == 0

    def test_median_slope_filter_is_configurable(self, cfg: Config) -> None:
        patch = (slice(10, 20), slice(10, 20))
        result, _, layers = self.result_with_patch(cfg, patch, slope=16.0)
        relaxed = replace_landslide_config(
            cfg,
            gating={"min_median_slope_deg": 10.0},
            optical={"brightness_method": "fixed", "brightness_fixed_increase": 0.05},
            sar={"change_method": "fixed", "fixed_min_abs_db": 2.0},
        )
        polygons = landslide_polygons(
            result, TRANSFORM, UTM45N, relaxed, slope_deg=layers["slope_deg"]
        )
        assert len(polygons) == 1
        assert polygons["median_slope_deg"].iloc[0] == pytest.approx(16.0)

    def test_small_polygons_are_dropped(self, cfg: Config) -> None:
        patch = (slice(10, 12), slice(10, 12))  # 4 px = 400 m^2
        result, tuned, layers = self.result_with_patch(cfg, patch)
        polygons = landslide_polygons(
            result, TRANSFORM, UTM45N, tuned, slope_deg=layers["slope_deg"]
        )
        assert len(polygons) == 0

    def test_geographic_crs_is_refused(self, cfg: Config) -> None:
        patch = (slice(10, 20), slice(10, 20))
        result, tuned, layers = self.result_with_patch(cfg, patch)
        with pytest.raises(ValueError, match="requires a projected CRS"):
            landslide_polygons(result, TRANSFORM, "EPSG:4326", tuned)

    def test_empty_change_map_returns_the_columns(self, cfg: Config) -> None:
        result, tuned, _ = self.result_with_patch(cfg, (slice(0, 0), slice(0, 0)))
        polygons = landslide_polygons(result, TRANSFORM, UTM45N, tuned)
        assert len(polygons) == 0
        assert "area_m2" in polygons.columns
        assert "median_slope_deg" in polygons.columns

    def test_mean_agreeing_signals_is_recorded(self, cfg: Config) -> None:
        patch = (slice(10, 20), slice(10, 20))
        result, tuned, layers = self.result_with_patch(cfg, patch)
        polygons = landslide_polygons(
            result, TRANSFORM, UTM45N, tuned, slope_deg=layers["slope_deg"]
        )
        assert polygons["mean_agreeing_signals"].iloc[0] == pytest.approx(3.0)


class TestUncomputableSignalIsNotFatal:
    """A signal with no scale is recorded unavailable, never raised.

    Found by the end-to-end pipeline test: a perfectly uniform scene crashed
    the detector outright, where the project's rule everywhere else is to
    report "unavailable with a reason" and carry on with what remains.
    """

    def test_a_noiseless_scene_does_not_crash(self, cfg: Config) -> None:
        layers = scene()  # uniform: every change is exactly zero
        result = detect_change(cfg, **layers)
        assert result.changed_pixels == 0

    def test_the_uncomputable_signals_are_marked_unavailable(
        self, cfg: Config
    ) -> None:
        result = detect_change(cfg, **scene())
        for name in ("brightness_increase", "sar_change"):
            signal = result.signals[name]
            assert not signal.available.any()
            assert "unavailable" in signal.method
            assert "no scale" in signal.method

    def test_an_unavailable_signal_neither_helps_nor_hinders(
        self, cfg: Config
    ) -> None:
        """It must not count as agreement, nor as disagreement."""
        patch = (slice(10, 20), slice(10, 20))
        layers = scene()
        layers["ndvi_post"][patch] = 0.10  # only NDVI can be computed
        result = detect_change(cfg, **layers)
        assert result.signals["ndvi_drop"].available.any()
        assert not result.signals["sar_change"].available.any()
        # Default requires 2 agreeing signals; only 1 is computable.
        assert result.changed_pixels == 0
        assert not result.valid.any()


class TestWaterIsNotLandslide:
    """New water satisfies two of the three signals on its own.

    NDVI falls sharply (water absorbs NIR) and the SAR change is large (water
    is specular), so a change map at a landslide-dam site fills with the
    impoundment unless it is excluded. Measured at Baige: 28.7% of the change
    map, and 51.2% of its largest polygon, was new water.
    """

    def test_post_date_water_is_excluded_by_default(self, cfg: Config) -> None:
        patch = (slice(10, 20), slice(10, 20))
        layers = scene()
        # A patch that became open water: NDVI collapses, backscatter collapses.
        layers["ndvi_post"][patch] = -0.95
        layers["sar_db_post"][patch] = -22.0

        became_water = np.zeros(layers["ndvi_pre"].shape, dtype=bool)
        became_water[patch] = True

        tuned = replace_landslide_config(
            cfg,
            optical={"brightness_method": "fixed", "brightness_fixed_increase": 0.05},
            sar={"change_method": "fixed", "fixed_min_abs_db": 2.0},
            min_agreeing_signals=2,
        )
        without = detect_change(tuned, **layers)
        with_mask = detect_change(tuned, water_post=became_water, **layers)

        assert without.change[patch].any(), "water does trip the signals"
        assert not with_mask.change[patch].any()
        assert with_mask.excluded["water_on_post_date"][patch].all()

    def test_the_exclusion_can_be_disabled(self, cfg: Config) -> None:
        patch = (slice(10, 20), slice(10, 20))
        layers = scene()
        layers["ndvi_post"][patch] = -0.95
        layers["sar_db_post"][patch] = -22.0
        became_water = np.zeros(layers["ndvi_pre"].shape, dtype=bool)
        became_water[patch] = True

        tuned = replace_landslide_config(
            cfg,
            gating={"exclude_water_on_post_date": False},
            optical={"brightness_method": "fixed", "brightness_fixed_increase": 0.05},
            sar={"change_method": "fixed", "fixed_min_abs_db": 2.0},
        )
        assert detect_change(tuned, water_post=became_water, **layers).change[patch].any()

    def test_a_real_landslide_is_unaffected(self, cfg: Config) -> None:
        patch = (slice(10, 20), slice(10, 20))
        layers = add_landslide(scene(), patch)
        no_water = np.zeros(layers["ndvi_pre"].shape, dtype=bool)
        tuned = replace_landslide_config(
            cfg,
            optical={"brightness_method": "fixed", "brightness_fixed_increase": 0.05},
            sar={"change_method": "fixed", "fixed_min_abs_db": 2.0},
        )
        assert detect_change(tuned, water_post=no_water, **layers).change[patch].all()
