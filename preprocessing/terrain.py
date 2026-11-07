"""Terrain derivatives and the terrain-shadow mask.

This module produces the layers the project's core contribution depends on
(brief, Section 7.1): slope, aspect, hillshade/illumination and, most
importantly, a **terrain-shadow mask computed per scene** from the DEM and that
scene's own sun geometry.

Two physically distinct things are both loosely called "shadow", and conflating
them would weaken the whole shadow-rejection argument, so they are kept separate
here and recombined only on request:

* **Self-shadow** (shading): the surface facet itself faces away from the sun,
  i.e. ``cos(incidence) <= 0``. Local geometry only.
* **Cast shadow**: the facet faces the sun, but another landform stands between
  it and the sun. This needs a horizon search along the solar azimuth and is
  what makes deep Himalayan valleys dark even where the slope faces the sun.

``ee.Terrain.hillShadow``, which the brief mentions, computes cast shadow. The
implementation here is local rather than server-side so that it is unit-testable
against synthetic terrain with a known analytic answer, and so that it lands on
exactly the same grid as the rest of the local stack.

**Cloud shadow is not terrain shadow** and is never produced here; it belongs to
:mod:`preprocessing.cloud_mask` (brief, Section 7.1).

References
----------
Horn, B. K. P. (1981). "Hill shading and the reflectance map."
    *Proceedings of the IEEE*, 69(1), 14-47. doi:10.1109/PROC.1981.11918
    -- the 3x3 kernel used for slope and aspect, and the reflectance-map
    formulation of hillshade.
Dozier, J. and Frew, J. (1990). "Rapid calculation of terrain parameters for
    radiation modeling from digital elevation data." *IEEE Transactions on
    Geoscience and Remote Sensing*, 28(5), 963-969.
    -- the horizon-search formulation used for cast shadow.
"""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np

from typing import TYPE_CHECKING

from utils.logging import get_logger

if TYPE_CHECKING:  # pragma: no cover
    from config.schema import Config

log = get_logger(__name__)

# Horn (1981) 3x3 kernels. Applied with *correlation*, not convolution, so the
# kernel is used exactly as written. Row index increases southward, column
# index increases eastward, which is the orientation of a north-up raster.
_HORN_DZ_DCOL = np.array(
    [
        [-1.0, 0.0, 1.0],
        [-2.0, 0.0, 2.0],
        [-1.0, 0.0, 1.0],
    ]
)
_HORN_DZ_DROW = np.array(
    [
        [-1.0, -2.0, -1.0],
        [0.0, 0.0, 0.0],
        [1.0, 2.0, 1.0],
    ]
)
_HORN_NORMALISER = 8.0


@dataclass(frozen=True)
class TerrainDerivatives:
    """Slope/aspect/gradient products on a common grid.

    Angles are in **radians**; use the ``*_deg`` helpers for degrees.
    """

    slope: np.ndarray
    aspect: np.ndarray
    dz_deast: np.ndarray
    dz_dnorth: np.ndarray
    cellsize: float

    @property
    def slope_deg(self) -> np.ndarray:
        return np.degrees(self.slope)

    @property
    def aspect_deg(self) -> np.ndarray:
        """Downslope azimuth in degrees clockwise from north, 0-360."""
        return np.degrees(self.aspect) % 360.0


def gradients(dem: np.ndarray, cellsize: float) -> tuple[np.ndarray, np.ndarray]:
    """East and north elevation gradients, by Horn's (1981) 3x3 kernel.

    Returns ``(dz_deast, dz_dnorth)``, both dimensionless (metres per metre).
    Edges use nearest-value replication, which flattens the one-pixel border
    rather than inventing terrain beyond the DEM.
    """
    from scipy import ndimage

    if cellsize <= 0:
        raise ValueError(f"cellsize must be positive, got {cellsize}")
    if dem.ndim != 2:
        raise ValueError(f"dem must be 2-D, got shape {dem.shape}")

    elevation = np.asarray(dem, dtype=np.float64)
    denominator = _HORN_NORMALISER * cellsize

    dz_dcol = ndimage.correlate(elevation, _HORN_DZ_DCOL, mode="nearest") / denominator
    dz_drow = ndimage.correlate(elevation, _HORN_DZ_DROW, mode="nearest") / denominator

    # Column index increases eastward; row index increases *southward*, so the
    # northward gradient is the negative of the row gradient.
    return dz_dcol, -dz_drow


