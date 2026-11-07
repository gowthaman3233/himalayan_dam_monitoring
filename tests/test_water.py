"""Rule-based water detection: indices, thresholding and water-body polygons.

Arrays built in this file are SYNTHETIC (brief, Section 2) -- hand-made so that
the right answer is known analytically. The one exception is
``TestRealStack``, marked ``realdata``, which runs the detector over the real
Phase 2 Sentinel-1/2 stack of Tsho Rolpa and skips when that stack is absent.
"""

from __future__ import annotations

from pathlib import Path

import numpy as np
import pytest
from affine import Affine

from config.schema import Config
from detection.water import (
    Bimodality,
    ThresholdDecision,
    bimodality,
    boundaries,
    combine_evidence,
    mndwi,
    ndwi,
    optical_water_mask,
    otsu_threshold,
    sar_water_mask,
    sar_water_threshold,
    spectral_index,
    tiled_otsu_threshold,
    water_bodies,
)

CELLSIZE = 10.0
UTM45N = "EPSG:32645"

#: A north-up 10 m transform placed inside UTM 45N, near the default AOI.
TRANSFORM = Affine(CELLSIZE, 0.0, 450000.0, 0.0, -CELLSIZE, 3085000.0)


def replace_water_config(cfg: Config, **overrides) -> Config:
    """A copy of ``cfg`` with ``detection.water`` fields overridden.

    The config is frozen, so tests build a modified copy rather than mutating
    the session-scoped fixture. The copy is re-**validated** rather than built
    with ``model_copy``, which skips validators -- a test asserting that an
    invalid combination is refused would otherwise pass vacuously.
    """
    data = cfg.model_dump(mode="python")
    water = data["detection"]["water"]
    for section in ("optical", "sar", "polygons"):
        patch = overrides.pop(section, None)
        if patch is not None:
            water[section].update(patch)
    water.update(overrides)
    return Config.model_validate(data)


# --------------------------------------------------------------------------- #
# Spectral indices
# --------------------------------------------------------------------------- #


@pytest.mark.synthetic
class TestIndices:
    def test_normalised_difference_arithmetic(self) -> None:
        green = np.array([[1000.0, 2000.0]])
        nir = np.array([[3000.0, 2000.0]])
        # (1000-3000)/4000 = -0.5 ; (2000-2000)/4000 = 0.0
        assert np.allclose(spectral_index(green, nir), [[-0.5, 0.0]])

    def test_index_range_is_minus_one_to_one(self) -> None:
        rng = np.random.default_rng(0)
        a = rng.uniform(0.0, 10000.0, size=(40, 40))
        b = rng.uniform(0.0, 10000.0, size=(40, 40))
        values = spectral_index(a, b)
        assert np.nanmin(values) >= -1.0
        assert np.nanmax(values) <= 1.0

    def test_zero_denominator_is_nan_not_zero(self) -> None:
        """Zero is the decision boundary, so it must never be a fill value."""
        values = spectral_index(np.array([0.0]), np.array([0.0]))
        assert np.isnan(values[0])

    def test_nan_input_propagates(self) -> None:
        values = spectral_index(np.array([np.nan, 1000.0]), np.array([500.0, 500.0]))
        assert np.isnan(values[0])
        assert np.isfinite(values[1])

    def test_mismatched_shapes_rejected(self) -> None:
        with pytest.raises(ValueError, match="band shapes differ"):
            spectral_index(np.zeros((2, 2)), np.zeros((3, 3)))

    def test_water_is_positive_in_both_indices(self) -> None:
        """Water: moderate green, near-zero NIR and SWIR1."""
        green, nir, swir1 = (
            np.array([800.0]),
            np.array([150.0]),
            np.array([80.0]),
        )
        assert ndwi(green, nir)[0] > 0.0
        assert mndwi(green, swir1)[0] > 0.0

    def test_mndwi_is_the_same_expression_as_ndsi(self) -> None:
        """MNDWI cannot tell snow from water, by construction.

        The Normalized Difference Snow Index (Hall et al. 1995) is
        ``(Green - SWIR1) / (Green + SWIR1)`` -- the same formula as MNDWI
        (Xu 2006). Snow therefore scores *high* on MNDWI. This is the finding
        that makes the snow screen necessary, so it is pinned as a test.
        """
        green, swir1 = np.array([7000.0]), np.array([600.0])
        ndsi = spectral_index(green, swir1)
        assert mndwi(green, swir1)[0] == ndsi[0]
        assert ndsi[0] > 0.0  # snow, scored as water by MNDWI

    def test_neither_index_rejects_snow(self) -> None:
        """Both indices call snow water, so neither is a snow discriminator.

        Reflectance values encode the spectral *ordering* snow is known to have
        (high green, high NIR, low SWIR1); they are not measurements of a real
        surface.
        """
        snow_green, snow_nir, snow_swir1 = 7000.0, 5500.0, 600.0
        snow_ndwi = ndwi(np.array([snow_green]), np.array([snow_nir]))[0]
        snow_mndwi = mndwi(np.array([snow_green]), np.array([snow_swir1]))[0]

        assert snow_ndwi > 0.0
        assert snow_mndwi > snow_ndwi  # MNDWI is the worse of the two for snow


