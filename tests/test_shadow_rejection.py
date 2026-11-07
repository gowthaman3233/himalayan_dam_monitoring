"""Shadow-rejection fusion: the three Section 7.3 rules, and what they cost.

Arrays built here are SYNTHETIC (brief, Section 2) and are constructed so the
expected verdict follows from the physics being encoded, not from a tuned
weight. ``TestRealStack`` is marked ``realdata`` and runs over the Phase 2
stack of Tsho Rolpa, skipping when it is absent.
"""

from __future__ import annotations

from pathlib import Path

import numpy as np
import pytest

from config.schema import Config
from detection.shadow_rejection import (
    CLASS_LAND,
    CLASS_TERRAIN_SHADOW,
    CLASS_UNCLASSIFIED,
    CLASS_WATER,
    OPTICAL_TERMS,
    false_water_reduction,
    fuse,
    soft_support,
)
from detection.water import optical_water_mask

STACK = Path("data/processed/stack_tsho_rolpa.tif")


def replace_shadow_config(cfg: Config, **overrides) -> Config:
    """A re-validated copy of ``cfg`` with ``detection.shadow_rejection`` patched."""
    data = cfg.model_dump(mode="python")
    section = data["detection"]["shadow_rejection"]
    for key in ("membership", "weights"):
        patch = overrides.pop(key, None)
        if patch is not None:
            for name, value in patch.items():
                if isinstance(value, dict):
                    section[key][name].update(value)
                else:
                    section[key][name] = value
    section.update(overrides)
    return Config.model_validate(data)


def scene(shape=(4, 4), **layers) -> dict[str, np.ndarray]:
    """Uniform synthetic evidence layers, overridden per keyword.

    Defaults describe ordinary sunlit mountain land: a steep, well-illuminated,
    bright, radar-bright, non-shadowed slope with a negative water index.
    """
    defaults = {
        "water_index": -0.4,
        "nir_reflectance": 0.30,
        "slope_deg": 35.0,
        "illumination": 0.80,
        "terrain_shadow": False,
        "sar_db": -8.0,
    }
    defaults.update(layers)
    out = {}
    for name, value in defaults.items():
        dtype = bool if isinstance(value, bool) else float
        out[name] = np.full(shape, value, dtype=dtype)
    return out


# --------------------------------------------------------------------------- #
# Membership
# --------------------------------------------------------------------------- #


@pytest.mark.synthetic
class TestSoftSupport:
    def test_support_is_zero_at_the_midpoint(self) -> None:
        """A cited mask threshold keeps its meaning as the crossing point."""
        value = soft_support(np.array([10.0]), 10.0, 4.0, below_is_positive=True)
        assert value[0] == pytest.approx(0.0)

    def test_below_is_positive_direction(self) -> None:
        flat = soft_support(np.array([0.0]), 10.0, 4.0, below_is_positive=True)
        steep = soft_support(np.array([60.0]), 10.0, 4.0, below_is_positive=True)
        assert flat[0] > 0.0
        assert steep[0] < 0.0

    def test_above_is_positive_direction(self) -> None:
        wet = soft_support(np.array([0.6]), 0.0, 0.15, below_is_positive=False)
        dry = soft_support(np.array([-0.6]), 0.0, 0.15, below_is_positive=False)
        assert wet[0] > 0.0
        assert dry[0] < 0.0

    def test_support_is_bounded(self) -> None:
        values = soft_support(
            np.array([-1e6, 0.0, 1e6]), 10.0, 4.0, below_is_positive=True
        )
        assert np.all(values >= -1.0) and np.all(values <= 1.0)

    def test_nan_gives_no_support_rather_than_evidence_against(self) -> None:
        value = soft_support(np.array([np.nan]), 10.0, 4.0, below_is_positive=True)
        assert value[0] == 0.0

    def test_softness_must_be_positive(self) -> None:
        with pytest.raises(ValueError, match="softness must be positive"):
            soft_support(np.array([1.0]), 0.0, 0.0, below_is_positive=True)


# --------------------------------------------------------------------------- #
# The three rules of brief Section 7.3
# --------------------------------------------------------------------------- #


