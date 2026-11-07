"""Terrain derivatives and the terrain-shadow mask.

Every surface here is SYNTHETIC and chosen so the correct answer is known
analytically — a flat plane, a constant-gradient ramp, a vertical wall — so the
tests check the physics rather than merely re-running the implementation.

The headline case is :func:`test_cast_shadow_length_matches_analytic_solution`:
a wall of height ``h`` under a sun at elevation ``e`` casts a shadow of exactly
``h / tan(e)``.
"""

from __future__ import annotations

import numpy as np
import pytest

from preprocessing.terrain import (
    cast_shadow,
    cos_incidence,
    gradients,
    hillshade,
    slope_aspect,
    solar_vector,
    terrain_shadow_mask,
)

pytestmark = pytest.mark.synthetic

CELLSIZE = 10.0


def ramp(slope_deg: float, size: int = 60, cellsize: float = CELLSIZE) -> np.ndarray:
    """A plane of constant slope whose downslope direction faces SOUTH.

    Row 0 is north and highest, so elevation falls towards increasing row.
    """
    rows = np.arange(size, dtype=float)[:, None] * np.ones((1, size))
    return (size - 1 - rows) * cellsize * np.tan(np.radians(slope_deg))


# --------------------------------------------------------------------------- #
# Gradients, slope and aspect (Horn 1981)
# --------------------------------------------------------------------------- #


def test_flat_ground_has_zero_slope() -> None:
    derived = slope_aspect(np.full((40, 40), 1234.5), CELLSIZE)
    assert derived.slope_deg.max() == pytest.approx(0.0, abs=1e-9)


def test_flat_ground_aspect_is_defined_not_nan() -> None:
    """Aspect is undefined on flat ground; it must be a number, not NaN."""
    derived = slope_aspect(np.full((20, 20), 10.0), CELLSIZE)
    assert np.isfinite(derived.aspect).all()


@pytest.mark.parametrize("slope_deg", [5.0, 15.0, 30.0, 45.0, 60.0])
def test_constant_ramp_recovers_its_slope(slope_deg: float) -> None:
    derived = slope_aspect(ramp(slope_deg), CELLSIZE)
    interior = derived.slope_deg[5:-5, 5:-5]
    assert interior.mean() == pytest.approx(slope_deg, abs=1e-6)


def test_south_facing_ramp_has_aspect_180() -> None:
    """Aspect is the downslope azimuth, clockwise from north."""
    derived = slope_aspect(ramp(30.0), CELLSIZE)
    assert derived.aspect_deg[5:-5, 5:-5].mean() == pytest.approx(180.0, abs=1e-6)


def test_east_facing_ramp_has_aspect_90() -> None:
    cols = np.arange(60, dtype=float)[None, :] * np.ones((60, 1))
    dem = (59 - cols) * CELLSIZE * np.tan(np.radians(20.0))
    derived = slope_aspect(dem, CELLSIZE)
    assert derived.aspect_deg[5:-5, 5:-5].mean() == pytest.approx(90.0, abs=1e-6)


def test_gradient_signs_follow_compass_directions() -> None:
    """Elevation rising to the east gives a positive east gradient."""
    cols = np.arange(30, dtype=float)[None, :] * np.ones((30, 1))
    dz_deast, dz_dnorth = gradients(cols * CELLSIZE, CELLSIZE)
    assert dz_deast[5:-5, 5:-5].mean() == pytest.approx(1.0, abs=1e-9)
    assert dz_dnorth[5:-5, 5:-5].mean() == pytest.approx(0.0, abs=1e-9)


def test_gradients_reject_bad_input() -> None:
    with pytest.raises(ValueError, match="cellsize"):
        gradients(np.zeros((5, 5)), 0.0)
    with pytest.raises(ValueError, match="2-D"):
        gradients(np.zeros((5, 5, 3)), CELLSIZE)


# --------------------------------------------------------------------------- #
# Illumination
# --------------------------------------------------------------------------- #


@pytest.mark.parametrize("zenith", [0.0, 15.0, 30.0, 60.0])
def test_flat_ground_illumination_is_cos_zenith(zenith: float) -> None:
    illumination = cos_incidence(np.full((30, 30), 500.0), CELLSIZE, 135.0, zenith)
    assert illumination.mean() == pytest.approx(np.cos(np.radians(zenith)), abs=1e-9)


def test_slope_facing_the_sun_is_fully_lit() -> None:
    """A 30° south slope under a sun 30° from vertical in the south faces it square on."""
    illumination = cos_incidence(ramp(30.0), CELLSIZE, 180.0, 30.0)
    assert illumination[5:-5, 5:-5].mean() == pytest.approx(1.0, abs=1e-6)


def test_slope_facing_away_is_self_shadowed() -> None:
    """A south-facing slope with the sun low in the north is turned away."""
    illumination = cos_incidence(ramp(40.0), CELLSIZE, 0.0, 70.0)
    assert (illumination[5:-5, 5:-5] < 0).all()


def test_hillshade_clips_but_cos_incidence_does_not() -> None:
    """The signed layer is retained: how far below zero is usable evidence."""
    dem = ramp(40.0)
    assert hillshade(dem, CELLSIZE, 0.0, 70.0).min() == pytest.approx(0.0)
    assert cos_incidence(dem, CELLSIZE, 0.0, 70.0).min() < 0.0


def test_solar_vector_is_a_unit_vector() -> None:
    for azimuth in (0.0, 90.0, 152.565, 270.0):
        for zenith in (0.0, 35.077, 80.0):
            assert np.linalg.norm(solar_vector(azimuth, zenith)) == pytest.approx(1.0)