def slope_aspect(dem: np.ndarray, cellsize: float) -> TerrainDerivatives:
    """Slope and aspect from a DEM (Horn 1981).

    Aspect is the **downslope** azimuth, clockwise from north, which is the
    convention used by GDAL and ESRI. On perfectly flat ground aspect is
    undefined; it is set to 0 there and the caller can identify those cells by
    ``slope == 0``.
    """
    dz_deast, dz_dnorth = gradients(dem, cellsize)

    slope = np.arctan(np.hypot(dz_deast, dz_dnorth))
    # Downslope direction is the negative gradient. atan2(east, north) gives an
    # azimuth measured clockwise from north.
    aspect = np.arctan2(-dz_deast, -dz_dnorth)
    aspect = np.where(slope > 0, aspect, 0.0)

    return TerrainDerivatives(
        slope=slope,
        aspect=aspect,
        dz_deast=dz_deast,
        dz_dnorth=dz_dnorth,
        cellsize=float(cellsize),
    )


def solar_vector(sun_azimuth_deg: float, sun_zenith_deg: float) -> np.ndarray:
    """Unit vector pointing from the surface **towards** the sun.

    Components are ``(east, north, up)``. Azimuth is measured clockwise from
    north, as reported by Sentinel-2's ``MEAN_SOLAR_AZIMUTH_ANGLE``.
    """
    azimuth = np.radians(float(sun_azimuth_deg))
    zenith = np.radians(float(sun_zenith_deg))
    return np.array(
        [
            np.sin(zenith) * np.sin(azimuth),
            np.sin(zenith) * np.cos(azimuth),
            np.cos(zenith),
        ]
    )


def cos_incidence(
    dem: np.ndarray,
    cellsize: float,
    sun_azimuth_deg: float,
    sun_zenith_deg: float,
) -> np.ndarray:
    """Cosine of the solar incidence angle on the surface (Horn 1981).

    This is the continuous **illumination** layer required by the brief,
    Section 7.1, before any clipping. Values run from -1 (facing directly away
    from the sun) through 0 (grazing) to 1 (sun normal to the surface).

    Negative values are *self-shadow*: they are retained rather than clipped,
    because how far below zero a facet lies is information the shadow-rejection
    fusion in Phase 4 can use.
    """
    dz_deast, dz_dnorth = gradients(dem, cellsize)
    sun_east, sun_north, sun_up = solar_vector(sun_azimuth_deg, sun_zenith_deg)

    # The upward surface normal for a height field z(east, north) is
    # (-dz_deast, -dz_dnorth, 1) before normalisation, so the cosine is a
    # per-pixel dot product with the solar vector, divided by the normal's
    # length.
    #
    # Written out elementwise rather than as a stacked array with
    # ``np.linalg.norm`` and ``@``. Both forms are numerically identical, but
    # the stacked one allocates a three-channel copy of the DEM and dispatches
    # a matrix product for what is elementwise arithmetic. On this project's
    # Windows machine that product is also blocked above roughly 300x300x3 --
    # the process dies with no traceback and exit code 0 -- which silently
    # took out every terrain-shadow and Phase 4 fusion call at AOI scale.
    # Elementwise arithmetic needs no BLAS and allocates less.
    dot = -dz_deast * sun_east - dz_dnorth * sun_north + sun_up
    length = np.sqrt(dz_deast * dz_deast + dz_dnorth * dz_dnorth + 1.0)

    return dot / length