# --------------------------------------------------------------------------- #
# Otsu
# --------------------------------------------------------------------------- #


@pytest.mark.synthetic
class TestOtsu:
    def bimodal_sample(self, seed: int = 1) -> np.ndarray:
        """Two well-separated Gaussians, 20% in the low mode."""
        rng = np.random.default_rng(seed)
        low = rng.normal(-20.0, 1.0, size=2000)
        high = rng.normal(-8.0, 1.5, size=8000)
        return np.concatenate([low, high])

    def test_threshold_falls_between_the_two_modes(self) -> None:
        threshold = otsu_threshold(self.bimodal_sample())
        assert -20.0 < threshold < -8.0

    def test_matches_scikit_image(self) -> None:
        """Cross-check the hand-written implementation against the reference."""
        skimage_filters = pytest.importorskip("skimage.filters")
        samples = self.bimodal_sample(seed=7)
        bins = 256
        ours = otsu_threshold(samples, bins=bins)
        theirs = float(skimage_filters.threshold_otsu(samples, nbins=bins))
        bin_width = float(np.ptp(samples)) / bins
        assert abs(ours - theirs) <= bin_width

    def test_all_identical_values_is_refused(self) -> None:
        with pytest.raises(ValueError, match="no between-class variance"):
            otsu_threshold(np.full(100, -12.0))

    def test_no_finite_samples_is_refused(self) -> None:
        with pytest.raises(ValueError, match="no finite samples"):
            otsu_threshold(np.full(10, np.nan))

    def test_search_range_excludes_outliers(self) -> None:
        samples = np.concatenate([self.bimodal_sample(), np.full(50, 1e6)])
        threshold = otsu_threshold(samples, value_range=(-35.0, 5.0))
        assert -20.0 < threshold < -8.0

    def test_search_range_emptying_the_sample_is_refused(self) -> None:
        with pytest.raises(ValueError, match="inside the search range"):
            otsu_threshold(np.full(10, 100.0), value_range=(-35.0, 5.0))


# --------------------------------------------------------------------------- #
# The bimodality guard -- Otsu always returns a number; this says whether to
# believe it.
# --------------------------------------------------------------------------- #


@pytest.mark.synthetic
class TestBimodalityGuard:
    def test_two_separated_modes_are_bimodal(self) -> None:
        rng = np.random.default_rng(2)
        samples = np.concatenate(
            [rng.normal(-20.0, 1.0, 2000), rng.normal(-8.0, 1.0, 2000)]
        )
        measure = bimodality(samples, otsu_threshold(samples), min_separation=2.0)
        assert measure.is_bimodal
        assert measure.separation > 2.0

    def test_single_mode_is_not_bimodal(self) -> None:
        """The failure Otsu cannot detect on its own (Chini et al. 2017)."""
        rng = np.random.default_rng(3)
        samples = rng.normal(-12.0, 2.0, 10000)
        measure = bimodality(samples, otsu_threshold(samples), min_separation=2.0)
        assert not measure.is_bimodal

    def test_equal_variance_separation_recovers_ashman_equation_3_1(self) -> None:
        """With equal spreads the statistic is (mu2 - mu1) / sigma, recovered.

        The fit must return the *generating* separation, not an inflated one.
        This is what the EM fit buys over hard-splitting the sample at the
        threshold: see :func:`test_hard_splitting_would_inflate_the_statistic`.
        """
        sigma = 1.0
        separation_wanted = 4.0
        rng = np.random.default_rng(4)
        low = rng.normal(0.0, sigma, 200000)
        high = rng.normal(separation_wanted * sigma, sigma, 200000)
        measure = bimodality(np.concatenate([low, high]), separation_wanted / 2.0)

        assert measure.separation == pytest.approx(separation_wanted, rel=0.02)
        assert measure.converged
        assert measure.weight_low == pytest.approx(0.5, abs=0.01)

    def test_hard_splitting_would_inflate_the_statistic(self) -> None:
        """Why the modes are fitted rather than hard-split (docs/methods.md 3.4).

        Splitting a single Gaussian at its own Otsu threshold truncates each
        side, pushing the means apart and shrinking both spreads. The resulting
        statistic clears the >= 2 criterion, which would certify any unimodal
        histogram as bimodal. The fitted statistic does not.
        """
        rng = np.random.default_rng(11)
        samples = rng.normal(-12.0, 2.0, 20000)
        threshold = otsu_threshold(samples)

        low = samples[samples <= threshold]
        high = samples[samples > threshold]
        hard_split = (
            np.sqrt(2.0)
            * abs(high.mean() - low.mean())
            / np.sqrt(low.std() ** 2 + high.std() ** 2)
        )

        assert hard_split > 2.0, "the inflation this design avoids"
        assert bimodality(samples, threshold, min_separation=2.0).separation < 2.0

    def test_empty_side_has_no_separation(self) -> None:
        measure = bimodality(np.array([1.0, 2.0, 3.0]), threshold=10.0)
        assert measure.separation == 0.0
        assert not measure.is_bimodal
        assert measure.count_high == 0

    def test_weight_low_reports_the_minority_share(self) -> None:
        measure = bimodality(np.array([0.0, 0.0, 10.0, 10.0, 10.0, 10.0]), 5.0)
        assert measure.weight_low == pytest.approx(2 / 6)

    def test_describe_names_the_verdict(self) -> None:
        measure = bimodality(np.array([1.0, 1.1, 9.0, 9.1]), 5.0)
        assert "bimodal" in measure.describe()