def test_solar_vector_points_where_expected() -> None:
    # Sun due east, 90° from vertical: unit vector along +east.
    east = solar_vector(90.0, 90.0)
    assert east[0] == pytest.approx(1.0)
    assert east[1] == pytest.approx(0.0, abs=1e-9)
    # Sun overhead: straight up.
    assert solar_vector(123.0, 0.0)[2] == pytest.approx(1.0)


# --------------------------------------------------------------------------- #
# Cast shadow (Dozier & Frew 1990)
# --------------------------------------------------------------------------- #


def test_flat_ground_casts_no_shadow() -> None:
    assert not cast_shadow(np.full((40, 40), 100.0), CELLSIZE, 135.0, 45.0).any()


def test_overhead_sun_casts_no_shadow() -> None:
    """With the sun at the zenith nothing can block anything."""
    dem = np.zeros((30, 60))
    dem[:, :30] = 300.0
    assert not cast_shadow(dem, CELLSIZE, 270.0, 0.0).any()


@pytest.mark.parametrize("sun_elevation_deg", [20.0, 30.0, 45.0, 60.0])
def test_cast_shadow_length_matches_analytic_solution(sun_elevation_deg: float) -> None:
    """A wall of height h casts a shadow of exactly h / tan(elevation).

    This is the test that makes the shadow mask trustworthy: the answer comes
    from geometry, not from the implementation.
    """
    height = 200.0
    dem = np.zeros((40, 200))
    dem[:, :100] = height  # wall occupying the western half

    # Sun in the west, so the shadow falls eastward from the wall edge.
    shadowed = cast_shadow(dem, CELLSIZE, 270.0, 90.0 - sun_elevation_deg)

    measured_m = shadowed[20, 100:].sum() * CELLSIZE
    analytic_m = height / np.tan(np.radians(sun_elevation_deg))

    # Tolerance is one cell: the ray is sampled on a discrete grid.
    assert measured_m == pytest.approx(analytic_m, abs=CELLSIZE)


def test_shadow_falls_away_from_the_sun() -> None:
    """Sun in the east must put the wall's shadow to the west, not the east."""
    dem = np.zeros((40, 200))
    dem[:, 100:] = 200.0  # wall on the EASTERN half

    shadowed = cast_shadow(dem, CELLSIZE, 90.0, 45.0)

    assert shadowed[20, :100].any(), "no shadow west of an eastern wall"
    assert not shadowed[20, 120:].any(), "shadow appeared on the sunlit side"


def test_taller_obstacles_cast_longer_shadows() -> None:
    lengths = []
    for height in (100.0, 200.0, 400.0):
        dem = np.zeros((20, 300))
        dem[:, :50] = height
        lengths.append(cast_shadow(dem, CELLSIZE, 270.0, 45.0)[10, 50:].sum())
    assert lengths[0] < lengths[1] < lengths[2]


def test_sun_below_the_horizon_shadows_everything() -> None:
    shadowed = cast_shadow(np.random.default_rng(0).random((20, 20)) * 100, CELLSIZE, 180.0, 95.0)
    assert shadowed.all()


def test_rays_leaving_the_dem_do_not_create_shadow() -> None:
    """Running off the edge is not evidence that terrain blocks the sun."""
    dem = np.zeros((30, 30))
    assert not cast_shadow(dem, CELLSIZE, 270.0, 20.0).any()


def test_cast_shadow_rejects_bad_step() -> None:
    with pytest.raises(ValueError, match="step_px"):
        cast_shadow(np.zeros((10, 10)), CELLSIZE, 180.0, 45.0, step_px=0.0)


# --------------------------------------------------------------------------- #
# The combined product
# --------------------------------------------------------------------------- #


def test_mask_separates_self_shadow_from_cast_shadow() -> None:
    """The two kinds of shadow are different evidence and stay distinguishable."""
    dem = np.zeros((40, 200))
    dem[:, :100] = 200.0

    product = terrain_shadow_mask(dem, CELLSIZE, 270.0, 45.0)

    assert set(product) == {
        "illumination",
        "hillshade",
        "self_shadow",
        "cast_shadow",
        "terrain_shadow",
    }
    # The flat ground east of the wall is lit but blocked: cast, not self.
    assert product["cast_shadow"][20, 101:120].all()
    assert not product["self_shadow"][20, 101:120].any()


def test_combined_mask_is_the_union_of_its_parts() -> None:
    dem = ramp(35.0)
    dem[20:25, 20:25] += 300.0
    product = terrain_shadow_mask(dem, CELLSIZE, 200.0, 60.0)
    expected = product["self_shadow"] | product["cast_shadow"]
    assert np.array_equal(product["terrain_shadow"], expected)


def test_hillshade_and_illumination_agree_where_lit() -> None:
    product = terrain_shadow_mask(ramp(20.0), CELLSIZE, 180.0, 30.0)
    lit = product["illumination"] > 0
    assert np.allclose(product["hillshade"][lit], product["illumination"][lit])


def test_a_lit_scene_has_little_shadow_and_a_low_sun_has_much() -> None:
    """Sanity: shadow fraction must rise as the sun drops."""
    rng = np.random.default_rng(42)
    from scipy import ndimage

    dem = ndimage.gaussian_filter(rng.random((80, 80)) * 800.0, sigma=3)

    high_sun = terrain_shadow_mask(dem, CELLSIZE, 180.0, 20.0)["terrain_shadow"].mean()
    low_sun = terrain_shadow_mask(dem, CELLSIZE, 180.0, 80.0)["terrain_shadow"].mean()
    assert low_sun > high_sun