def hillshade(
    dem: np.ndarray,
    cellsize: float,
    sun_azimuth_deg: float,
    sun_zenith_deg: float,
    *,
    clip: bool = True,
) -> np.ndarray:
    """Illumination in 0-1 (Horn 1981), ignoring cast shadow.

    With ``clip=True`` self-shadowed facets are floored at 0, which is what a
    cartographic hillshade shows. Use :func:`cos_incidence` for the unclipped
    signed layer.

    This deliberately does **not** account for cast shadow. Combine it with
    :func:`cast_shadow` through :func:`terrain_shadow_mask` for the physical
    answer.
    """
    illumination = cos_incidence(dem, cellsize, sun_azimuth_deg, sun_zenith_deg)
    return np.clip(illumination, 0.0, 1.0) if clip else illumination


def cast_shadow(
    dem: np.ndarray,
    cellsize: float,
    sun_azimuth_deg: float,
    sun_zenith_deg: float,
    *,
    max_distance_m: float | None = None,
    step_px: float = 1.0,
) -> np.ndarray:
    """Boolean mask of pixels where terrain blocks the direct sun.

    Implements the horizon search of Dozier and Frew (1990): march from each
    pixel towards the sun and test whether any terrain along that ray rises
    above the solar elevation line from that pixel.

    A pixel at height ``z0`` is shadowed if, at horizontal distance ``d`` along
    the solar azimuth, the terrain height ``z(d)`` satisfies::

        z(d) - z0 > d * tan(solar_elevation)

    Args:
        max_distance_m: how far to search. ``None`` derives it from the DEM's
            own relief, which is the furthest any terrain in this DEM could
            possibly cast: ``relief / tan(solar_elevation)``. Searching further
            cannot change the result, so this is exact, not an approximation.
        step_px: ray sampling interval in pixels. Values below 1 oversample.

    Returns:
        Boolean array, ``True`` where the direct beam is blocked.
    """
    from scipy import ndimage

    elevation = np.asarray(dem, dtype=np.float64)
    if elevation.ndim != 2:
        raise ValueError(f"dem must be 2-D, got shape {elevation.shape}")
    if step_px <= 0:
        raise ValueError(f"step_px must be positive, got {step_px}")

    zenith = np.radians(float(sun_zenith_deg))
    elevation_angle = np.pi / 2.0 - zenith

    # Sun at or below the horizon: everything is in shadow, and the tangent
    # below would blow up. Answer directly instead.
    if elevation_angle <= 0:
        log.warning(
            "sun zenith %.2f deg is at or below the horizon; the whole scene "
            "is unlit",
            sun_zenith_deg,
        )
        return np.ones_like(elevation, dtype=bool)

    tan_elevation = np.tan(elevation_angle)

    sun = solar_vector(sun_azimuth_deg, sun_zenith_deg)
    # Horizontal step towards the sun, in pixels. Row index increases
    # southward, hence the negated north component.
    horizontal = np.hypot(sun[0], sun[1])
    if horizontal <= 0:
        # Sun exactly overhead: nothing can be cast-shadowed.
        return np.zeros_like(elevation, dtype=bool)

    d_col = (sun[0] / horizontal) * step_px
    d_row = -(sun[1] / horizontal) * step_px

    if max_distance_m is None:
        relief = float(np.nanmax(elevation) - np.nanmin(elevation))
        max_distance_m = relief / tan_elevation if relief > 0 else 0.0

    n_steps = int(np.ceil(max_distance_m / (cellsize * step_px))) if cellsize else 0
    if n_steps <= 0:
        return np.zeros_like(elevation, dtype=bool)

    rows, cols = elevation.shape
    row_idx, col_idx = np.meshgrid(
        np.arange(rows, dtype=np.float64),
        np.arange(cols, dtype=np.float64),
        indexing="ij",
    )

    shadowed = np.zeros(elevation.shape, dtype=bool)
    log.debug(
        "cast shadow: %d step(s) of %.1f px towards azimuth %.2f deg "
        "(solar elevation %.2f deg)",
        n_steps,
        step_px,
        sun_azimuth_deg,
        np.degrees(elevation_angle),
    )

    for step in range(1, n_steps + 1):
        sample_row = row_idx + d_row * step
        sample_col = col_idx + d_col * step

        # Rays leaving the DEM are not evidence of shadow: there is no data to
        # say the terrain rises, so those samples must not set the flag.
        inside = (
            (sample_row >= 0)
            & (sample_row <= rows - 1)
            & (sample_col >= 0)
            & (sample_col <= cols - 1)
        )
        if not inside.any():
            break

        sampled = ndimage.map_coordinates(
            elevation,
            np.stack([sample_row, sample_col]),
            order=1,
            mode="nearest",
        )

        distance = step * step_px * cellsize
        blocks = (sampled - elevation) > (distance * tan_elevation)
        shadowed |= blocks & inside

    return shadowed


