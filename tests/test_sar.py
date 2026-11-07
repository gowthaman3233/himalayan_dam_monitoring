"""Sentinel-1 units, speckle filtering and layover/shadow geometry.

All arrays are SYNTHETIC. The geometry tests use idealised slopes where the
layover and shadow conditions of Kropatsch & Strobl (1990) can be checked
against the inequality directly.
"""

from __future__ import annotations

import numpy as np
import pytest

from config.schema import Config
from preprocessing.sar import (
    GEOMETRY_FORESHORTENING,
    GEOMETRY_LAYOVER,
    GEOMETRY_NOMINAL,
    GEOMETRY_SHADOW,
    SARUnitsError,
    despeckle,
    from_decibels,
    layover_shadow_mask,
    lee_filter,
    local_incidence_angle,
    looks_like_decibels,
    median_filter,
    to_decibels,
    toward_sensor_azimuth,
)

pytestmark = pytest.mark.synthetic

CELLSIZE = 10.0


def tilted(slope_deg: float, azimuth_deg: float, size: int = 60) -> np.ndarray:
    """A plane whose surface rises towards ``azimuth_deg``."""
    rows = np.arange(size, dtype=float)[:, None] * np.ones((1, size))
    cols = np.arange(size, dtype=float)[None, :] * np.ones((size, 1))
    east = cols * CELLSIZE
    north = (size - 1 - rows) * CELLSIZE
    azimuth = np.radians(azimuth_deg)
    distance = east * np.sin(azimuth) + north * np.cos(azimuth)
    return distance * np.tan(np.radians(slope_deg))


# --------------------------------------------------------------------------- #
# Units -- the guard against double conversion
# --------------------------------------------------------------------------- #


def test_linear_power_is_not_mistaken_for_decibels() -> None:
    assert looks_like_decibels(np.array([0.01, 0.2, 1.3, 0.05])) is False


def test_decibel_data_is_recognised() -> None:
    """Real S1 dB backscatter is mostly negative."""
    assert looks_like_decibels(np.array([-18.0, -7.2, -25.1, 2.0])) is True


def test_converting_decibels_again_is_refused() -> None:
    """The Phase 1 finding, enforced: COPERNICUS/S1_GRD is already in dB."""
    already_db = np.array([[-18.0, -7.2], [-25.1, -12.0]])
    with pytest.raises(SARUnitsError, match="already looks like decibels"):
        to_decibels(already_db)


def test_forced_conversion_is_possible_but_explicit() -> None:
    already_db = np.array([[-18.0, -7.2], [-25.1, -12.0]])
    assert np.isfinite(to_decibels(already_db, force=True)).sum() == 0


def test_decibel_round_trip() -> None:
    power = np.array([0.001, 0.01, 0.1, 1.0, 10.0])
    assert np.allclose(from_decibels(to_decibels(power)), power)


def test_known_decibel_values() -> None:
    assert to_decibels(np.array([1.0]))[0] == pytest.approx(0.0)
    assert to_decibels(np.array([10.0]))[0] == pytest.approx(10.0)
    assert to_decibels(np.array([0.1]))[0] == pytest.approx(-10.0)


def test_zero_power_becomes_nan_not_minus_infinity() -> None:
    assert np.isnan(to_decibels(np.array([0.0]))[0])


# --------------------------------------------------------------------------- #
# Speckle filtering (Lee 1980)
# --------------------------------------------------------------------------- #


def test_lee_filter_preserves_a_uniform_field() -> None:
    uniform = np.full((40, 40), 0.25)
    assert np.allclose(lee_filter(uniform, 5, 4.4), 0.25)


def test_lee_filter_reduces_speckle_variance() -> None:
    rng = np.random.default_rng(0)
    # Multiplicative speckle on a constant scene.
    speckled = 0.3 * rng.gamma(shape=4.4, scale=1 / 4.4, size=(120, 120))
    filtered = lee_filter(speckled, 5, 4.4)
    assert filtered.var() < speckled.var()
    assert filtered.mean() == pytest.approx(speckled.mean(), rel=0.05)


