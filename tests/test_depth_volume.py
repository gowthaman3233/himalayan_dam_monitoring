"""Depth and volume under the strict branch rules of brief Section 8.

Synthetic DEMs are hand-made so the right answer is known analytically: a
V-shaped valley of known geometry has a volume that can be computed by hand
and compared. ``TestRealStack`` is marked ``realdata`` and runs required
system test 8 against Tsho Rolpa, whose lake predates the GLO-30 epoch.
"""

from __future__ import annotations

from datetime import date
from pathlib import Path

import numpy as np
import pytest

from analysis.depth_volume import (
    BRANCH_A,
    BRANCH_B,
    BRANCH_C,
    BRANCH_B_REASON,
    VALUE_TYPE_ESTIMATED,
    VALUE_TYPE_UNAVAILABLE,
    decide_branch,
    estimate_depth_volume,
    shoreline_ring,
    water_surface_elevation,
)
from config.schema import Config

CELLSIZE = 10.0
PIXEL_AREA = CELLSIZE * CELLSIZE
STACK = Path("data/processed/stack_tsho_rolpa.tif")

DEM_EPOCH_END = date(2014, 9, 8)  # measured, data/raw/dem/dem_epoch.json


def replace_depth_config(cfg: Config, **overrides) -> Config:
    """A re-validated copy with ``analysis.depth_volume`` patched."""
    data = cfg.model_dump(mode="python")
    section = data["analysis"]["depth_volume"]
    for key in ("shoreline", "branch"):
        patch = overrides.pop(key, None)
        if patch is not None:
            section[key].update(patch)
    section.update(overrides)
    return Config.model_validate(data)


def flat_bottomed_valley(
    shape=(40, 40), rim_m=120.0, floor_m=100.0, floor_half_width=5
):
    """A DEM with a flat floor and walls rising linearly to a rim.

    Rows are uniform, so the cross-section is the same everywhere and the
    filled volume can be worked out by hand.
    """
    cols = np.arange(shape[1])
    centre = shape[1] // 2
    distance = np.abs(cols - centre)
    profile = np.where(
        distance <= floor_half_width,
        floor_m,
        floor_m + (distance - floor_half_width) * 2.0,
    )
    profile = np.minimum(profile, rim_m)
    return np.tile(profile, (shape[0], 1)).astype(float)


def water_up_to(dem: np.ndarray, level_m: float) -> np.ndarray:
    """Everything at or below ``level_m`` is water."""
    return dem <= level_m


# --------------------------------------------------------------------------- #
# Shoreline and WSE
# --------------------------------------------------------------------------- #


@pytest.mark.synthetic
class TestShoreline:
    def test_ring_is_outside_the_water(self) -> None:
        water = np.zeros((20, 20), dtype=bool)
        water[8:12, 8:12] = True
        ring = shoreline_ring(water, 1)
        assert not (ring & water).any()
        assert ring[7, 8] and ring[12, 11]

    def test_ring_width_grows_with_the_buffer(self) -> None:
        water = np.zeros((30, 30), dtype=bool)
        water[13:17, 13:17] = True
        assert shoreline_ring(water, 2).sum() > shoreline_ring(water, 1).sum()

    def test_zero_buffer_is_refused(self) -> None:
        with pytest.raises(ValueError, match="at least one pixel"):
            shoreline_ring(np.ones((4, 4), dtype=bool), 0)

    def test_wse_is_the_median_shoreline_elevation(self, cfg: Config) -> None:
        dem = flat_bottomed_valley()
        water = water_up_to(dem, 110.0)
        wse = water_surface_elevation(dem, water, cfg, cellsize_m=CELLSIZE)
        assert wse is not None
        # The ring sits one pixel outside the 110 m contour, so it is above it.
        assert 110.0 < wse.wse_m <= 120.0
        assert wse.samples > 20

    def test_too_few_samples_gives_no_wse(self, cfg: Config) -> None:
        dem = flat_bottomed_valley(shape=(6, 6))
        water = np.zeros((6, 6), dtype=bool)
        water[2:4, 2:4] = True
        strict = replace_depth_config(cfg, shoreline={"min_samples": 10_000})
        assert water_surface_elevation(dem, water, strict, cellsize_m=CELLSIZE) is None

    def test_statistic_is_configurable(self, cfg: Config) -> None:
        dem = flat_bottomed_valley()
        water = water_up_to(dem, 110.0)
        median = water_surface_elevation(dem, water, cfg, cellsize_m=CELLSIZE)
        lowest = water_surface_elevation(
            dem, water, replace_depth_config(cfg, shoreline={"statistic": "min"}),
            cellsize_m=CELLSIZE,
        )
        assert lowest.wse_m <= median.wse_m

    def test_wider_buffer_biases_the_wse_upward_on_a_slope(self, cfg: Config) -> None:
        """Measured at Tsho Rolpa too: +10.7 m from a 10 m to a 50 m ring."""
        dem = flat_bottomed_valley()
        water = water_up_to(dem, 110.0)
        narrow = water_surface_elevation(
            dem, water, replace_depth_config(cfg, shoreline={"buffer_m": 10.0}),
            cellsize_m=CELLSIZE,
        )
        wide = water_surface_elevation(
            dem, water, replace_depth_config(cfg, shoreline={"buffer_m": 50.0}),
            cellsize_m=CELLSIZE,
        )
        assert wide.wse_m > narrow.wse_m