# --------------------------------------------------------------------------- #
# Tiled Otsu
# --------------------------------------------------------------------------- #


@pytest.mark.synthetic
def water_patch_image(
    shape: tuple[int, int] = (256, 256),
    patch: tuple[slice, slice] = (slice(20, 100), slice(20, 100)),
    *,
    land_db: float = -8.0,
    water_db: float = -20.0,
    noise_db: float = 1.0,
    seed: int = 5,
) -> np.ndarray:
    """Synthetic dB image: a dark patch in one corner, bright land elsewhere."""
    rng = np.random.default_rng(seed)
    image = rng.normal(land_db, noise_db, size=shape)
    image[patch] = rng.normal(water_db, noise_db, size=image[patch].shape)
    return image


@pytest.mark.synthetic
class TestTiledOtsu:
    def test_threshold_found_in_the_tile_containing_both_classes(self) -> None:
        decision = tiled_otsu_threshold(water_patch_image(), tile_px=128)
        assert decision.available
        assert -20.0 < decision.value < -8.0
        assert decision.tiles_accepted >= 1
        assert decision.tiles_tested == 4

    def test_uniform_image_yields_no_threshold_and_says_why(self) -> None:
        """A scene with no water must not produce a water threshold."""
        rng = np.random.default_rng(6)
        decision = tiled_otsu_threshold(
            rng.normal(-8.0, 1.0, size=(256, 256)), tile_px=128
        )
        assert not decision.available
        assert decision.value is None
        assert "separating" in decision.reason
        assert decision.value_type == "unavailable"

    def test_tiles_below_the_valid_fraction_are_skipped(self) -> None:
        image = water_patch_image()
        valid = np.zeros(image.shape, dtype=bool)
        valid[:40, :40] = True  # ~2.4% of the first tile
        decision = tiled_otsu_threshold(
            image, valid=valid, tile_px=128, min_tile_valid_fraction=0.5
        )
        assert not decision.available
        assert decision.tiles_accepted == 0

    def test_min_tiles_can_demand_more_evidence(self) -> None:
        image = water_patch_image()
        permissive = tiled_otsu_threshold(image, tile_px=128, min_tiles=1)
        demanding = tiled_otsu_threshold(image, tile_px=128, min_tiles=4)
        assert permissive.available
        assert not demanding.available
        assert "fewer than the 4 required" in demanding.reason

    def test_small_water_fraction_misplaces_a_global_threshold(self) -> None:
        """The reason tiling exists, stated precisely.

        A 16x16 water patch in a 256x256 image is 0.39% of the pixels. Under
        that imbalance global Otsu still *reports* a separation -- what it gets
        wrong is **where** it puts the threshold: it splits the dominant land
        mode instead of dividing land from water, selecting roughly 40% of the
        image as water. Tiling recovers the true fraction. So the failure mode
        is threshold placement, not the bimodality verdict, and the
        bimodality guard alone would not catch it.
        """
        image = water_patch_image(patch=(slice(0, 16), slice(0, 16)))
        true_fraction = 16 * 16 / image.size

        global_threshold = otsu_threshold(image)
        global_fraction = float((image <= global_threshold).mean())

        tiled = tiled_otsu_threshold(image, tile_px=32, min_separation=2.0)
        assert tiled.available
        assert -20.0 < tiled.value < -8.0
        tiled_fraction = float((image <= tiled.value).mean())

        assert global_fraction > 20 * true_fraction, (
            f"global Otsu selected {global_fraction:.1%} where the truth is "
            f"{true_fraction:.2%}"
        )
        assert tiled_fraction == pytest.approx(true_fraction, abs=0.005)


# --------------------------------------------------------------------------- #
# Configured threshold dispatch
# --------------------------------------------------------------------------- #