@pytest.mark.synthetic
class TestSection73Rules:
    """Each rule must fall out of the fusion, not be special-cased."""

    def shadowed_dark_pixel(self, **overrides) -> dict[str, np.ndarray]:
        """Dark optical pixel inside terrain shadow, on steep ground.

        A shadowed rock face: the water indices read positive (this is exactly
        the false water Phase 3 produces) and NIR is low because it is dark.
        """
        base = {
            "water_index": 0.25,
            "nir_reflectance": 0.06,
            "slope_deg": 52.0,
            "illumination": 0.05,
            "terrain_shadow": True,
        }
        base.update(overrides)
        return scene(**base)

    def test_rule_1_sar_not_water_like_gives_shadow(self, cfg: Config) -> None:
        """Dark + in terrain shadow + SAR NOT water-like -> shadow."""
        layers = self.shadowed_dark_pixel(sar_db=-5.0)  # bright: not water
        result = fuse(cfg, sar_threshold_db=-16.0, **layers)
        assert result.classification[0, 0] == CLASS_TERRAIN_SHADOW
        assert result.p_terrain_shadow[0, 0] > result.p_water[0, 0]

    def test_rule_2_sar_water_like_gives_water(self, cfg: Config) -> None:
        """Dark + in terrain shadow + SAR water-like (reliable) -> water.

        The shadow mask is still set, and the pixel is still steep. What flips
        the verdict is that SAR determines the material, which both supports
        water and discounts "shadow, material indeterminate".
        """
        layers = self.shadowed_dark_pixel(sar_db=-22.0)  # dark: water-like
        result = fuse(cfg, sar_threshold_db=-16.0, **layers)
        assert result.classification[0, 0] == CLASS_WATER
        assert result.p_water[0, 0] > result.p_terrain_shadow[0, 0]

    def test_rule_2_and_1_differ_only_in_the_sar_evidence(self, cfg: Config) -> None:
        """The two verdicts must be driven by SAR alone, nothing else."""
        water_like = fuse(
            cfg, sar_threshold_db=-16.0, **self.shadowed_dark_pixel(sar_db=-22.0)
        )
        not_water_like = fuse(
            cfg, sar_threshold_db=-16.0, **self.shadowed_dark_pixel(sar_db=-5.0)
        )
        assert water_like.classification[0, 0] == CLASS_WATER
        assert not_water_like.classification[0, 0] == CLASS_TERRAIN_SHADOW

    def test_rule_3_sar_inside_layover_shadow_is_withdrawn(self, cfg: Config) -> None:
        """SAR water-like but inside layover/shadow -> defer to optical.

        The SAR evidence is withdrawn rather than downweighted, so the same
        water-like backscatter that produced water in rule 2 no longer does.
        """
        layers = self.shadowed_dark_pixel(sar_db=-22.0)
        unreliable = np.ones(layers["sar_db"].shape, dtype=bool)
        result = fuse(cfg, sar_threshold_db=-16.0, sar_unreliable=unreliable, **layers)

        assert not result.terms["sar_backscatter"].available[0, 0]
        assert result.classification[0, 0] == CLASS_TERRAIN_SHADOW
        assert result.reasons["sar_deferred_to_optical"][0, 0]

    def test_rule_3_defers_to_optical_when_optical_is_decisive(
        self, cfg: Config
    ) -> None:
        """"Defer to optical" means optical decides, not that water is refused.

        Same gated SAR, but now the optical and terrain evidence describe a
        lake: flat, dark in NIR, strongly positive index.
        """
        layers = scene(
            water_index=0.7,
            nir_reflectance=0.04,
            slope_deg=1.0,
            illumination=0.05,
            terrain_shadow=True,
            sar_db=-22.0,
        )
        unreliable = np.ones(layers["sar_db"].shape, dtype=bool)
        result = fuse(cfg, sar_threshold_db=-16.0, sar_unreliable=unreliable, **layers)
        assert result.classification[0, 0] == CLASS_WATER

    def test_trusting_sar_in_layover_shadow_is_configurable(self, cfg: Config) -> None:
        layers = self.shadowed_dark_pixel(sar_db=-22.0)
        unreliable = np.ones(layers["sar_db"].shape, dtype=bool)
        trusting = replace_shadow_config(cfg, trust_sar_in_layover_shadow=True)
        result = fuse(
            trusting, sar_threshold_db=-16.0, sar_unreliable=unreliable, **layers
        )
        assert result.terms["sar_backscatter"].available[0, 0]
        assert result.classification[0, 0] == CLASS_WATER