# --------------------------------------------------------------------------- #
# Branch selection
# --------------------------------------------------------------------------- #


@pytest.mark.synthetic
class TestBranchSelection:
    def test_flat_dem_inside_the_lake_is_branch_b(self, cfg: Config) -> None:
        """The GLO-30 water-flattening signature, whatever the dates say."""
        dem = flat_bottomed_valley()
        water = water_up_to(dem, 110.0)
        dem_flat = dem.copy()
        dem_flat[water] = 110.0  # the DEM recorded the water surface

        wse = water_surface_elevation(dem_flat, water, cfg, cellsize_m=CELLSIZE)
        decision = decide_branch(
            cfg,
            dem_flat,
            water,
            wse=wse,
            dem_epoch_end=DEM_EPOCH_END,
            lake_first_observed=date(2023, 10, 19),  # dates say "after"
        )
        assert decision.branch == BRANCH_B
        assert BRANCH_B_REASON in decision.reason
        assert decision.evidence["dem_std_inside_m"] == pytest.approx(0.0)

    def test_dem_water_mask_overlap_is_branch_b(self, cfg: Config) -> None:
        dem = flat_bottomed_valley()
        water = water_up_to(dem, 110.0)
        wse = water_surface_elevation(dem, water, cfg, cellsize_m=CELLSIZE)
        decision = decide_branch(
            cfg, dem, water, wse=wse, dem_water_mask=water.copy()
        )
        assert decision.branch == BRANCH_B
        assert decision.evidence["dem_water_mask_overlap"] == pytest.approx(1.0)

    def test_lake_postdating_the_dem_is_branch_a(self, cfg: Config) -> None:
        dem = flat_bottomed_valley()
        water = water_up_to(dem, 110.0)
        wse = water_surface_elevation(dem, water, cfg, cellsize_m=CELLSIZE)
        decision = decide_branch(
            cfg,
            dem,
            water,
            wse=wse,
            dem_epoch_end=DEM_EPOCH_END,
            lake_first_observed=date(2023, 10, 19),
        )
        assert decision.branch == BRANCH_A

    def test_lake_predating_the_dem_is_branch_b(self, cfg: Config) -> None:
        dem = flat_bottomed_valley()
        water = water_up_to(dem, 110.0)
        wse = water_surface_elevation(dem, water, cfg, cellsize_m=CELLSIZE)
        decision = decide_branch(
            cfg,
            dem,
            water,
            wse=wse,
            dem_epoch_end=DEM_EPOCH_END,
            lake_first_observed=date(2013, 5, 1),
        )
        assert decision.branch == BRANCH_B

    def test_unusable_observation_is_branch_c(self, cfg: Config) -> None:
        dem = flat_bottomed_valley()
        water = water_up_to(dem, 110.0)
        decision = decide_branch(
            cfg, dem, water, wse=None, observation_is_usable=False
        )
        assert decision.branch == BRANCH_C
        assert "cloud" in decision.reason

    def test_no_shoreline_is_branch_c(self, cfg: Config) -> None:
        dem = flat_bottomed_valley()
        water = water_up_to(dem, 110.0)
        decision = decide_branch(cfg, dem, water, wse=None)
        assert decision.branch == BRANCH_C
        assert "shoreline" in decision.reason

    def test_unknown_dates_without_flatness_is_branch_c(self, cfg: Config) -> None:
        """Not knowing which branch applies is itself an answer."""
        dem = flat_bottomed_valley()
        water = water_up_to(dem, 110.0)
        wse = water_surface_elevation(dem, water, cfg, cellsize_m=CELLSIZE)
        decision = decide_branch(cfg, dem, water, wse=wse)
        assert decision.branch == BRANCH_C
        assert "cannot establish" in decision.reason

    def test_negligible_implied_depth_falls_to_branch_c(self, cfg: Config) -> None:
        """Dates say A, the DEM is not flat, but it sits at the water surface.

        Branch A would be differencing two measurements of the same surface,
        so the result would be noise dressed as a depth. Branch C is the
        honest answer.
        """
        dem = flat_bottomed_valley()
        water = water_up_to(dem, 110.0)

        # Put the lake bed just half a metre below the shoreline the WSE will
        # find, with enough roughness to clear the flatness tolerance.
        probe = water_surface_elevation(dem, water, cfg, cellsize_m=CELLSIZE)
        rng = np.random.default_rng(0)
        shallow = dem.copy()
        shallow[water] = probe.wse_m - 0.5 + rng.normal(0.0, 0.8, int(water.sum()))

        wse = water_surface_elevation(shallow, water, cfg, cellsize_m=CELLSIZE)
        decision = decide_branch(
            cfg,
            shallow,
            water,
            wse=wse,
            dem_epoch_end=DEM_EPOCH_END,
            lake_first_observed=date(2023, 10, 19),
        )
        assert decision.evidence["dem_std_inside_m"] > 0.5, "not caught by flatness"
        assert decision.evidence["implied_mean_depth_m"] < 1.0
        assert decision.branch == BRANCH_C
        assert "measuring noise" in decision.reason


