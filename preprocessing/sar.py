"""Sentinel-1 preprocessing: units, speckle filtering, layover/shadow geometry.

Brief, Section 7.1: convert to dB, apply a configurable speckle filter, keep the
incidence angle, and build a SAR layover/shadow mask per scene from the DEM,
the incidence angle and the orbit geometry.

**Units -- an important correction to the brief.** ``COPERNICUS/S1_GRD`` already
serves VV/VH **in decibels**; it is ``COPERNICUS/S1_GRD_FLOAT`` that carries
linear power. Verified empirically in Phase 1 (docs/methods.md 1.4): VV spans
-49.1 to +13.8 dB over the study area, a range only meaningful on a log scale.
Applying a dB conversion again would corrupt the data, so
``preprocessing.sar.convert_to_db`` defaults to **false** and
:func:`to_decibels` refuses input that already looks logarithmic.

Why the layover/shadow mask matters here specifically: the shadow-rejection
logic in Phase 4 (brief, Section 7.3) defers to optical evidence wherever SAR is
geometrically unreliable. That rule is only safe if the unreliable areas are
identified honestly, which is what this module does.

References
----------
Lee, J. S. (1980). "Digital image enhancement and noise filtering by use of
    local statistics." *IEEE Transactions on Pattern Analysis and Machine
    Intelligence*, PAMI-2(2), 165-168. -- the adaptive local-statistics speckle
    filter implemented in :func:`lee_filter`.
Kropatsch, W. G. and Strobl, D. (1990). "The generation of SAR layover and
    shadow maps from digital elevation models." *IEEE Transactions on Geoscience
    and Remote Sensing*, 28(1), 98-107. doi:10.1109/36.45752 -- the layover and
    shadow conditions implemented in :func:`layover_shadow_mask`.
"""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np

from config.schema import Config
from utils.logging import get_logger

log = get_logger(__name__)

#: Class codes in the returned geometry map.
GEOMETRY_NOMINAL = 0
GEOMETRY_FORESHORTENING = 1
GEOMETRY_LAYOVER = 2
GEOMETRY_SHADOW = 3

GEOMETRY_LABELS = {
    GEOMETRY_NOMINAL: "nominal",
    GEOMETRY_FORESHORTENING: "foreshortening",
    GEOMETRY_LAYOVER: "layover",
    GEOMETRY_SHADOW: "radar shadow",
}


class SARUnitsError(ValueError):
    """Raised when a dB conversion would be applied to data already in dB."""


# --------------------------------------------------------------------------- #
# Units
# --------------------------------------------------------------------------- #


def looks_like_decibels(backscatter: np.ndarray) -> bool:
    """Heuristic: does this array already look logarithmic?

    Linear backscatter power is non-negative and typically well below 10;
    decibel backscatter is mostly negative. A substantial negative fraction is
    therefore strong evidence of dB.
    """
    values = np.asarray(backscatter, dtype=np.float64)
    finite = values[np.isfinite(values)]
    if finite.size == 0:
        return False
    return bool((finite < 0).mean() > 0.1)


def to_decibels(backscatter: np.ndarray, *, force: bool = False) -> np.ndarray:
    """Linear power to decibels: ``10 * log10(x)``.

    Raises:
        SARUnitsError: if the input already looks like dB and ``force`` is not
            set. Silently double-converting is the failure mode this guards
            against -- it produces plausible-looking nonsense.
    """
    values = np.asarray(backscatter, dtype=np.float64)
    if not force and looks_like_decibels(values):
        raise SARUnitsError(
            "this array already looks like decibels (a substantial fraction of "
            "values are negative). COPERNICUS/S1_GRD is served in dB; converting "
            "again would corrupt it. Pass force=True only if you are certain the "
            "input is linear power."
        )
    with np.errstate(divide="ignore", invalid="ignore"):
        return 10.0 * np.log10(np.where(values > 0, values, np.nan))


def from_decibels(backscatter_db: np.ndarray) -> np.ndarray:
    """Decibels to linear power: ``10 ** (x / 10)``.

    Needed because speckle statistics are defined on linear power, not dB.
    """
    return np.power(10.0, np.asarray(backscatter_db, dtype=np.float64) / 10.0)


# --------------------------------------------------------------------------- #
# Speckle filtering
# --------------------------------------------------------------------------- #


