"""Coordinate reference system helpers.

Brief, Section 6: the projection is *derived* from the AOI centroid, never
assumed, and every area or volume is computed in that projected CRS -- never in
degrees. The guards here exist so that a geographic CRS cannot silently reach an
area calculation.

The zone arithmetic is deliberately dependency-free (pure stdlib) so that it can
be unit-tested without GDAL/PROJ installed. Anything needing PROJ imports it
lazily.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:  # pragma: no cover
    from pyproj import CRS

# EPSG:326xx = WGS 84 / UTM zone xx N; EPSG:327xx = ... zone xx S.
UTM_NORTH_EPSG_BASE = 32600
UTM_SOUTH_EPSG_BASE = 32700

UTM_ZONE_WIDTH_DEG = 6.0
UTM_MIN_ZONE = 1
UTM_MAX_ZONE = 60

# UTM is defined between 80 deg S and 84 deg N; outside that range a polar
# stereographic projection (UPS) is required instead.
UTM_LAT_MIN = -80.0
UTM_LAT_MAX = 84.0

#: The two UTM zones spanning Nepal (brief, Section 6). Used by tests and for
#: sanity logging only -- never to constrain the zone actually chosen.
NEPAL_UTM_EPSG = (32644, 32645)


def utm_zone_from_lon(lon: float) -> int:
    """UTM zone number (1-60) containing ``lon``.

    Zone *n* spans ``[-180 + 6(n-1), -180 + 6n)`` degrees. Longitude exactly
    +180 is folded into zone 60 rather than producing a non-existent zone 61.

    Note: this returns the *regular* zone. The Norway/Svalbard irregularities
    (31V/32V and 31X-37X) widen some MGRS grid zones but do not change which
    EPSG UTM code to reproject into, so they are not special-cased here.
    """
    if not _finite(lon):
        raise ValueError(f"longitude must be a finite number, got {lon!r}")
    if not -180.0 <= lon <= 180.0:
        raise ValueError(f"longitude out of range [-180, 180]: {lon}")

    zone = int((lon + 180.0) // UTM_ZONE_WIDTH_DEG) + 1
    return min(zone, UTM_MAX_ZONE)


def utm_epsg_from_lonlat(lon: float, lat: float) -> int:
    """EPSG code of the WGS84 UTM zone containing ``(lon, lat)``.

    Example: Tsho Rolpa at 86.467 E, 27.867 N falls in zone 45 N -> EPSG:32645.
    """
    if not _finite(lat):
        raise ValueError(f"latitude must be a finite number, got {lat!r}")
    if not -90.0 <= lat <= 90.0:
        raise ValueError(f"latitude out of range [-90, 90]: {lat}")
    if not UTM_LAT_MIN <= lat <= UTM_LAT_MAX:
        raise ValueError(
            f"latitude {lat} is outside the UTM domain "
            f"[{UTM_LAT_MIN}, {UTM_LAT_MAX}]; a polar projection is required"
        )

    zone = utm_zone_from_lon(lon)
    base = UTM_NORTH_EPSG_BASE if lat >= 0.0 else UTM_SOUTH_EPSG_BASE
    return base + zone


def utm_epsg_for_centroid(centroid: tuple[float, float]) -> int:
    """Convenience wrapper taking a ``(lon, lat)`` tuple."""
    lon, lat = centroid
    return utm_epsg_from_lonlat(lon, lat)


def is_projected(crs: Any) -> bool:
    """True if ``crs`` is a projected (metric) CRS rather than a geographic one."""
    from pyproj import CRS as _CRS

    return bool(_CRS.from_user_input(crs).is_projected)


def ensure_projected(crs: Any, context: str = "this computation") -> "CRS":
    """Return ``crs`` as a :class:`pyproj.CRS`, refusing geographic CRSs.

    Guard for every area/length/volume calculation: a geographic CRS would
    produce numbers in square degrees, which are meaningless and vary with
    latitude (brief, Section 6).
    """
    from pyproj import CRS as _CRS

    parsed = _CRS.from_user_input(crs)
    if not parsed.is_projected:
        raise ValueError(
            f"{context} requires a projected CRS, but got the geographic CRS "
            f"{parsed.to_string()!r}. Reproject to the AOI's UTM zone first "
            f"(see utils.crs.utm_epsg_from_lonlat)."
        )
    return parsed


def pixel_area_m2(transform: Any, crs: Any) -> float:
    """Area of one pixel in square metres, from an affine transform.

    ``transform`` is an ``affine.Affine`` (as carried by rasterio). The CRS is
    checked first: a geographic transform would give square degrees.
    """
    ensure_projected(crs, context="pixel area")
    a, b, _, d, e, _ = (
        transform.a,
        transform.b,
        transform.c,
        transform.d,
        transform.e,
        transform.f,
    )
    # |determinant| of the linear part: correct for rotated as well as
    # north-up transforms.
    return abs(a * e - b * d)


def _finite(value: Any) -> bool:
    import math

    try:
        return math.isfinite(float(value))
    except (TypeError, ValueError):
        return False