@pytest.mark.synthetic
class TestConfiguredThreshold:
    def test_tiled_otsu_is_the_configured_default(self, cfg: Config) -> None:
        assert cfg.detection.water.sar.threshold_method == "tiled_otsu"
        decision = sar_water_threshold(water_patch_image(), cfg)
        assert decision.method == "tiled_otsu"
        assert decision.available

    def test_global_otsu_can_be_selected(self, cfg: Config) -> None:
        tuned = replace_water_config(cfg, sar={"threshold_method": "otsu"})
        decision = sar_water_threshold(water_patch_image(), tuned)
        assert decision.method == "otsu"

    def test_fixed_method_requires_a_value(self, cfg: Config) -> None:
        with pytest.raises(ValueError, match="does not invent"):
            replace_water_config(
                cfg, sar={"threshold_method": "fixed", "fixed_threshold_db": None}
            )

    def test_fixed_threshold_is_labelled_as_not_derived(self, cfg: Config) -> None:
        tuned = replace_water_config(
            cfg, sar={"threshold_method": "fixed", "fixed_threshold_db": -16.0}
        )
        decision = sar_water_threshold(water_patch_image(), tuned)
        assert decision.value == -16.0
        assert "not derived" in decision.reason

    def test_no_fallback_is_invented_when_none_is_configured(self, cfg: Config) -> None:
        """The integrity rule: an unsupported threshold stays unavailable."""
        assert cfg.detection.water.sar.fixed_threshold_db is None
        rng = np.random.default_rng(8)
        decision = sar_water_threshold(rng.normal(-8.0, 1.0, size=(256, 256)), cfg)
        assert not decision.available
        assert decision.value is None

    def test_configured_fallback_is_used_and_disclosed(self, cfg: Config) -> None:
        tuned = replace_water_config(cfg, sar={"fixed_threshold_db": -16.0})
        rng = np.random.default_rng(9)
        decision = sar_water_threshold(rng.normal(-8.0, 1.0, size=(256, 256)), tuned)
        assert decision.available
        assert decision.value == -16.0
        assert decision.method == "tiled_otsu->fixed"
        assert "fell back" in decision.reason


# --------------------------------------------------------------------------- #
# Masks
# --------------------------------------------------------------------------- #


def reflectance_scene(
    shape: tuple[int, int] = (50, 50), water: tuple[slice, slice] | None = None
) -> dict[str, np.ndarray]:
    """Synthetic S2-like reflectance: dry land, with an optional water block.

    Values encode the spectral ordering of the two surfaces (water: low NIR and
    SWIR1; land: higher NIR and SWIR1 than green) and are not measurements.
    """
    green = np.full(shape, 1200.0)
    nir = np.full(shape, 2600.0)
    swir1 = np.full(shape, 2200.0)
    if water is not None:
        green[water] = 900.0
        nir[water] = 200.0
        swir1[water] = 100.0
    return {"green": green, "nir": nir, "swir1": swir1}