def lee_filter(
    image: np.ndarray,
    window_px: int = 5,
    equivalent_number_of_looks: float = 4.4,
) -> np.ndarray:
    """Adaptive speckle filter of Lee (1980).

    Blends the local mean towards the observed value by a weight derived from
    local variance, so homogeneous areas are smoothed while edges and bright
    targets are preserved::

        k    = max(0, (Var_local - Var_noise)) / Var_local
        out  = mean_local + k * (observed - mean_local)

    with ``Var_noise = mean_local^2 / ENL`` for multiplicative speckle.

    The input must be **linear power**, since the multiplicative speckle model
    does not hold in dB. :func:`despeckle` handles that conversion.
    """
    from scipy import ndimage

    if window_px < 3 or window_px % 2 == 0:
        raise ValueError(f"window_px must be odd and >= 3, got {window_px}")
    if equivalent_number_of_looks <= 0:
        raise ValueError(
            f"equivalent_number_of_looks must be positive, got "
            f"{equivalent_number_of_looks}"
        )

    values = np.asarray(image, dtype=np.float64)
    size = (window_px, window_px)

    local_mean = ndimage.uniform_filter(values, size=size)
    local_mean_sq = ndimage.uniform_filter(values**2, size=size)
    local_var = np.maximum(local_mean_sq - local_mean**2, 0.0)

    noise_var = (local_mean**2) / float(equivalent_number_of_looks)

    with np.errstate(divide="ignore", invalid="ignore"):
        weight = np.where(local_var > 0, (local_var - noise_var) / local_var, 0.0)
    weight = np.clip(weight, 0.0, 1.0)

    return local_mean + weight * (values - local_mean)


def median_filter(image: np.ndarray, window_px: int = 5) -> np.ndarray:
    """Focal median -- the simple alternative the brief allows.

    Unlike :func:`lee_filter` this is valid directly on dB, because the median
    commutes with the monotonic log transform.
    """
    from scipy import ndimage

    if window_px < 3 or window_px % 2 == 0:
        raise ValueError(f"window_px must be odd and >= 3, got {window_px}")
    return ndimage.median_filter(np.asarray(image, dtype=np.float64), size=window_px)


def despeckle(backscatter_db: np.ndarray, cfg: Config) -> np.ndarray:
    """Apply the configured speckle filter to **decibel** backscatter.

    The Lee filter is defined for multiplicative speckle on linear power, so
    this converts dB to power, filters, and converts back. The median filter is
    applied directly in dB, where it is equivalent.
    """
    settings = cfg.preprocessing.sar
    method = settings.speckle_filter

    if method == "none":
        return np.asarray(backscatter_db, dtype=np.float64)

    if method == "median":
        return median_filter(backscatter_db, settings.speckle_window_px)

    # Lee: round-trip through linear power.
    power = from_decibels(backscatter_db)
    filtered = lee_filter(
        power,
        window_px=settings.speckle_window_px,
        equivalent_number_of_looks=settings.equivalent_number_of_looks,
    )
    with np.errstate(divide="ignore", invalid="ignore"):
        return 10.0 * np.log10(np.where(filtered > 0, filtered, np.nan))


# --------------------------------------------------------------------------- #
# Layover and shadow geometry
# --------------------------------------------------------------------------- #


@dataclass(frozen=True)
class SARGeometry:
    """Per-pixel radar geometry classification for one scene."""

    classes: np.ndarray
    range_slope_deg: np.ndarray
    local_incidence_deg: np.ndarray
    toward_sensor_azimuth_deg: float

    @property
    def layover(self) -> np.ndarray:
        return self.classes == GEOMETRY_LAYOVER

    @property
    def shadow(self) -> np.ndarray:
        return self.classes == GEOMETRY_SHADOW

    @property
    def unreliable(self) -> np.ndarray:
        """Layover or shadow: where SAR evidence must not be trusted.

        Brief, Section 7.3: a SAR-water-like pixel inside this mask is
        *uncertain*, and the fusion defers to optical evidence.
        """
        return self.layover | self.shadow

    def fractions(self) -> dict[str, float]:
        return {
            label: float((self.classes == code).mean())
            for code, label in GEOMETRY_LABELS.items()
        }


def toward_sensor_azimuth(cfg: Config, orbit_pass: str) -> float:
    """Azimuth from the ground towards the sensor, in degrees clockwise of north.

    Sentinel-1 is **right-looking**: targets lie to the right of the flight
    direction, so from a target the sensor lies at ``heading - 90``. The
    configured defaults encode that for the mean ascending and descending
    headings; they are overridable per scene.
    """
    table = cfg.preprocessing.sar.toward_sensor_azimuth_deg
    key = (orbit_pass or "").upper()
    if key not in table:
        raise ValueError(
            f"no toward-sensor azimuth configured for orbit pass {orbit_pass!r}; "
            f"known: {sorted(table)}"
        )
    return float(table[key])