# --------------------------------------------------------------------------- #
# Required system tests 1-3 (brief, Section 13), at unit level
# --------------------------------------------------------------------------- #


@pytest.mark.synthetic
class TestRequiredScenarios:
    def test_1_normal_mountain_terrain_has_no_water(self, cfg: Config) -> None:
        result = fuse(cfg, sar_threshold_db=-16.0, **scene())
        assert result.classification[0, 0] == CLASS_LAND
        assert not result.water.any()

    def test_2_deep_shadowed_valley_with_no_lake_is_shadow_not_water(
        self, cfg: Config
    ) -> None:
        """Required test 2. The headline failure this project exists to fix."""
        layers = scene(
            water_index=0.3,  # the index is fooled
            nir_reflectance=0.05,  # and it is genuinely dark
            slope_deg=55.0,
            illumination=0.02,
            terrain_shadow=True,
            sar_db=-7.0,  # but SAR says it is not water
        )
        result = fuse(cfg, sar_threshold_db=-16.0, **layers)
        assert result.classification[0, 0] == CLASS_TERRAIN_SHADOW
        assert not result.water[0, 0]

    def test_3_known_lake_in_a_shadowed_valley_is_water(self, cfg: Config) -> None:
        """Required test 3. The reduction must not be bought by deleting lakes."""
        layers = scene(
            water_index=0.65,
            nir_reflectance=0.05,
            slope_deg=0.5,
            illumination=0.05,  # in shadow
            terrain_shadow=True,
            sar_db=-21.0,
        )
        result = fuse(cfg, sar_threshold_db=-16.0, **layers)
        assert result.classification[0, 0] == CLASS_WATER
        assert result.water[0, 0]

    def test_snow_is_not_water(self, cfg: Config) -> None:
        """Bright NIR and a positive MNDWI: the Phase 3 failure mode."""
        layers = scene(
            water_index=0.6,  # MNDWI is high for snow -- it is NDSI
            nir_reflectance=0.55,  # but snow is bright in NIR
            slope_deg=30.0,
            illumination=0.9,
            terrain_shadow=False,
            sar_db=-9.0,
        )
        result = fuse(cfg, sar_threshold_db=-16.0, **layers)
        assert result.classification[0, 0] != CLASS_WATER


# --------------------------------------------------------------------------- #
# Evidence handling
# --------------------------------------------------------------------------- #