@pytest.mark.synthetic
class TestOpticalMask:
    def test_dry_land_gives_no_water(self, cfg: Config) -> None:
        """Required test 1: normal terrain -> no water."""
        scene = reflectance_scene()
        evidence = optical_water_mask(
            scene["green"], scene["nir"], scene["swir1"], cfg
        )
        assert evidence.water_pixels == 0
        assert evidence.valid.all()

    def test_water_block_is_detected(self, cfg: Config) -> None:
        block = (slice(10, 20), slice(10, 20))
        scene = reflectance_scene(water=block)
        evidence = optical_water_mask(
            scene["green"], scene["nir"], scene["swir1"], cfg
        )
        assert evidence.water[block].all()
        assert evidence.water_pixels == 100

    def test_cloud_pixels_are_invalid_not_dry(self, cfg: Config) -> None:
        """A cloudy pixel must never read as an observation of dry land."""
        block = (slice(10, 20), slice(10, 20))
        scene = reflectance_scene(water=block)
        invalid = np.zeros((50, 50), dtype=bool)
        invalid[block] = True  # cloud sitting exactly over the water

        evidence = optical_water_mask(
            scene["green"], scene["nir"], scene["swir1"], cfg, invalid=invalid
        )
        assert evidence.water_pixels == 0
        assert not evidence.valid[block].any()
        # The distinction that matters: not water, and not observed either.
        assert evidence.valid.sum() == 50 * 50 - 100

    def test_each_rule_is_honoured(self, cfg: Config) -> None:
        block = (slice(10, 20), slice(10, 20))
        scene = reflectance_scene(water=block)
        for rule in ("ndwi", "mndwi", "both_and", "both_or"):
            tuned = replace_water_config(cfg, optical={"rule": rule})
            evidence = optical_water_mask(
                scene["green"], scene["nir"], scene["swir1"], tuned
            )
            assert evidence.water[block].all(), rule
            assert rule in evidence.method

    def test_both_indices_are_reported_whichever_rule_runs(self, cfg: Config) -> None:
        scene = reflectance_scene(water=(slice(10, 20), slice(10, 20)))
        evidence = optical_water_mask(
            scene["green"], scene["nir"], scene["swir1"], cfg
        )
        assert "ndwi_water_fraction" in evidence.stats
        assert "mndwi_water_fraction" in evidence.stats

    def test_threshold_is_configurable(self, cfg: Config) -> None:
        scene = reflectance_scene(water=(slice(10, 20), slice(10, 20)))
        strict = replace_water_config(cfg, optical={"mndwi_threshold": 0.99})
        evidence = optical_water_mask(
            scene["green"], scene["nir"], scene["swir1"], strict
        )
        assert evidence.water_pixels == 0

    def test_snow_is_rejected_by_the_nir_screen(self, cfg: Config) -> None:
        """Snow passes both indices but fails the NIR test (Hall et al. 1995)."""
        snow = (slice(25, 35), slice(25, 35))
        water = (slice(10, 20), slice(10, 20))
        scene = reflectance_scene(water=water)
        # Snow: bright green, bright NIR, dark SWIR1 -> high NDWI and MNDWI.
        scene["green"][snow] = 7000.0
        scene["nir"][snow] = 5500.0
        scene["swir1"][snow] = 600.0

        evidence = optical_water_mask(
            scene["green"], scene["nir"], scene["swir1"], cfg
        )
        assert evidence.water[water].all(), "real water must survive the screen"
        assert not evidence.water[snow].any(), "snow must not be called water"

        # The index-only mask -- the Phase 4 baseline -- keeps the snow.
        assert evidence.pre_screen_water is not None
        assert evidence.pre_screen_water[snow].all()
        assert evidence.stats["snow_screened_px"] == 100

    def test_screen_can_be_disabled_leaving_the_index_only_mask(
        self, cfg: Config
    ) -> None:
        snow = (slice(25, 35), slice(25, 35))
        scene = reflectance_scene()
        scene["green"][snow] = 7000.0
        scene["nir"][snow] = 5500.0
        scene["swir1"][snow] = 600.0

        bare = replace_water_config(
            cfg, optical={"snow_screen_nir_max_reflectance": None}
        )
        evidence = optical_water_mask(
            scene["green"], scene["nir"], scene["swir1"], bare
        )
        assert evidence.water[snow].all()
        assert evidence.pre_screen_water is None
        assert "snow_screened_px" not in evidence.stats

    def test_screen_threshold_is_in_reflectance_not_stored_units(
        self, cfg: Config
    ) -> None:
        """A scale mix-up would be a factor of 10 000, so it is pinned.

        The stored NIR of the water block is 200 DN = 0.02 reflectance, well
        under the 0.11 ceiling. Declaring the data to be already in reflectance
        makes that same pixel read as 200.0, so the screen rejects everything --
        which is what a forgotten scale factor would silently do.
        """
        water = (slice(10, 20), slice(10, 20))
        scene = reflectance_scene(water=water)
        assert cfg.detection.water.optical.reflectance_scale == pytest.approx(1e-4)

        correct = optical_water_mask(
            scene["green"], scene["nir"], scene["swir1"], cfg
        )
        assert correct.water[water].all()

        unscaled = replace_water_config(cfg, optical={"reflectance_scale": 1.0})
        wrong = optical_water_mask(
            scene["green"], scene["nir"], scene["swir1"], unscaled
        )
        assert wrong.water_pixels == 0

    def test_terrain_shadow_is_not_an_input(self, cfg: Config) -> None:
        """Phase 3 is shadow-naive by design, so Phase 4 has a baseline.

        Dark shadowed land with low NIR/SWIR1 is expected to be called water
        here. Phase 4's job is to reject it; this test pins the baseline.
        """
        shadowed = (slice(30, 40), slice(30, 40))
        scene = reflectance_scene()
        scene["green"][shadowed] = 300.0
        scene["nir"][shadowed] = 180.0
        scene["swir1"][shadowed] = 120.0

        evidence = optical_water_mask(
            scene["green"], scene["nir"], scene["swir1"], cfg
        )
        assert evidence.water[shadowed].all()


@pytest.mark.synthetic
class TestSARMask:
    def test_dark_backscatter_is_water(self, cfg: Config) -> None:
        image = water_patch_image()
        evidence = sar_water_mask(image, cfg)
        assert evidence.available
        assert evidence.water[30:90, 30:90].mean() > 0.95
        assert evidence.water[150:, 150:].mean() < 0.01

    def test_unavailable_threshold_gives_no_valid_pixels(self, cfg: Config) -> None:
        """No threshold means no evidence -- not an observation of dry land."""
        rng = np.random.default_rng(10)
        evidence = sar_water_mask(rng.normal(-8.0, 1.0, size=(256, 256)), cfg)
        assert not evidence.available
        assert evidence.water_pixels == 0
        assert evidence.valid.sum() == 0
        assert evidence.threshold.value_type == "unavailable"

    def test_invalid_pixels_are_excluded(self, cfg: Config) -> None:
        image = water_patch_image()
        invalid = np.zeros(image.shape, dtype=bool)
        invalid[:, :128] = True  # the half holding the dark patch
        evidence = sar_water_mask(image, cfg, invalid=invalid)
        assert not evidence.water[:, :128].any()

    def test_a_precomputed_decision_is_reused(self, cfg: Config) -> None:
        image = water_patch_image()
        decision = ThresholdDecision(value=-14.0, method="fixture", available=True)
        evidence = sar_water_mask(image, cfg, decision=decision)
        assert evidence.threshold is decision
        assert np.array_equal(evidence.water, image <= -14.0)