def layover_shadow_mask(
    dem: np.ndarray,
    cellsize: float,
    incidence_angle_deg: np.ndarray | float,
    toward_sensor_azimuth_deg: float,
    *,
    dilate_px: int = 0,
) -> SARGeometry:
    """Classify radar geometric distortion from the DEM (Kropatsch & Strobl 1990).

    Let ``alpha`` be the terrain slope measured in the ground-range direction,
    positive where the terrain rises **towards** the sensor, and ``theta`` the
    radar incidence angle. Then:

    * **layover** where ``alpha >= theta`` -- the slope is steeper than the
      incidence angle, so the top of the slope is imaged before its base and
      different surfaces collapse into one pixel;
    * **shadow** where ``alpha <= theta - 90`` -- the far side of a ridge tilts
      away more steeply than the complement of the incidence angle, so the
      radar cannot illuminate it at all;
    * **foreshortening** where ``0 < alpha < theta`` -- compressed but still
      usable, reported separately because it degrades rather than destroys the
      measurement;
    * **nominal** otherwise.

    Args:
        incidence_angle_deg: the scene's ``angle`` band, or a scalar.
        toward_sensor_azimuth_deg: see :func:`toward_sensor_azimuth`.
        dilate_px: grow layover and shadow by this many pixels.
    """
    from preprocessing.terrain import gradients

    elevation = np.asarray(dem, dtype=np.float64)
    dz_deast, dz_dnorth = gradients(elevation, cellsize)

    # Slope component along the horizontal direction towards the sensor.
    azimuth = np.radians(float(toward_sensor_azimuth_deg))
    east_component = np.sin(azimuth)
    north_component = np.cos(azimuth)
    dz_drange = dz_deast * east_component + dz_dnorth * north_component

    # Positive where the terrain rises towards the sensor.
    range_slope = np.arctan(dz_drange)

    theta = np.radians(np.asarray(incidence_angle_deg, dtype=np.float64))

    layover = range_slope >= theta
    shadow = range_slope <= (theta - np.pi / 2.0)
    foreshortening = (range_slope > 0) & (range_slope < theta) & ~layover

    if dilate_px > 0:
        from preprocessing.cloud_mask import dilate as _dilate

        layover = _dilate(layover, dilate_px)
        shadow = _dilate(shadow, dilate_px)

    classes = np.full(elevation.shape, GEOMETRY_NOMINAL, dtype=np.uint8)
    classes[foreshortening] = GEOMETRY_FORESHORTENING
    # Layover and shadow are assigned last: they are the severe cases and must
    # not be overwritten by the milder foreshortening class.
    classes[layover] = GEOMETRY_LAYOVER
    classes[shadow] = GEOMETRY_SHADOW

    geometry = SARGeometry(
        classes=classes,
        range_slope_deg=np.degrees(range_slope),
        local_incidence_deg=np.degrees(theta) * np.ones_like(elevation),
        toward_sensor_azimuth_deg=float(toward_sensor_azimuth_deg),
    )
    log.info(
        "SAR geometry (towards sensor %.1f deg): %s",
        toward_sensor_azimuth_deg,
        ", ".join(f"{k} {v * 100:.2f}%" for k, v in geometry.fractions().items()),
    )
    return geometry


def local_incidence_angle(
    dem: np.ndarray,
    cellsize: float,
    incidence_angle_deg: np.ndarray | float,
    toward_sensor_azimuth_deg: float,
) -> np.ndarray:
    """Incidence angle relative to the local surface, in degrees.

    The ``angle`` band gives the incidence angle against the ellipsoid. Over
    real topography the angle against the actual surface differs by the
    range-direction slope, and that is what controls backscatter brightness.
    """
    from preprocessing.terrain import gradients

    dz_deast, dz_dnorth = gradients(np.asarray(dem, dtype=np.float64), cellsize)

    azimuth = np.radians(float(toward_sensor_azimuth_deg))
    dz_drange = dz_deast * np.sin(azimuth) + dz_dnorth * np.cos(azimuth)
    range_slope = np.arctan(dz_drange)

    theta = np.radians(np.asarray(incidence_angle_deg, dtype=np.float64))
    return np.degrees(np.clip(theta - range_slope, 0.0, np.pi / 2.0))


def layover_shadow_for_scene(
    cfg: "Config",
    dem: np.ndarray,
    cellsize: float,
    incidence_angle_deg: "np.ndarray | float",
    orbit_pass: str,
) -> SARGeometry:
    """:func:`layover_shadow_mask` with the settings from configuration.

    ``preprocessing.sar.geometry_dilate_px`` had no reader -- the function
    below defaulted it and every caller took the default, so the setting did
    nothing. The toward-sensor azimuth is looked up from the orbit pass here
    too, so a caller cannot pair an ascending scene with a descending geometry
    by accident.
    """
    return layover_shadow_mask(
        dem,
        cellsize,
        incidence_angle_deg,
        toward_sensor_azimuth(cfg, orbit_pass),
        dilate_px=cfg.preprocessing.sar.geometry_dilate_px,
    )