def terrain_shadow_mask(
    dem: np.ndarray,
    cellsize: float,
    sun_azimuth_deg: float,
    sun_zenith_deg: float,
    *,
    max_distance_m: float | None = None,
    step_px: float = 1.0,
) -> dict[str, np.ndarray]:
    """The full per-scene terrain-shadow product.

    Returns a dict with:

    ``illumination``
        signed ``cos(incidence)``, the continuous layer (brief, Section 7.1);
    ``hillshade``
        the same clipped to 0-1;
    ``self_shadow``
        facets turned away from the sun;
    ``cast_shadow``
        facets blocked by other terrain;
    ``terrain_shadow``
        either of the two -- the mask the shadow-rejection fusion consumes.

    The components are returned alongside the combined mask on purpose: Phase 4
    treats "dark because the slope tilts away" and "dark because a ridge is in
    the way" as different evidence, and reporting only the union would throw
    that distinction away.
    """
    illumination = cos_incidence(dem, cellsize, sun_azimuth_deg, sun_zenith_deg)
    self_shadow = illumination <= 0.0
    cast = cast_shadow(
        dem,
        cellsize,
        sun_azimuth_deg,
        sun_zenith_deg,
        max_distance_m=max_distance_m,
        step_px=step_px,
    )

    return {
        "illumination": illumination,
        "hillshade": np.clip(illumination, 0.0, 1.0),
        "self_shadow": self_shadow,
        "cast_shadow": cast,
        "terrain_shadow": self_shadow | cast,
    }


def terrain_shadow_for_scene(
    cfg: "Config",
    dem: np.ndarray,
    cellsize: float,
    sun_azimuth_deg: float,
    sun_zenith_deg: float,
) -> dict[str, np.ndarray]:
    """:func:`terrain_shadow_mask` with the ray-search settings from config.

    ``preprocessing.terrain.shadow_ray_step_px`` and ``shadow_max_distance_m``
    had no reader: the function below takes them as arguments with defaults,
    and every caller relied on those defaults, so changing either setting did
    nothing. This is the wiring that makes them real.

    The sun angles stay arguments, not configuration -- they belong to the
    scene, and a per-scene shadow mask computed from a configured angle would
    be wrong for every scene but one (brief, Section 7.1).
    """
    settings = cfg.preprocessing.terrain
    return terrain_shadow_mask(
        dem,
        cellsize,
        sun_azimuth_deg,
        sun_zenith_deg,
        max_distance_m=settings.shadow_max_distance_m,
        step_px=settings.shadow_ray_step_px,
    )


def quicklook_hillshade(
    cfg: "Config", dem: np.ndarray, cellsize: float
) -> np.ndarray:
    """Hillshade under the configured quick-look sun, for visual checks only.

    Explicitly **not** for analysis: the per-scene shadow masks use each
    scene's own sun angles, never these. Named so that a reader cannot mistake
    one for the other.
    """
    settings = cfg.preprocessing.terrain
    return hillshade(
        dem,
        cellsize,
        settings.quicklook_azimuth_deg,
        90.0 - settings.quicklook_altitude_deg,
    )