# --------------------------------------------------------------------------- #
# Branch A arithmetic
# --------------------------------------------------------------------------- #


@pytest.mark.synthetic
class TestBranchA:
    def test_volume_matches_a_hand_computed_valley(self, cfg: Config) -> None:
        """A prism of known cross-section: volume checkable by hand.

        The valley floor is at 100 m, 11 pixels wide, with walls rising 2 m
        per pixel. Filling to exactly the shoreline elevation the WSE
        recovers, the volume is the sum of (WSE - DEM) over the wet pixels,
        which the test recomputes independently from the profile.
        """
        dem = flat_bottomed_valley()
        water = water_up_to(dem, 110.0)
        wse = water_surface_elevation(dem, water, cfg, cellsize_m=CELLSIZE)

        estimate = estimate_depth_volume(
            cfg,
            water,
            dem,
            cellsize_m=CELLSIZE,
            pixel_area_m2=PIXEL_AREA,
            dem_epoch_end=DEM_EPOCH_END,
            lake_first_observed=date(2023, 10, 19),
        )
        assert estimate.branch == BRANCH_A
        assert estimate.value_type == VALUE_TYPE_ESTIMATED

        expected = float(np.clip(wse.wse_m - dem[water], 0.0, None).sum() * PIXEL_AREA)
        assert estimate.volume_m3 == pytest.approx(expected)
        assert estimate.max_depth_m == pytest.approx(wse.wse_m - dem.min())

    def test_depth_is_clipped_at_zero(self, cfg: Config) -> None:
        """No pixel may contribute negative water."""
        dem = flat_bottomed_valley()
        water = np.ones(dem.shape, dtype=bool)  # claim the whole scene is water
        estimate = estimate_depth_volume(
            cfg,
            water,
            dem,
            cellsize_m=CELLSIZE,
            pixel_area_m2=PIXEL_AREA,
            dem_epoch_end=DEM_EPOCH_END,
            lake_first_observed=date(2023, 10, 19),
        )
        if estimate.branch == BRANCH_A:
            assert estimate.volume_m3 >= 0.0
            assert estimate.mean_depth_m >= 0.0

    def test_uncertainty_bounds_bracket_the_estimate(self, cfg: Config) -> None:
        dem = flat_bottomed_valley()
        water = water_up_to(dem, 110.0)
        height_error = np.full(dem.shape, 2.0)
        estimate = estimate_depth_volume(
            cfg,
            water,
            dem,
            cellsize_m=CELLSIZE,
            pixel_area_m2=PIXEL_AREA,
            dem_height_error=height_error,
            dem_epoch_end=DEM_EPOCH_END,
            lake_first_observed=date(2023, 10, 19),
        )
        assert estimate.volume_low_m3 <= estimate.volume_m3 <= estimate.volume_high_m3
        assert estimate.volume_low_m3 < estimate.volume_high_m3

    def test_larger_dem_error_widens_the_bounds(self, cfg: Config) -> None:
        dem = flat_bottomed_valley()
        water = water_up_to(dem, 110.0)

        def spread(error_m: float) -> float:
            estimate = estimate_depth_volume(
                cfg,
                water,
                dem,
                cellsize_m=CELLSIZE,
                pixel_area_m2=PIXEL_AREA,
                dem_height_error=np.full(dem.shape, error_m),
                dem_epoch_end=DEM_EPOCH_END,
                lake_first_observed=date(2023, 10, 19),
            )
            return estimate.volume_high_m3 - estimate.volume_low_m3

        assert spread(5.0) > spread(1.0)

    def test_estimate_is_recorded_as_estimated_not_observed(self, cfg: Config) -> None:
        dem = flat_bottomed_valley()
        water = water_up_to(dem, 110.0)
        estimate = estimate_depth_volume(
            cfg,
            water,
            dem,
            cellsize_m=CELLSIZE,
            pixel_area_m2=PIXEL_AREA,
            dem_epoch_end=DEM_EPOCH_END,
            lake_first_observed=date(2023, 10, 19),
        )
        assert estimate.value_type == VALUE_TYPE_ESTIMATED
        assert estimate.value_type != "observed"