# --------------------------------------------------------------------------- #
# Combination
# --------------------------------------------------------------------------- #


@pytest.mark.synthetic
class TestCombine:
    def evidence_pair(self, cfg: Config):
        block = (slice(10, 20), slice(10, 20))
        scene = reflectance_scene(water=block)
        optical = optical_water_mask(
            scene["green"], scene["nir"], scene["swir1"], cfg
        )
        # SAR agreeing on half the block and adding a strip of its own.
        sar_image = np.full((50, 50), -8.0)
        sar_image[10:15, 10:20] = -22.0
        sar_image[40:45, 0:10] = -22.0
        sar = sar_water_mask(
            sar_image,
            cfg,
            decision=ThresholdDecision(value=-15.0, method="fixture", available=True),
        )
        return optical, sar, block

    def test_intersection_is_the_configured_default(self, cfg: Config) -> None:
        """Chosen on measured evidence -- see docs/methods.md 3.5."""
        optical, sar, _ = self.evidence_pair(cfg)
        combined = combine_evidence(optical, sar, cfg)
        assert combined.combine == "intersection"
        assert combined.water_pixels == 50  # only where both sources agree

    def test_union_takes_either_source(self, cfg: Config) -> None:
        optical, sar, _ = self.evidence_pair(cfg)
        tuned = replace_water_config(cfg, combine="union")
        combined = combine_evidence(optical, sar, tuned)
        assert combined.water_pixels == 150  # 100 optical + 50 SAR-only

    def test_single_source_modes(self, cfg: Config) -> None:
        optical, sar, _ = self.evidence_pair(cfg)
        only_optical = combine_evidence(
            optical, sar, replace_water_config(cfg, combine="optical")
        )
        only_sar = combine_evidence(
            optical, sar, replace_water_config(cfg, combine="sar")
        )
        assert only_optical.water_pixels == 100
        assert only_sar.water_pixels == 100

    def test_missing_source_is_an_error_not_a_silent_empty(self, cfg: Config) -> None:
        optical, _, _ = self.evidence_pair(cfg)
        with pytest.raises(ValueError, match="needs sar evidence"):
            combine_evidence(optical, None, cfg)

    def test_intersection_validity_requires_both_sources(self, cfg: Config) -> None:
        """An intersection over a pixel one source never saw would read as dry."""
        optical, sar, _ = self.evidence_pair(cfg)
        blinded = sar_water_mask(
            np.full((50, 50), np.nan),
            cfg,
            decision=ThresholdDecision(value=-15.0, method="fixture", available=True),
        )
        combined = combine_evidence(
            optical, blinded, replace_water_config(cfg, combine="intersection")
        )
        assert combined.valid.sum() == 0
        assert combined.water_pixels == 0

    def test_agreement_is_measured_over_mutually_valid_pixels(
        self, cfg: Config
    ) -> None:
        optical, sar, _ = self.evidence_pair(cfg)
        agreement = combine_evidence(optical, sar, cfg).agreement()
        assert agreement["both_px"] == 50
        assert agreement["optical_only_px"] == 50
        assert agreement["sar_only_px"] == 50
        assert agreement["iou"] == pytest.approx(50 / 150)

    def test_agreement_needs_both_sources(self, cfg: Config) -> None:
        optical, _, _ = self.evidence_pair(cfg)
        detection = combine_evidence(
            optical, None, replace_water_config(cfg, combine="optical")
        )
        assert detection.agreement() is None


# --------------------------------------------------------------------------- #
# Water-body polygons
# --------------------------------------------------------------------------- #


