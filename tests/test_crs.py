"""UTM zone derivation and projected-CRS guards.

All coordinates here are SYNTHETIC test inputs chosen to exercise zone
arithmetic and boundaries. The one real-world case (Tsho Rolpa) uses the
published coordinates cited in config/config.yaml.
"""

from __future__ import annotations

import pytest

from utils.crs import (
    NEPAL_UTM_EPSG,
    UTM_LAT_MAX,
    ensure_projected,
    is_projected,
    pixel_area_m2,
    utm_epsg_for_centroid,
    utm_epsg_from_lonlat,
    utm_zone_from_lon,
)

pytestmark = pytest.mark.synthetic


# --------------------------------------------------------------------------- #
# Zone arithmetic
# --------------------------------------------------------------------------- #


@pytest.mark.parametrize(
    ("lon", "expected_zone"),
    [
        (-180.0, 1),
        (-177.0, 1),
        (-174.000001, 1),
        (-174.0, 2),
        (0.0, 31),
        (3.0, 31),
        (78.0, 44),  # zone 44 spans 78-84 E
        (83.999999, 44),
        (84.0, 45),  # zone 45 spans 84-90 E
        (89.999999, 45),
        (90.0, 46),
        (179.999999, 60),
        (180.0, 60),  # folded into zone 60, not a non-existent zone 61
    ],
)
def test_utm_zone_boundaries(lon: float, expected_zone: int) -> None:
    assert utm_zone_from_lon(lon) == expected_zone


@pytest.mark.parametrize("lon", [-180.1, 180.1, 1e9, float("nan"), float("inf")])
def test_invalid_longitude_raises(lon: float) -> None:
    with pytest.raises(ValueError):
        utm_zone_from_lon(lon)


def test_non_numeric_longitude_raises() -> None:
    with pytest.raises(ValueError):
        utm_zone_from_lon("east")  # type: ignore[arg-type]


# --------------------------------------------------------------------------- #
# EPSG selection
# --------------------------------------------------------------------------- #


def test_nepal_spans_zones_44_and_45() -> None:
    """Brief, Section 6: Nepal spans EPSG:32644 and EPSG:32645."""
    assert utm_epsg_from_lonlat(81.0, 29.0) == 32644  # far-western Nepal
    assert utm_epsg_from_lonlat(87.0, 27.0) == 32645  # eastern Nepal
    assert {32644, 32645} == set(NEPAL_UTM_EPSG)


def test_tsho_rolpa_falls_in_zone_45n() -> None:
    """Published position 86.467 E, 27.867 N (see config/config.yaml for sources)."""
    assert utm_epsg_from_lonlat(86.467, 27.867) == 32645


def test_southern_hemisphere_uses_the_327xx_block() -> None:
    assert utm_epsg_from_lonlat(86.467, -27.867) == 32745


def test_equator_counts_as_northern() -> None:
    """lat == 0 is assigned to the northern block; the choice must be explicit."""
    assert utm_epsg_from_lonlat(86.467, 0.0) == 32645


def test_centroid_wrapper_agrees() -> None:
    assert utm_epsg_for_centroid((86.467, 27.867)) == utm_epsg_from_lonlat(
        86.467, 27.867
    )


@pytest.mark.parametrize("lat", [-90.0, -85.0, UTM_LAT_MAX + 0.1, 90.0])
def test_latitudes_outside_the_utm_domain_raise(lat: float) -> None:
    with pytest.raises(ValueError):
        utm_epsg_from_lonlat(86.467, lat)


@pytest.mark.parametrize("lat", [95.0, -120.0])
def test_impossible_latitude_raises(lat: float) -> None:
    with pytest.raises(ValueError, match="range"):
        utm_epsg_from_lonlat(86.467, lat)


# --------------------------------------------------------------------------- #
# Projected-CRS guards (brief, Section 6: never measure in degrees)
# --------------------------------------------------------------------------- #


def test_is_projected() -> None:
    assert is_projected("EPSG:32645") is True
    assert is_projected("EPSG:4326") is False


def test_ensure_projected_accepts_utm() -> None:
    crs = ensure_projected("EPSG:32645", context="area")
    assert crs.is_projected


def test_ensure_projected_refuses_geographic() -> None:
    with pytest.raises(ValueError) as err:
        ensure_projected("EPSG:4326", context="lake area")
    message = str(err.value)
    assert "lake area" in message
    assert "projected" in message


def test_pixel_area_for_a_10m_grid() -> None:
    from affine import Affine

    # North-up 10 m grid: note the negative y-scale, as written by rasterio.
    transform = Affine(10.0, 0.0, 400000.0, 0.0, -10.0, 3100000.0)
    assert pixel_area_m2(transform, "EPSG:32645") == pytest.approx(100.0)


def test_pixel_area_handles_a_rotated_transform() -> None:
    import math

    from affine import Affine

    rotated = Affine.rotation(30.0) @ Affine.scale(10.0, -10.0)
    assert pixel_area_m2(rotated, "EPSG:32645") == pytest.approx(100.0)
    assert math.isfinite(pixel_area_m2(rotated, "EPSG:32645"))


def test_pixel_area_refuses_a_geographic_crs() -> None:
    from affine import Affine

    degrees = Affine(0.0001, 0.0, 86.4, 0.0, -0.0001, 27.9)
    with pytest.raises(ValueError, match="projected"):
        pixel_area_m2(degrees, "EPSG:4326")