# --------------------------------------------------------------------------- #
# Branches B and C emit no numbers
# --------------------------------------------------------------------------- #


@pytest.mark.synthetic
class TestNoUntraceableValues:
    def branch_b_estimate(self, cfg: Config):
        dem = flat_bottomed_valley()
        water = water_up_to(dem, 110.0)
        dem_flat = dem.copy()
        dem_flat[water] = 110.0
        return estimate_depth_volume(
            cfg,
            water,
            dem_flat,
            cellsize_m=CELLSIZE,
            pixel_area_m2=PIXEL_AREA,
            dem_epoch_end=DEM_EPOCH_END,
            lake_first_observed=date(2013, 1, 1),
        )

    def test_branch_b_returns_no_depth_or_volume(self, cfg: Config) -> None:
        estimate = self.branch_b_estimate(cfg)
        assert estimate.branch == BRANCH_B
        assert estimate.value_type == VALUE_TYPE_UNAVAILABLE
        assert estimate.mean_depth_m is None
        assert estimate.max_depth_m is None
        assert estimate.volume_m3 is None
        assert estimate.volume_low_m3 is None
        assert estimate.volume_high_m3 is None

    def test_branch_b_gives_the_reason_the_brief_requires(self, cfg: Config) -> None:
        assert BRANCH_B_REASON in self.branch_b_estimate(cfg).reason

    def test_unavailable_is_not_zero(self, cfg: Config) -> None:
        """A None volume must never be read as "the lake holds no water"."""
        estimate = self.branch_b_estimate(cfg)
        assert estimate.volume_m3 is not 0.0  # noqa: F632 - identity is the point
        assert estimate.volume_m3 is None
        assert not estimate.available

    def test_branch_c_returns_no_numbers(self, cfg: Config) -> None:
        dem = flat_bottomed_valley()
        water = water_up_to(dem, 110.0)
        estimate = estimate_depth_volume(
            cfg,
            water,
            dem,
            cellsize_m=CELLSIZE,
            pixel_area_m2=PIXEL_AREA,
            observation_is_usable=False,
        )
        assert estimate.branch == BRANCH_C
        assert estimate.volume_m3 is None
        assert estimate.reason

    def test_every_result_carries_a_branch(self, cfg: Config) -> None:
        """Section 8: no value may be emitted that is not traceable to one."""
        dem = flat_bottomed_valley()
        water = water_up_to(dem, 110.0)
        cases = [
            dict(dem_epoch_end=DEM_EPOCH_END, lake_first_observed=date(2023, 10, 19)),
            dict(dem_epoch_end=DEM_EPOCH_END, lake_first_observed=date(2013, 1, 1)),
            dict(observation_is_usable=False),
            dict(),
        ]
        for kwargs in cases:
            estimate = estimate_depth_volume(
                cfg, water, dem, cellsize_m=CELLSIZE, pixel_area_m2=PIXEL_AREA, **kwargs
            )
            assert estimate.branch in {BRANCH_A, BRANCH_B, BRANCH_C}
            if estimate.volume_m3 is not None:
                assert estimate.branch == BRANCH_A

    def test_empirical_formula_is_refused_without_approval(self, cfg: Config) -> None:
        """The brief allows one only with approval and a citation."""
        tuned = replace_depth_config(
            cfg, branch_b_empirical_formula="V = 0.1 * A**1.5"
        )
        dem = flat_bottomed_valley()
        water = water_up_to(dem, 110.0)
        with pytest.raises(NotImplementedError, match="no empirical"):
            estimate_depth_volume(
                tuned, water, dem, cellsize_m=CELLSIZE, pixel_area_m2=PIXEL_AREA
            )

    def test_record_maps_to_the_database_columns(self, cfg: Config) -> None:
        """Section 10's depth_volume_estimates table."""
        record = self.branch_b_estimate(cfg).as_record(site_id=1, obs_date="2023-10-19")
        expected = {
            "site_id", "obs_date", "branch", "wse_m", "wse_uncertainty_m",
            "mean_depth_m", "max_depth_m", "volume_m3", "volume_low_m3",
            "volume_high_m3", "value_type", "method", "notes",
        }
        assert set(record) == expected
        assert record["branch"] == BRANCH_B
        assert record["value_type"] == VALUE_TYPE_UNAVAILABLE