@pytest.mark.synthetic
class TestWaterBodies:
    def square_mask(self, side: int = 10, shape: tuple[int, int] = (50, 50)):
        mask = np.zeros(shape, dtype=bool)
        mask[5 : 5 + side, 5 : 5 + side] = True
        return mask

    def test_area_and_perimeter_are_exact_for_a_square(self) -> None:
        """A 10x10 pixel square at 10 m: 10 000 m^2, 400 m perimeter."""
        bodies = water_bodies(self.square_mask(), TRANSFORM, UTM45N)
        assert len(bodies) == 1
        assert bodies["area_m2"].iloc[0] == pytest.approx(10_000.0)
        assert bodies["perimeter_m"].iloc[0] == pytest.approx(400.0)
        assert bodies["pixel_count"].iloc[0] == 100

    def test_centroid_is_the_square_centre(self) -> None:
        bodies = water_bodies(self.square_mask(), TRANSFORM, UTM45N)
        # Columns 5-14 and rows 5-14 -> centre at pixel edge offset 10.
        assert bodies["centroid_x"].iloc[0] == pytest.approx(450000.0 + 100.0)
        assert bodies["centroid_y"].iloc[0] == pytest.approx(3085000.0 - 100.0)

    def test_geographic_centroid_is_converted_not_computed_in_degrees(self) -> None:
        bodies = water_bodies(self.square_mask(), TRANSFORM, UTM45N)
        lon = bodies["centroid_lon"].iloc[0]
        lat = bodies["centroid_lat"].iloc[0]
        # The transform places the square in eastern Nepal; a loose box is
        # enough to catch a CRS mix-up.
        assert 80.0 < lon < 90.0
        assert 25.0 < lat < 32.0

    def test_geographic_crs_is_refused(self) -> None:
        with pytest.raises(ValueError, match="requires a projected CRS"):
            water_bodies(self.square_mask(), TRANSFORM, "EPSG:4326")

    def test_separate_blocks_are_separate_bodies_sorted_largest_first(self) -> None:
        mask = np.zeros((60, 60), dtype=bool)
        mask[5:15, 5:15] = True  # 100 px
        mask[30:35, 30:35] = True  # 25 px
        bodies = water_bodies(mask, TRANSFORM, UTM45N)
        assert len(bodies) == 2
        assert list(bodies["body_id"]) == [1, 2]
        assert bodies["area_m2"].iloc[0] > bodies["area_m2"].iloc[1]
        assert bodies["pixel_count"].iloc[0] == 100

    def test_min_area_drops_specks(self) -> None:
        mask = np.zeros((60, 60), dtype=bool)
        mask[5:15, 5:15] = True
        mask[30, 30] = True  # a single pixel: 100 m^2
        kept = water_bodies(mask, TRANSFORM, UTM45N, min_area_m2=1000.0)
        assert len(kept) == 1

    def test_everything_dropped_returns_an_empty_frame_with_the_columns(self) -> None:
        mask = np.zeros((20, 20), dtype=bool)
        mask[5, 5] = True
        bodies = water_bodies(mask, TRANSFORM, UTM45N, min_area_m2=1e9)
        assert len(bodies) == 0
        assert "area_m2" in bodies.columns
        assert "geometry" in bodies.columns

    def test_empty_mask_gives_no_bodies(self) -> None:
        bodies = water_bodies(np.zeros((20, 20), dtype=bool), TRANSFORM, UTM45N)
        assert len(bodies) == 0

    def test_island_is_excluded_from_area(self) -> None:
        """A hole in a lake is land, and must not be counted as water."""
        mask = np.zeros((50, 50), dtype=bool)
        mask[5:15, 5:15] = True
        mask[9:11, 9:11] = False  # a 2x2 island
        bodies = water_bodies(mask, TRANSFORM, UTM45N)
        assert bodies["area_m2"].iloc[0] == pytest.approx(10_000.0 - 400.0)

    def test_diagonal_chain_connectivity(self) -> None:
        mask = np.zeros((20, 20), dtype=bool)
        mask[5:7, 5:7] = True
        mask[7:9, 7:9] = True  # touches the first block only at a corner
        assert len(water_bodies(mask, TRANSFORM, UTM45N, connectivity=8)) == 1
        assert len(water_bodies(mask, TRANSFORM, UTM45N, connectivity=4)) == 2

    def test_invalid_connectivity_is_refused(self) -> None:
        with pytest.raises(ValueError, match="connectivity must be 4 or 8"):
            water_bodies(self.square_mask(), TRANSFORM, UTM45N, connectivity=6)

    def test_boundaries_are_the_polygon_outlines(self) -> None:
        bodies = water_bodies(self.square_mask(), TRANSFORM, UTM45N)
        outlined = boundaries(bodies)
        assert outlined.geometry.iloc[0].geom_type in {"LineString", "MultiLineString"}
        assert outlined.geometry.iloc[0].length == pytest.approx(400.0)
        assert list(outlined["body_id"]) == list(bodies["body_id"])


# --------------------------------------------------------------------------- #
# Real imagery -- the Phase 3 gate check
# --------------------------------------------------------------------------- #

STACK = Path("data/processed/stack_tsho_rolpa.tif")


@pytest.fixture(scope="module")
def stack(root: Path):
    """The real Phase 2 stack, as a dict of layers plus its grid."""
    rasterio = pytest.importorskip("rasterio")
    path = root / STACK
    if not path.exists():
        pytest.skip(f"{STACK} not built; run the Phase 2 preprocessing first")
    with rasterio.open(path) as src:
        layers = {
            name: src.read(index + 1).astype(np.float64)
            for index, name in enumerate(src.descriptions)
        }
        return {"layers": layers, "transform": src.transform, "crs": str(src.crs)}