@pytest.mark.synthetic
class TestEvidenceHandling:
    def test_slope_is_available_under_cloud(self, cfg: Config) -> None:
        """The DEM does not stop working because the sky is cloudy."""
        layers = scene()
        invalid = np.ones(layers["slope_deg"].shape, dtype=bool)
        result = fuse(cfg, sar_threshold_db=-16.0, optical_invalid=invalid, **layers)
        assert result.terms["slope"].available.all()
        assert not result.terms["water_index"].available.any()
        assert not result.terms["nir"].available.any()

    def test_a_pixel_with_no_evidence_is_unclassified_not_land(
        self, cfg: Config
    ) -> None:
        """The distinction the brief's gap handling rests on."""
        shape = (3, 3)
        invalid = np.ones(shape, dtype=bool)
        result = fuse(
            cfg,
            water_index=np.full(shape, 0.5),
            nir_reflectance=np.full(shape, 0.05),
            optical_invalid=invalid,
        )
        assert (result.classification == CLASS_UNCLASSIFIED).all()
        assert not result.valid.any()
        assert np.isnan(result.p_water).all()

    def test_probabilities_sum_to_one_where_valid(self, cfg: Config) -> None:
        result = fuse(cfg, sar_threshold_db=-16.0, **scene())
        total = result.p_water + result.p_terrain_shadow + result.p_land
        assert np.allclose(total[result.valid], 1.0)

    def test_fusion_runs_with_optical_evidence_alone(self, cfg: Config) -> None:
        shape = (3, 3)
        result = fuse(
            cfg,
            water_index=np.full(shape, 0.6),
            nir_reflectance=np.full(shape, 0.04),
        )
        assert set(result.terms) == {"water_index", "nir"}
        assert result.classification[0, 0] == CLASS_WATER

    def test_fusion_without_any_evidence_is_refused(self, cfg: Config) -> None:
        with pytest.raises(ValueError, match="no evidence"):
            fuse(cfg)

    def test_mismatched_shapes_are_refused(self, cfg: Config) -> None:
        with pytest.raises(ValueError, match="mismatched shapes"):
            fuse(
                cfg,
                water_index=np.zeros((4, 4)),
                nir_reflectance=np.zeros((5, 5)),
            )

    def test_persistence_needs_enough_observations(self, cfg: Config) -> None:
        layers = scene()
        persistence = np.ones(layers["slope_deg"].shape)
        one = fuse(
            cfg,
            sar_threshold_db=-16.0,
            persistence=persistence,
            persistence_observations=1,
            **layers,
        )
        two = fuse(
            cfg,
            sar_threshold_db=-16.0,
            persistence=persistence,
            persistence_observations=2,
            **layers,
        )
        assert "persistence" not in one.terms
        assert one.reasons["persistence_too_few_observations"].all()
        assert "persistence" in two.terms

    def test_zero_weight_drops_a_term_entirely(self, cfg: Config) -> None:
        muted = replace_shadow_config(cfg, weights={"sar_backscatter": 0.0})
        result = fuse(muted, sar_threshold_db=-16.0, **scene())
        assert "sar_backscatter" not in result.terms

    def test_sar_without_any_threshold_is_skipped_not_guessed(
        self, cfg: Config
    ) -> None:
        """No invented dB cutoff, consistent with Phase 3."""
        assert cfg.detection.shadow_rejection.membership.sar.water_max_db is None
        result = fuse(cfg, sar_threshold_db=None, **scene())
        assert "sar_backscatter" not in result.terms
        assert result.reasons["sar_no_threshold"].all()

    def test_explain_lists_every_factor(self, cfg: Config) -> None:
        """Brief, Section 9: a verdict must be able to list its factors."""
        result = fuse(cfg, sar_threshold_db=-16.0, **scene())
        explanation = result.explain(0, 0)
        assert explanation["classification"] == "land"
        assert set(explanation["factors"]) == set(result.terms)
        for factor in explanation["factors"].values():
            assert {"target", "support", "weight", "contribution", "available"} <= set(
                factor
            )

    def test_low_confidence_is_flagged_uncertain(self, cfg: Config) -> None:
        """A pixel with balanced evidence must not be reported as confident."""
        decisive = replace_shadow_config(cfg, min_confidence=0.99)
        result = fuse(decisive, sar_threshold_db=-16.0, **scene())
        assert result.uncertain.all()
        assert not result.water.any()  # uncertain pixels are not confident water


# --------------------------------------------------------------------------- #
# The Section 7.3 report
# --------------------------------------------------------------------------- #


@pytest.mark.synthetic
class TestFalseWaterReduction:
    def test_removal_and_retention_are_both_reported(self, cfg: Config) -> None:
        shape = (1, 4)
        # Two genuine water pixels (flat, dark NIR, SAR-dark) and two shadowed
        # rock faces that the index also called water.
        layers = {
            "water_index": np.array([[0.6, 0.6, 0.3, 0.3]]),
            "nir_reflectance": np.array([[0.04, 0.04, 0.06, 0.06]]),
            "slope_deg": np.array([[0.5, 0.5, 55.0, 55.0]]),
            "illumination": np.array([[0.8, 0.8, 0.03, 0.03]]),
            "terrain_shadow": np.array([[False, False, True, True]]),
            "sar_db": np.array([[-21.0, -21.0, -6.0, -6.0]]),
        }
        result = fuse(cfg, sar_threshold_db=-16.0, **layers)

        baseline = np.ones(shape, dtype=bool)  # the index called everything water
        reference = np.array([[True, True, False, False]])
        report = false_water_reduction(baseline, result, reference_water=reference)

        assert report["baseline_px"] == 4
        assert report["fused_px"] == 2
        assert report["removed_px"] == 2
        assert report["removed_fraction_of_baseline"] == pytest.approx(0.5)
        assert report["reference_retained_fraction"] == pytest.approx(1.0)
        assert report["removed_as_terrain_shadow_px"] == 2

    def test_retention_is_none_without_a_reference(self, cfg: Config) -> None:
        """Removal alone is meaningless, so its absence is explicit."""
        result = fuse(cfg, sar_threshold_db=-16.0, **scene())
        report = false_water_reduction(np.ones((4, 4), dtype=bool), result)
        assert report["reference_retained_fraction"] is None

    def test_an_empty_baseline_does_not_divide_by_zero(self, cfg: Config) -> None:
        result = fuse(cfg, sar_threshold_db=-16.0, **scene())
        report = false_water_reduction(np.zeros((4, 4), dtype=bool), result)
        assert report["removed_fraction_of_baseline"] == 0.0