# --------------------------------------------------------------------------- #
# Real imagery -- required system test 8
# --------------------------------------------------------------------------- #


@pytest.fixture(scope="module")
def tsho_rolpa(root: Path):
    """The real stack plus the GLO-30 water-body mask, on one grid."""
    rasterio = pytest.importorskip("rasterio")
    path = root / STACK
    if not path.exists():
        pytest.skip(f"{STACK} not built; run the Phase 2 preprocessing first")

    from preprocessing.stack import Grid, reproject_to_grid

    with rasterio.open(path) as src:
        layers = {
            name: src.read(index + 1).astype(np.float64)
            for index, name in enumerate(src.descriptions)
        }
        transform, crs = src.transform, str(src.crs)

    dem_path = root / "data/raw/dem/DEM_GLO30_v02_EPSG32645.tif"
    if not dem_path.exists():
        pytest.skip("the GLO-30 DEM export is not present")
    grid = Grid(
        crs=crs,
        transform=transform,
        width=layers["elevation"].shape[1],
        height=layers["elevation"].shape[0],
    )
    with rasterio.open(dem_path) as src:
        try:
            band = list(src.descriptions).index("WBM") + 1
        except ValueError:
            band = 3
    wbm = reproject_to_grid(dem_path, grid, band=band, categorical=True)
    return {
        "layers": layers,
        "transform": transform,
        "crs": crs,
        "dem_water": np.isin(np.rint(wbm).astype(int), (1, 2, 3)),
    }