def test_lee_filter_preserves_a_strong_edge() -> None:
    """The point of an adaptive filter: smooth flats, keep edges."""
    scene = np.full((60, 60), 0.05)
    scene[:, 30:] = 0.5
    filtered = lee_filter(scene, 5, 4.4)
    # The step is retained far from the boundary.
    assert filtered[30, 10] == pytest.approx(0.05, rel=1e-6)
    assert filtered[30, 50] == pytest.approx(0.5, rel=1e-6)
    assert filtered[30, 50] - filtered[30, 10] > 0.4


def test_lee_filter_rejects_even_windows() -> None:
    with pytest.raises(ValueError, match="odd"):
        lee_filter(np.zeros((10, 10)), 4, 4.4)


def test_lee_filter_rejects_non_positive_looks() -> None:
    with pytest.raises(ValueError, match="equivalent_number_of_looks"):
        lee_filter(np.ones((10, 10)), 5, 0.0)


def test_median_filter_removes_isolated_spikes() -> None:
    scene = np.full((30, 30), -12.0)
    scene[15, 15] = 40.0
    assert median_filter(scene, 5)[15, 15] == pytest.approx(-12.0)


def test_despeckle_honours_the_configured_method(cfg: Config) -> None:
    rng = np.random.default_rng(1)
    backscatter_db = -15.0 + rng.normal(0, 2.0, size=(60, 60))

    assert cfg.preprocessing.sar.speckle_filter == "lee"
    filtered = despeckle(backscatter_db, cfg)
    assert np.nanvar(filtered) < np.nanvar(backscatter_db)
    # Still decibels afterwards, not power.
    assert np.nanmean(filtered) == pytest.approx(-15.0, abs=1.0)


def test_despeckle_none_is_a_passthrough(mutable_config, write_config) -> None:
    from config.loader import load_config

    mutable_config["preprocessing"]["sar"]["speckle_filter"] = "none"
    local = load_config(write_config(mutable_config), load_env=False)
    data = np.array([[-10.0, -20.0], [-30.0, -5.0]])
    assert np.array_equal(despeckle(data, local), data)


def test_even_speckle_window_is_rejected_by_config(
    mutable_config, write_config
) -> None:
    from config.loader import ConfigError, load_config

    mutable_config["preprocessing"]["sar"]["speckle_window_px"] = 4
    with pytest.raises(ConfigError, match="odd"):
        load_config(write_config(mutable_config), load_env=False)


# --------------------------------------------------------------------------- #
# Layover and shadow (Kropatsch & Strobl 1990)
# --------------------------------------------------------------------------- #


def test_flat_ground_is_geometrically_nominal() -> None:
    geometry = layover_shadow_mask(np.zeros((40, 40)), CELLSIZE, 35.0, 270.0)
    assert (geometry.classes == GEOMETRY_NOMINAL).all()
    assert not geometry.unreliable.any()


def test_slope_steeper_than_incidence_is_layover() -> None:
    """alpha >= theta -- the defining layover condition."""
    theta = 35.0
    dem = tilted(slope_deg=50.0, azimuth_deg=270.0)  # rises towards the sensor
    geometry = layover_shadow_mask(dem, CELLSIZE, theta, 270.0)
    assert (geometry.classes[5:-5, 5:-5] == GEOMETRY_LAYOVER).all()


def test_slope_just_below_incidence_is_foreshortening_not_layover() -> None:
    theta = 40.0
    dem = tilted(slope_deg=30.0, azimuth_deg=270.0)
    geometry = layover_shadow_mask(dem, CELLSIZE, theta, 270.0)
    interior = geometry.classes[5:-5, 5:-5]
    assert (interior == GEOMETRY_FORESHORTENING).all()
    assert not geometry.unreliable[5:-5, 5:-5].any()