# --------------------------------------------------------------------------- #
# Real imagery -- the Phase 4 gate check
# --------------------------------------------------------------------------- #


@pytest.fixture(scope="module")
def stack(root: Path):
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


@pytest.fixture(scope="module")
def fused(stack, cfg: Config):
    from detection.water import mndwi

    layers = stack["layers"]
    invalid = (layers["cloud_mask"] > 0) | (layers["cloud_shadow_mask"] > 0)
    geometry = np.rint(layers["sar_geometry_desc"]).astype(int)
    return fuse(
        cfg,
        water_index=mndwi(layers["B3"], layers["B11"]),
        water_index_threshold=cfg.detection.water.optical.mndwi_threshold,
        nir_reflectance=layers["B8"] * cfg.detection.water.optical.reflectance_scale,
        slope_deg=layers["slope_deg"],
        illumination=layers["illumination"],
        terrain_shadow=layers["terrain_shadow_mask"] > 0,
        sar_db=layers["VV_desc"],
        sar_threshold_db=-10.42,  # derived by Phase 3 for this scene
        sar_unreliable=np.isin(geometry, (2, 3)),
        optical_invalid=invalid,
    )


@pytest.mark.realdata
class TestRealStack:
    """Fusion over the real Tsho Rolpa stack.

    Tsho Rolpa is a documented lake (config.yaml ``aoi.source``); the GLO-30
    DEM-epoch water-body mask is an independent observation of its surface,
    used here as a reference rather than as ground truth.
    """

    def dem_water(self, stack, root: Path) -> np.ndarray:
        rasterio = pytest.importorskip("rasterio")
        from preprocessing.stack import Grid, reproject_to_grid

        layers = stack["layers"]
        grid = Grid(
            crs=stack["crs"],
            transform=stack["transform"],
            width=layers["B3"].shape[1],
            height=layers["B3"].shape[0],
        )
        path = root / "data/raw/dem/DEM_GLO30_v02_EPSG32645.tif"
        if not path.exists():
            pytest.skip("the GLO-30 DEM export is not present")
        with rasterio.open(path) as src:
            try:
                band = list(src.descriptions).index("WBM") + 1
            except ValueError:
                band = 3
        wbm = reproject_to_grid(path, grid, band=band, categorical=True)
        return np.isin(np.rint(wbm).astype(int), (1, 2, 3))

    def test_false_water_is_substantially_reduced(
        self, stack, fused, cfg: Config, root: Path
    ) -> None:
        """The Phase 4 gate: quantified reduction on a shadowed valley."""
        layers = stack["layers"]
        invalid = (layers["cloud_mask"] > 0) | (layers["cloud_shadow_mask"] > 0)
        optical = optical_water_mask(
            layers["B3"], layers["B8"], layers["B11"], cfg, invalid=invalid
        )
        report = false_water_reduction(
            optical.pre_screen_water, fused, reference_water=self.dem_water(stack, root)
        )

        assert report["removed_fraction_of_baseline"] > 0.5, (
            "the fusion should remove a large share of index-only false water"
        )
        assert report["reference_retained_fraction"] > 0.8, (
            "and it must not buy that by deleting the known lake"
        )

    def test_the_known_lake_survives_the_fusion(
        self, stack, fused, root: Path
    ) -> None:
        reference = self.dem_water(stack, root)
        retained = (fused.water & reference).sum() / max(reference.sum(), 1)
        assert retained > 0.8, f"only {retained:.1%} of the known lake retained"

    def test_shadowed_steep_terrain_is_not_called_water(self, stack, fused) -> None:
        layers = stack["layers"]
        deep_shadow = (layers["terrain_shadow_mask"] > 0) & (layers["slope_deg"] > 30.0)
        water_rate = fused.water[deep_shadow].mean()
        assert water_rate < 0.02, (
            f"{water_rate:.2%} of steep shadowed terrain still called water"
        )

    def test_every_pixel_has_a_traceable_verdict(self, stack, fused) -> None:
        """No pixel is classified without the evidence behind it being listable."""
        rows, cols = np.nonzero(fused.valid)
        for index in (0, len(rows) // 2, len(rows) - 1):
            explanation = fused.explain(int(rows[index]), int(cols[index]))
            assert explanation["classification"] in {"land", "water", "terrain_shadow"}
            assert explanation["factors"]
            total = (
                explanation["p_water"]
                + explanation["p_terrain_shadow"]
                + explanation["p_land"]
            )
            assert total == pytest.approx(1.0)

    def test_probabilities_are_nan_only_where_invalid(self, fused) -> None:
        assert np.isnan(fused.p_water[~fused.valid]).all()
        assert np.isfinite(fused.p_water[fused.valid]).all()


# --------------------------------------------------------------------------- #
# Asymmetric evidence
# --------------------------------------------------------------------------- #


@pytest.mark.synthetic
class TestSlopeAsymmetry:
    """Flatness is a necessary condition for water, not evidence of it."""

    def test_flat_ground_alone_does_not_make_water(self, cfg: Config) -> None:
        """A flat, dry, bright, radar-bright valley floor is land."""
        layers = scene(
            water_index=-0.3,
            nir_reflectance=0.28,
            slope_deg=0.5,
            illumination=0.85,
            terrain_shadow=False,
            sar_db=-8.0,
        )
        result = fuse(cfg, sar_threshold_db=-16.0, **layers)
        assert result.classification[0, 0] == CLASS_LAND

    def test_steep_ground_still_rules_water_out(self, cfg: Config) -> None:
        """The negative direction keeps its full weight."""
        flat = fuse(cfg, sar_threshold_db=-16.0, **scene(slope_deg=0.5))
        steep = fuse(cfg, sar_threshold_db=-16.0, **scene(slope_deg=60.0))
        assert flat.terms["slope"].effective_support()[0, 0] == pytest.approx(0.0)
        assert steep.terms["slope"].effective_support()[0, 0] < -0.9

    def test_default_is_one_sided(self, cfg: Config) -> None:
        assert cfg.detection.shadow_rejection.membership.slope.flat_support_scale == 0.0

    def test_symmetry_can_be_restored_by_configuration(self, cfg: Config) -> None:
        symmetric = replace_shadow_config(
            cfg, membership={"slope": {"flat_support_scale": 1.0}}
        )
        result = fuse(symmetric, sar_threshold_db=-16.0, **scene(slope_deg=0.5))
        assert result.terms["slope"].effective_support()[0, 0] > 0.9

    def test_asymmetry_does_not_break_a_genuine_lake(self, cfg: Config) -> None:
        """Water is carried by the optical and SAR evidence, not by flatness."""
        layers = scene(
            water_index=0.65,
            nir_reflectance=0.05,
            slope_deg=0.5,
            illumination=0.8,
            terrain_shadow=False,
            sar_db=-21.0,
        )
        result = fuse(cfg, sar_threshold_db=-16.0, **layers)
        assert result.classification[0, 0] == CLASS_WATER


# --------------------------------------------------------------------------- #
# Water needs an optical observation -- Section 7.3's missing rule
# --------------------------------------------------------------------------- #
@pytest.mark.synthetic
class TestWaterRequiresAnOpticalObservation:
    """Radar alone cannot tell water from dry snow or smooth ice.

    A pixel is "valid" if ANY single term applies, and the DEM-derived and SAR
    terms apply everywhere -- so a pixel with no usable optical data still
    received a verdict, decided by radar. Every rule in Section 7.3 begins
    "dark **optical** pixel", and its third rule makes SAR it cannot
    corroborate *uncertain*. The section has no rule for "no optical
    observation at all".

    Measured on Baige 2018, where 40.1% of the scene is optical nodata: the
    fusion reported water at a median 3,822 m on flat high ground, and 88.9%
    of everything it added over the rule-based mask had no optical
    observation. With the gate on, its water mask drops from 31,041 px to
    8,299 px -- which is exactly what the caller previously had to obtain by
    remembering to mask the result itself.
    """

    def _radar_water_no_optical(self, cfg: Config):
        """Flat, radar-dark ground with every optical band unusable."""
        layers = scene(slope_deg=1.0, sar_db=-20.0)
        return fuse(
            cfg,
            water_index=layers["water_index"],
            water_index_threshold=0.0,
            nir_reflectance=layers["nir_reflectance"],
            slope_deg=layers["slope_deg"],
            illumination=layers["illumination"],
            terrain_shadow=layers["terrain_shadow"],
            sar_db=layers["sar_db"],
            sar_threshold_db=-15.0,
            optical_invalid=np.ones(layers["slope_deg"].shape, dtype=bool),
        )

    def test_sar_only_water_is_uncertain_by_default(self, cfg: Config) -> None:
        result = self._radar_water_no_optical(cfg)
        assert not result.water.any(), (
            "water was asserted with no optical observation at all"
        )
        assert result.uncertain.all()

    def test_turning_the_gate_off_restores_the_old_behaviour(
        self, cfg: Config
    ) -> None:
        """Proof the absence above is the gate and not weak evidence."""
        lenient = replace_shadow_config(cfg, require_optical_for_water=False)
        result = self._radar_water_no_optical(lenient)
        assert result.water.any()

    def test_the_reason_mask_is_populated_either_way(self, cfg: Config) -> None:
        """The effect stays measurable from the result, whichever way it is set.

        A caller must be able to tell how much of a water mask rested on radar
        alone, even in a run that chose to allow it.
        """
        for flag in (True, False):
            config = replace_shadow_config(cfg, require_optical_for_water=flag)
            result = self._radar_water_no_optical(config)
            assert "water_without_optical" in result.reasons
            assert result.reasons["water_without_optical"].any()

    def test_water_with_optical_evidence_is_unaffected(self, cfg: Config) -> None:
        """The gate must not cost a genuine detection."""
        layers = scene(
            water_index=0.5, nir_reflectance=0.02, slope_deg=1.0, sar_db=-20.0
        )
        result = fuse(
            cfg,
            water_index=layers["water_index"],
            water_index_threshold=0.0,
            nir_reflectance=layers["nir_reflectance"],
            slope_deg=layers["slope_deg"],
            illumination=layers["illumination"],
            terrain_shadow=layers["terrain_shadow"],
            sar_db=layers["sar_db"],
            sar_threshold_db=-15.0,
        )
        assert result.water.any(), "the gate removed real water"

    def test_only_the_optical_terms_count_as_an_observation(self) -> None:
        """The DEM-derived terms apply everywhere and so cannot qualify."""
        assert set(OPTICAL_TERMS) == {"water_index", "nir"}
        for name in ("slope", "illumination", "terrain_shadow_mask",
                     "sar_backscatter", "persistence"):
            assert name not in OPTICAL_TERMS

    def test_partial_optical_coverage_keeps_the_covered_pixels(
        self, cfg: Config
    ) -> None:
        """Half a scene unusable must not cost the half that is usable."""
        shape = (4, 4)
        layers = scene(
            shape, water_index=0.5, nir_reflectance=0.02, slope_deg=1.0,
            sar_db=-20.0,
        )
        invalid = np.zeros(shape, dtype=bool)
        invalid[:2, :] = True        # top half has no optical observation
        result = fuse(
            cfg,
            water_index=layers["water_index"],
            water_index_threshold=0.0,
            nir_reflectance=layers["nir_reflectance"],
            slope_deg=layers["slope_deg"],
            illumination=layers["illumination"],
            terrain_shadow=layers["terrain_shadow"],
            sar_db=layers["sar_db"],
            sar_threshold_db=-15.0,
            optical_invalid=invalid,
        )
        assert not result.water[:2, :].any(), "no-optical half was called water"
        assert result.water[2:, :].all(), "observed half lost its water"