@pytest.mark.realdata
class TestRealStack:
    """Required system test 8 — a lake present in the DEM epoch.

    Tsho Rolpa existed long before the GLO-30 acquisition window
    (2011-01-05 to 2014-09-08, measured in data/raw/dem/dem_epoch.json), so
    the DEM recorded its water surface. The answer must be Branch B and
    **never a number**.
    """

    def test_8_lake_in_the_dem_epoch_gives_unavailable_never_a_number(
        self, tsho_rolpa, cfg: Config
    ) -> None:
        layers = tsho_rolpa["layers"]
        estimate = estimate_depth_volume(
            cfg,
            tsho_rolpa["dem_water"],
            layers["elevation"],
            cellsize_m=10.0,
            pixel_area_m2=100.0,
            dem_water_mask=tsho_rolpa["dem_water"],
            dem_height_error=layers["dem_height_error"],
            dem_epoch_end=DEM_EPOCH_END,
            lake_first_observed=date(2023, 10, 19),
        )
        assert estimate.branch == BRANCH_B
        assert estimate.value_type == VALUE_TYPE_UNAVAILABLE
        assert estimate.volume_m3 is None
        assert estimate.mean_depth_m is None
        assert estimate.max_depth_m is None
        assert BRANCH_B_REASON in estimate.reason

    def test_the_dem_is_provably_flattened_over_the_lake(
        self, tsho_rolpa, cfg: Config
    ) -> None:
        """The evidence Branch B rests on, asserted against the real DEM."""
        layers = tsho_rolpa["layers"]
        inside = layers["elevation"][tsho_rolpa["dem_water"]]
        inside = inside[np.isfinite(inside)]
        assert inside.size > 1000
        assert float(inside.std()) < 0.5, "GLO-30 flattens water bodies"

        errors = layers["dem_height_error"][tsho_rolpa["dem_water"]]
        assert float(np.nanmax(errors)) == pytest.approx(0.0), (
            "a zero height-error mask means no measurement was made, not "
            "perfect accuracy"
        )

    def test_dates_alone_would_have_chosen_the_wrong_branch(
        self, tsho_rolpa, cfg: Config
    ) -> None:
        """Why the DEM is tested directly rather than trusting dates.

        The lake was first *observed by this project* in 2023, long after the
        DEM epoch, so a date-only rule would wrongly select Branch A and
        produce a volume. The flatness test overrides it.
        """
        layers = tsho_rolpa["layers"]
        wse = water_surface_elevation(
            layers["elevation"], tsho_rolpa["dem_water"], cfg, cellsize_m=10.0
        )
        decision = decide_branch(
            cfg,
            layers["elevation"],
            tsho_rolpa["dem_water"],
            wse=wse,
            dem_epoch_end=DEM_EPOCH_END,
            lake_first_observed=date(2023, 10, 19),
        )
        assert decision.evidence["lake_postdates_dem"] is True
        assert decision.branch == BRANCH_B

    def test_the_branch_a_formula_here_would_be_buffer_dependent(
        self, tsho_rolpa, cfg: Config
    ) -> None:
        """The concrete harm Branch B prevents.

        Applying the Branch A arithmetic to this Branch B lake gives a
        plausible-looking volume that moves by more than half its own size
        when only the shoreline ring width changes.
        """
        layers = tsho_rolpa["layers"]
        water = tsho_rolpa["dem_water"]
        elevation = layers["elevation"]

        volumes = []
        for buffer_m in (10.0, 30.0, 50.0):
            tuned = replace_depth_config(cfg, shoreline={"buffer_m": buffer_m})
            wse = water_surface_elevation(elevation, water, tuned, cellsize_m=10.0)
            depth = np.clip(wse.wse_m - elevation, 0.0, None)[water]
            volumes.append(float(depth.sum() * 100.0))

        assert all(v > 0 for v in volumes)
        assert max(volumes) / min(volumes) > 1.5, (
            "the point of this test is that the number is unstable"
        )
        # And the system refuses to emit any of them.
        estimate = estimate_depth_volume(
            cfg,
            water,
            elevation,
            cellsize_m=10.0,
            pixel_area_m2=100.0,
            dem_water_mask=water,
            dem_height_error=layers["dem_height_error"],
            dem_epoch_end=DEM_EPOCH_END,
            lake_first_observed=date(2023, 10, 19),
        )
        assert estimate.volume_m3 is None