def test_steep_back_slope_is_radar_shadow() -> None:
    """alpha <= theta - 90 -- the defining shadow condition."""
    theta = 35.0
    # Tilting away from the sensor by more than (90 - 35) = 55 degrees.
    dem = tilted(slope_deg=60.0, azimuth_deg=90.0)
    geometry = layover_shadow_mask(dem, CELLSIZE, theta, 270.0)
    assert (geometry.classes[5:-5, 5:-5] == GEOMETRY_SHADOW).all()


def test_layover_and_shadow_are_both_unreliable() -> None:
    """Brief, Section 7.3: SAR inside these areas must not be trusted."""
    dem = tilted(50.0, 270.0)
    assert layover_shadow_mask(dem, CELLSIZE, 35.0, 270.0).unreliable[5:-5, 5:-5].all()

    dem = tilted(60.0, 90.0)
    assert layover_shadow_mask(dem, CELLSIZE, 35.0, 270.0).unreliable[5:-5, 5:-5].all()


def test_opposite_orbit_passes_distort_opposite_slopes() -> None:
    """Why ascending and descending must stay separate in steep terrain."""
    dem = tilted(slope_deg=50.0, azimuth_deg=270.0)

    from_west = layover_shadow_mask(dem, CELLSIZE, 35.0, 270.0)
    from_east = layover_shadow_mask(dem, CELLSIZE, 35.0, 90.0)

    assert from_west.layover[5:-5, 5:-5].all()
    assert not from_east.layover[5:-5, 5:-5].any()


def test_fractions_sum_to_one() -> None:
    rng = np.random.default_rng(3)
    from scipy import ndimage

    dem = ndimage.gaussian_filter(rng.random((60, 60)) * 900.0, sigma=2)
    fractions = layover_shadow_mask(dem, CELLSIZE, 35.0, 257.5).fractions()
    assert sum(fractions.values()) == pytest.approx(1.0)


def test_incidence_angle_may_be_a_per_pixel_band() -> None:
    """The real `angle` band varies across the swath."""
    dem = tilted(20.0, 270.0)
    angle = np.linspace(30.0, 45.0, dem.shape[1])[None, :] * np.ones_like(dem)
    geometry = layover_shadow_mask(dem, CELLSIZE, angle, 270.0)
    assert geometry.classes.shape == dem.shape


def test_local_incidence_differs_from_ellipsoid_incidence() -> None:
    """Terrain tilts the surface relative to the beam; that drives brightness."""
    dem = tilted(slope_deg=20.0, azimuth_deg=270.0)  # towards the sensor
    local = local_incidence_angle(dem, CELLSIZE, 35.0, 270.0)
    # Tilting towards the sensor reduces the local incidence angle.
    assert local[5:-5, 5:-5].mean() == pytest.approx(15.0, abs=0.5)


def test_flat_ground_local_incidence_equals_the_band() -> None:
    local = local_incidence_angle(np.zeros((30, 30)), CELLSIZE, 38.5, 102.5)
    assert local.mean() == pytest.approx(38.5, abs=1e-6)


# --------------------------------------------------------------------------- #
# Orbit geometry from config
# --------------------------------------------------------------------------- #


def test_orbit_pass_azimuths_are_configured(cfg: Config) -> None:
    assert toward_sensor_azimuth(cfg, "ASCENDING") == pytest.approx(257.5)
    assert toward_sensor_azimuth(cfg, "DESCENDING") == pytest.approx(102.5)


def test_orbit_pass_lookup_is_case_insensitive(cfg: Config) -> None:
    assert toward_sensor_azimuth(cfg, "ascending") == toward_sensor_azimuth(
        cfg, "ASCENDING"
    )


def test_unknown_orbit_pass_is_refused(cfg: Config) -> None:
    with pytest.raises(ValueError, match="orbit pass"):
        toward_sensor_azimuth(cfg, "SIDEWAYS")


def test_ascending_and_descending_look_from_opposite_sides(cfg: Config) -> None:
    """Right-looking geometry: the two passes differ by roughly 180 degrees."""
    separation = abs(
        toward_sensor_azimuth(cfg, "ASCENDING") - toward_sensor_azimuth(cfg, "DESCENDING")
    )
    assert separation == pytest.approx(155.0, abs=30.0)