@pytest.mark.realdata
class TestRealStack:
    """Detection over the real Phase 2 stack of Tsho Rolpa.

    Skipped where the stack has not been built. Tsho Rolpa is a documented
    water body: Shrestha & Nakagawa (2014) give a surface area of 1.537 km^2,
    max length 3.45 km and max width 0.5 km (see config.yaml, aoi.source). The
    assertions below are plausibility bounds around that published figure, not
    an accuracy claim -- the published area predates these 2023 scenes, and the
    lake has been growing.
    """

    def test_optical_detects_tsho_rolpa_at_a_plausible_area(
        self, stack, cfg: Config
    ) -> None:
        layers = stack["layers"]
        invalid = (layers["cloud_mask"] > 0) | (layers["cloud_shadow_mask"] > 0)
        evidence = optical_water_mask(
            layers["B3"], layers["B8"], layers["B11"], cfg, invalid=invalid
        )
        bodies = water_bodies(
            evidence.water,
            stack["transform"],
            stack["crs"],
            min_area_m2=cfg.detection.water.polygons.min_area_m2,
            connectivity=cfg.detection.water.polygons.connectivity,
        )
        assert len(bodies) > 0, "no water body found at a documented lake site"

        largest_km2 = bodies["area_m2"].iloc[0] / 1e6
        # Published 1.537 km^2 (2014). A factor-of-two band each way catches a
        # gross failure without asserting an accuracy this test cannot support.
        assert 0.75 < largest_km2 < 3.5, f"largest body {largest_km2:.3f} km^2"

    def test_largest_body_sits_inside_the_dem_water_mask(
        self, stack, cfg: Config
    ) -> None:
        """Cross-check against an independent source: the GLO-30 DEM epoch.

        The lake existed when the DEM was acquired (2011-2014), so the DEM's
        own water-body mask is an independent observation of roughly the same
        surface. This is also the evidence that puts Tsho Rolpa in depth
        Branch B (brief, Section 8).
        """
        rasterio = pytest.importorskip("rasterio")
        wbm_path = Path("data/raw/dem/DEM_GLO30_v02_EPSG32645.tif")
        layers = stack["layers"]

        invalid = (layers["cloud_mask"] > 0) | (layers["cloud_shadow_mask"] > 0)
        evidence = optical_water_mask(
            layers["B3"], layers["B8"], layers["B11"], cfg, invalid=invalid
        )

        from preprocessing.stack import Grid, reproject_to_grid

        grid = Grid(
            crs=stack["crs"],
            transform=stack["transform"],
            width=layers["B3"].shape[1],
            height=layers["B3"].shape[0],
        )
        with rasterio.open(wbm_path) as src:
            try:
                wbm_band = list(src.descriptions).index("WBM") + 1
            except ValueError:
                wbm_band = 3
        wbm = reproject_to_grid(wbm_path, grid, band=wbm_band, categorical=True)

        # GLO-30 WBM: 0 land, 1 ocean, 2 lake, 3 river.
        dem_water = np.isin(np.rint(wbm).astype(int), (1, 2, 3))
        if not dem_water.any():
            pytest.skip("the DEM water-body mask is empty over this AOI")

        overlap = np.count_nonzero(evidence.water & dem_water)
        recall = overlap / np.count_nonzero(dem_water)
        assert recall > 0.5, (
            f"only {recall:.1%} of the DEM-epoch water surface was re-detected"
        )

    def test_sar_threshold_decision_is_recorded_either_way(
        self, stack, cfg: Config
    ) -> None:
        """Whatever the outcome, it must be a documented decision, not a guess."""
        layers = stack["layers"]
        band = "VV_desc" if cfg.detection.water.sar.band == "VV" else "VH_desc"
        decision = sar_water_threshold(layers[band], cfg)
        assert isinstance(decision, ThresholdDecision)
        if decision.available:
            assert decision.value is not None
            assert cfg.detection.water.sar.search_range_db[0] < decision.value
        else:
            assert decision.value is None
            assert decision.reason
        assert decision.value_type in {"derived", "unavailable"}

    def test_shadowed_terrain_produces_false_water_for_phase_4_to_remove(
        self, stack, cfg: Config
    ) -> None:
        """Pins the Phase 3 baseline that Section 7.3 measures Phase 4 against.

        No assertion is made about *how much* false water there is -- only that
        the index-only mask is reported together with how much of it falls in
        terrain shadow, so the reduction has a baseline to be measured from.
        """
        layers = stack["layers"]
        invalid = (layers["cloud_mask"] > 0) | (layers["cloud_shadow_mask"] > 0)
        evidence = optical_water_mask(
            layers["B3"], layers["B8"], layers["B11"], cfg, invalid=invalid
        )
        shadow = layers["terrain_shadow_mask"] > 0
        in_shadow = np.count_nonzero(evidence.water & shadow)
        assert evidence.water_pixels > 0
        assert 0 <= in_shadow <= evidence.water_pixels