# --------------------------------------------------------------------------- #
# A lake that is part Branch A and part Branch B
# --------------------------------------------------------------------------- #
@pytest.mark.synthetic
class TestHeightErrorMaskSplit:
    """Section 8's branches are per-lake; a real barrier lake is not.

    A barrier lake routinely floods new ground AND deepens the river it dams.
    Over the new ground the DEM holds the pre-lake surface, so Branch A is
    exactly right. Over the old channel it recorded a WATER SURFACE, so the
    bed is unknown and `WSE - DEM` there measures the RISE in water level, not
    the depth -- yet it was being summed with true depths under one label.

    The GLO-30 height-error mask separates them per pixel: a value of exactly
    zero means no height was measured, which over water is the product stating
    it recorded a surface. On the Baige lake it reads 62.8% zero against 64.2%
    of the lake being pre-existing river -- agreement to within 1.4 points --
    and it was already being read into the evidence and then discarded.
    """

    def _mixed_lake(self):
        """A valley lake whose left half sat under water at DEM time."""
        dem = flat_bottomed_valley()
        water = water_up_to(dem, 110.0)
        hem = np.full(dem.shape, 2.5)      # a real height measurement
        hem[:, : dem.shape[1] // 2] = 0.0  # ...except the old channel
        return dem, water, hem

    def _estimate(self, cfg: Config, dem, water, hem):
        return estimate_depth_volume(
            cfg, water, dem,
            cellsize_m=CELLSIZE, pixel_area_m2=PIXEL_AREA,
            dem_height_error=hem,
            dem_epoch_end=DEM_EPOCH_END,
            lake_first_observed=date(2023, 10, 19),
        )

    def test_the_split_is_applied_and_recorded(self, cfg: Config) -> None:
        dem, water, hem = self._mixed_lake()
        estimate = self._estimate(cfg, dem, water, hem)
        assert estimate.branch == BRANCH_A
        assert estimate.evidence["height_error_split_applied"] is True
        assert estimate.evidence["branch_b_fraction"] > 0.0

    def test_the_volume_is_declared_a_lower_bound(self, cfg: Config) -> None:
        """The omitted part is real water, so the figure understates."""
        dem, water, hem = self._mixed_lake()
        estimate = self._estimate(cfg, dem, water, hem)
        assert estimate.evidence["volume_is_lower_bound"] is True
        assert "LOWER BOUND" in estimate.method
        assert "LOWER BOUND" in estimate.reason

    def test_the_split_volume_is_smaller_than_the_unsplit_one(
        self, cfg: Config
    ) -> None:
        """Proof the split changes the number, not just the wording."""
        dem, water, hem = self._mixed_lake()
        split = self._estimate(cfg, dem, water, hem)
        whole = self._estimate(
            replace_depth_config(cfg, branch={"use_height_error_mask": False}),
            dem, water, hem,
        )
        assert split.volume_m3 < whole.volume_m3
        assert whole.evidence["height_error_split_applied"] is False

    def test_depth_statistics_cover_only_the_measured_part(
        self, cfg: Config
    ) -> None:
        """A mean over pixels with no known bed is not a mean depth."""
        dem, water, hem = self._mixed_lake()
        estimate = self._estimate(cfg, dem, water, hem)
        measured = water & (hem != 0.0)
        assert estimate.evidence["measured_px"] == int(measured.sum())
        assert estimate.evidence["measured_px"] < int(water.sum())

    def test_a_lake_entirely_under_water_at_dem_time_is_branch_b(
        self, cfg: Config
    ) -> None:
        """Zero everywhere means the DEM measured no bed anywhere."""
        dem = flat_bottomed_valley()
        water = water_up_to(dem, 110.0)
        estimate = self._estimate(cfg, dem, water, np.zeros(dem.shape))
        assert estimate.branch == BRANCH_B
        assert estimate.value_type == VALUE_TYPE_UNAVAILABLE
        assert estimate.volume_m3 is None
        assert BRANCH_B_REASON in estimate.reason

    def test_a_trace_of_zero_error_does_not_trigger_a_split(
        self, cfg: Config
    ) -> None:
        """Scattered zeros are mask noise, not a submerged channel.

        Splitting on them would discard good data and label the result a
        lower bound for no reason.
        """
        dem = flat_bottomed_valley()
        water = water_up_to(dem, 110.0)
        hem = np.full(dem.shape, 2.5)
        rows, cols = np.nonzero(water)
        hem[rows[:3], cols[:3]] = 0.0     # a few pixels only
        estimate = self._estimate(cfg, dem, water, hem)
        assert estimate.evidence["height_error_split_applied"] is False
        assert estimate.evidence["volume_is_lower_bound"] is False

    def test_the_split_threshold_is_read_from_config(self, cfg: Config) -> None:
        dem, water, hem = self._mixed_lake()
        # The default splits this lake...
        assert self._estimate(cfg, dem, water, hem).evidence[
            "height_error_split_applied"
        ] is True
        # ...and a threshold above its Branch B fraction does not.
        strict = replace_depth_config(
            cfg, branch={"min_branch_b_fraction_to_split": 0.99}
        )
        assert self._estimate(strict, dem, water, hem).evidence[
            "height_error_split_applied"
        ] is False

    def test_without_a_height_error_mask_nothing_changes(
        self, cfg: Config
    ) -> None:
        """The split must never be inferred from an absent mask."""
        dem = flat_bottomed_valley()
        water = water_up_to(dem, 110.0)
        estimate = estimate_depth_volume(
            cfg, water, dem,
            cellsize_m=CELLSIZE, pixel_area_m2=PIXEL_AREA,
            dem_epoch_end=DEM_EPOCH_END,
            lake_first_observed=date(2023, 10, 19),
        )
        assert estimate.branch == BRANCH_A
        assert estimate.evidence["height_error_split_applied"] is False
