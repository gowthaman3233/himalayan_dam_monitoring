"""Bi-temporal landslide change detection.

Brief, Section 7.4: compare pre- and post-event composites on NDVI drop,
brightness/SWIR increase and Sentinel-1 backscatter change, and output a change
map plus polygons with area.

**This module is the sole source of novelty.** The brief is explicit that the
U-Net (Phase 6) classifies landslide-*like* surfaces on a single date, so the
"new" in "new landslide" must come from here and never from segmentation. A
scar that was already there before the event is not a new landslide, however
convincingly a classifier labels it.

Three design points, each forced by evidence rather than chosen for neatness:

1. **Agreement, not any single signal.** Each signal has a known failure mode
   on its own -- NDVI over ground that was already bare, brightness under a
   change of illumination, SAR over altered geometry -- so
   ``min_agreeing_signals`` (default 2 of 3) is what makes them complementary.
   A signal whose inputs were not supplied is *absent*, never counted as
   disagreeing.

2. **SAR change is used by magnitude, not sign.** Backscatter rises on some
   parts of a landslide and falls on others (Burrows et al. 2022; Mondini et
   al. 2021), so a signed threshold would systematically miss half of each
   failure. Note also that interferometric *coherence loss* is the stronger
   SAR indicator in the literature, but ``COPERNICUS/S1_GRD`` carries
   amplitude only -- SLC data would be needed. Recorded as a limitation in
   docs/methods.md 5.5 rather than worked around.

3. **Snow is screened out, not thresholded through.** A fresh snowfall between
   the two dates crushes NDVI and raises brightness, which is precisely a
   landslide's optical signature. Notti et al. (2023) avoid this by requiring
   images from a snow-free season; a monitoring prototype cannot assume that,
   so snow is screened per pixel on *both* dates with the test of Hall et al.
   (1995), and a pixel that is snow on either date is excluded as
   unattributable.

References
----------
Notti, D., Cignetti, M., Godone, D., & Giordan, D. (2023). Semi-automatic
    mapping of shallow landslides using free Sentinel-2 images and Google
    Earth Engine. *Natural Hazards and Earth System Sciences*, 23(7),
    2625-2648. doi:10.5194/nhess-23-2625-2023 -- NDVIvar = NDVI_post -
    NDVI_pre; "the optimal threshold should be in the range of -0.20 to
    -0.15"; applied as "NDVIvar <= -0.15 joined to slope > 15 deg", with
    polygon median-slope filters of 17 deg and 20 deg at their two sites.
Hall, D. K., Riggs, G. A., & Salomonson, V. V. (1995). Development of methods
    for mapping global snow cover using MODIS data. *Remote Sensing of
    Environment*, 54(2), 127-140. doi:10.1016/0034-4257(95)00137-P -- snow
    where NDSI >= 0.4 and NIR reflectance > 0.11.
Rouse, J. W., Haas, R. H., Schell, J. A., & Deering, D. W. (1974). Monitoring
    vegetation systems in the Great Plains with ERTS. *NASA SP-351*, 309-317
    -- NDVI.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Any

import numpy as np

# spectral_index is a generic safe normalised difference (NaN where the
# denominator vanishes); it lives in water.py because that is where the first
# index needed it. Imported rather than duplicated. A later tidy-up should move
# it to a shared module -- noted in docs/methods.md 5.7.
from detection.water import spectral_index
from utils.logging import get_logger

if TYPE_CHECKING:  # pragma: no cover
    import geopandas as gpd

    from config.schema import Config

log = get_logger(__name__)

#: Scale factor between a median absolute deviation and a standard deviation
#: for normally distributed data. MAD * 1.4826 estimates sigma robustly.
MAD_TO_SIGMA = 1.4826

#: Columns carried by every landslide polygon frame.
LANDSLIDE_COLUMNS = (
    "landslide_id",
    "area_m2",
    "perimeter_m",
    "pixel_count",
    "median_slope_deg",
    "mean_agreeing_signals",
    "centroid_x",
    "centroid_y",
    "centroid_lon",
    "centroid_lat",
    "geometry",
)


def ndvi(nir: np.ndarray, red: np.ndarray) -> np.ndarray:
    """NDVI = (NIR - Red) / (NIR + Red), after Rouse et al. (1974).

    Sentinel-2: B8 near-infrared, B4 red. Vegetation is strongly positive;
    bare rock and soil are near zero.
    """
    return spectral_index(nir, red)


def ndsi(green: np.ndarray, swir1: np.ndarray) -> np.ndarray:
    """NDSI = (Green - SWIR1) / (Green + SWIR1), after Hall et al. (1995).

    Identical in form to MNDWI (see ``detection.water.mndwi`` and
    docs/methods.md 3.2) -- which is exactly why neither index can separate
    snow from water, and why the NIR test below is needed alongside it.
    """
    return spectral_index(green, swir1)


def snow_mask(
    green: np.ndarray,
    swir1: np.ndarray,
    nir_reflectance: np.ndarray,
    *,
    ndsi_min: float = 0.4,
    nir_min: float = 0.11,
) -> np.ndarray:
    """Snow by the test of Hall et al. (1995): NDSI >= 0.4 and NIR > 0.11.

    Both conditions are needed. NDSI alone also selects water, which is why
    the MODIS algorithm adds the near-infrared criterion.
    """
    index = ndsi(green, swir1)
    reflectance = np.asarray(nir_reflectance, dtype=np.float64)
    return (index >= ndsi_min) & (reflectance > nir_min)


def snow_mask_from_config(
    cfg: "Config",
    green: np.ndarray,
    swir1: np.ndarray,
    nir_reflectance: np.ndarray,
) -> np.ndarray:
    """:func:`snow_mask` with the thresholds from configuration.

    ``gating.snow_ndsi_min`` and ``gating.snow_nir_min_reflectance`` carry the
    Hall et al. (1995) values and had no reader: :func:`snow_mask` defaulted
    them and :func:`detect_change` takes pre-built masks, so the configured
    numbers never reached the test they describe.
    """
    gating = cfg.detection.landslide_change.gating
    return snow_mask(
        green,
        swir1,
        nir_reflectance,
        ndsi_min=gating.snow_ndsi_min,
        nir_min=gating.snow_nir_min_reflectance,
    )


def robust_change_threshold(
    change: np.ndarray,
    min_z: float,
    *,
    valid: np.ndarray | None = None,
    absolute: bool = False,
) -> tuple[float, float, float]:
    """A change threshold derived from the scene's own distribution.

    Uses the median and the median absolute deviation rather than the mean and
    standard deviation: speckle and the long tail of genuine change both drag
    a mean, while the median is unmoved by a minority of extreme values. This
    is what the project uses wherever the literature publishes no threshold,
    instead of inventing one.

    Args:
        absolute: threshold ``|change - median|`` rather than the signed value.
            Used for SAR, where the sign is not informative.

    Returns:
        ``(threshold, median, sigma_estimate)``. The threshold is expressed in
        the units of ``change``.

    Raises:
        ValueError: if no finite sample survives, or the MAD is zero (a
            constant scene has no scale against which "unusual" is defined).
    """
    data = np.asarray(change, dtype=np.float64)
    selection = np.isfinite(data)
    if valid is not None:
        selection &= np.asarray(valid, dtype=bool)

    samples = data[selection]
    if samples.size == 0:
        raise ValueError("no finite samples from which to derive a change threshold")

    median = float(np.median(samples))
    mad = float(np.median(np.abs(samples - median)))
    if mad == 0.0:
        raise ValueError(
            "the median absolute deviation is zero, so the scene has no scale "
            "against which a change could be called unusual"
        )

    sigma = mad * MAD_TO_SIGMA
    threshold = median + min_z * sigma if not absolute else min_z * sigma
    return threshold, median, sigma


@dataclass(frozen=True)
class ChangeSignal:
    """One differenced quantity and the verdict it supports."""

    name: str
    change: np.ndarray
    indicates_landslide: np.ndarray
    available: np.ndarray
    threshold: float
    method: str

    def summary(self) -> dict[str, float | str]:
        present = int(np.count_nonzero(self.available))
        flagged = int(np.count_nonzero(self.indicates_landslide))
        return {
            "method": self.method,
            "threshold": float(self.threshold),
            "available_px": float(present),
            "flagged_px": float(flagged),
            "flagged_fraction_of_available": (
                float(flagged / present) if present else 0.0
            ),
        }


@dataclass
class LandslideChangeResult:
    """The Phase 5 product: a change map and the evidence behind it."""

    change: np.ndarray
    agreeing: np.ndarray
    valid: np.ndarray
    signals: dict[str, ChangeSignal] = field(default_factory=dict)
    excluded: dict[str, np.ndarray] = field(default_factory=dict)

    @property
    def changed_pixels(self) -> int:
        return int(np.count_nonzero(self.change))

    def exclusion_summary(self) -> dict[str, float]:
        return {
            name: float(np.count_nonzero(mask))
            for name, mask in self.excluded.items()
        }

    def summary(self) -> str:
        valid = int(np.count_nonzero(self.valid))
        return (
            f"{self.changed_pixels} changed px of {valid} assessable "
            f"({self.changed_pixels / valid * 100:.3f}%)"
            if valid
            else "no assessable pixels"
        )


def _unavailable_signal(
    name: str, change: np.ndarray, shape: tuple[int, int], reason: str
) -> ChangeSignal:
    """A signal that could not be computed, recorded rather than raised.

    ``available`` is empty, so the signal counts neither for nor against
    agreement -- the same treatment a missing input receives.
    """
    log.warning("%s unavailable: %s", name, reason)
    return ChangeSignal(
        name=name,
        change=change,
        indicates_landslide=np.zeros(shape, dtype=bool),
        available=np.zeros(shape, dtype=bool),
        threshold=float("nan"),
        method=f"unavailable: {reason}",
    )


def detect_change(
    cfg: "Config",
    *,
    ndvi_pre: np.ndarray | None = None,
    ndvi_post: np.ndarray | None = None,
    brightness_pre: np.ndarray | None = None,
    brightness_post: np.ndarray | None = None,
    sar_db_pre: np.ndarray | None = None,
    sar_db_post: np.ndarray | None = None,
    slope_deg: np.ndarray | None = None,
    snow_pre: np.ndarray | None = None,
    snow_post: np.ndarray | None = None,
    terrain_shadow_pre: np.ndarray | None = None,
    terrain_shadow_post: np.ndarray | None = None,
    water_post: np.ndarray | None = None,
    invalid_pre: np.ndarray | None = None,
    invalid_post: np.ndarray | None = None,
) -> LandslideChangeResult:
    """Detect new landslide surfaces between two dates.

    Every signal is optional, so a pair with no SAR, or with one optical date
    clouded, still yields whatever the remaining evidence supports -- but a
    pixel is only ever called changed where enough signals *agree*.

    Args:
        ndvi_pre, ndvi_post: NDVI on each date. Pass :func:`ndvi` output.
        brightness_pre, brightness_post: a brightness or SWIR measure, in
            consistent units across the two dates. An increase indicates fresh
            bare material.
        sar_db_pre, sar_db_post: backscatter in dB.
        slope_deg: terrain slope; pixels below ``gating.min_slope_deg`` are
            excluded, as landslides require a slope.
        snow_pre, snow_post: snow masks. Pass :func:`snow_mask` output. A pixel
            that is snow on *either* date is excluded as unattributable.
        water_post: open water on the post date, from Phase 3/4 water
            detection. Excluded because a landslide deposit cannot be under
            water, and because water trips the NDVI and SAR signals unaided --
            so a change map at a dam site otherwise fills with the
            impoundment. Note this is water on the post date, not merely
            *new* water: a river that deepens into a lake is water on both
            dates and would survive a new-water-only filter. This module does
            not import the water detector, so the phases stay separable.
        terrain_shadow_pre, terrain_shadow_post: geometric shadow masks.
        invalid_pre, invalid_post: cloud, cloud shadow and defective pixels.

    Returns:
        A :class:`LandslideChangeResult`.
    """
    settings = cfg.detection.landslide_change
    shape = _common_shape(
        ndvi_pre, ndvi_post, brightness_pre, brightness_post, sar_db_pre, sar_db_post,
        slope_deg,
    )

    # ---- what is excluded before any change is believed ------------------ #
    excluded: dict[str, np.ndarray] = {}
    assessable = np.ones(shape, dtype=bool)

    for name, mask in (("invalid_pre", invalid_pre), ("invalid_post", invalid_post)):
        if mask is not None:
            flag = np.asarray(mask, dtype=bool)
            excluded[name] = flag
            assessable &= ~flag

    if settings.gating.exclude_snow:
        for name, mask in (("snow_pre", snow_pre), ("snow_post", snow_post)):
            if mask is not None:
                flag = np.asarray(mask, dtype=bool)
                excluded[name] = flag
                assessable &= ~flag

    if settings.gating.exclude_terrain_shadow:
        for name, mask in (
            ("terrain_shadow_pre", terrain_shadow_pre),
            ("terrain_shadow_post", terrain_shadow_post),
        ):
            if mask is not None:
                flag = np.asarray(mask, dtype=bool)
                excluded[name] = flag
                assessable &= ~flag

    if settings.gating.exclude_water_on_post_date and water_post is not None:
        wet = np.asarray(water_post, dtype=bool)
        excluded["water_on_post_date"] = wet
        assessable &= ~wet

    if slope_deg is not None:
        gentle = np.asarray(slope_deg, dtype=np.float64) < settings.gating.min_slope_deg
        excluded["slope_below_minimum"] = gentle
        assessable &= ~gentle

    # ---- signals --------------------------------------------------------- #
    signals: dict[str, ChangeSignal] = {}

    if ndvi_pre is not None and ndvi_post is not None:
        pre = np.asarray(ndvi_pre, dtype=np.float64)
        post = np.asarray(ndvi_post, dtype=np.float64)
        change = post - pre
        available = np.isfinite(change) & assessable
        threshold = settings.optical.ndvi_drop
        signals["ndvi_drop"] = ChangeSignal(
            name="ndvi_drop",
            change=change,
            indicates_landslide=(change <= threshold) & available,
            available=available,
            threshold=float(threshold),
            method=f"NDVIvar <= {threshold} (Notti et al. 2023)",
        )

    if brightness_pre is not None and brightness_post is not None:
        pre = np.asarray(brightness_pre, dtype=np.float64)
        post = np.asarray(brightness_post, dtype=np.float64)
        change = post - pre
        available = np.isfinite(change) & assessable
        optical = settings.optical
        if optical.brightness_method == "fixed":
            threshold = float(optical.brightness_fixed_increase)
            method = f"brightness increase >= {threshold} (configured)"
        else:
            try:
                threshold, median, sigma = robust_change_threshold(
                    change, optical.brightness_min_z, valid=available
                )
            except ValueError as exc:
                # No scale against which change could be called unusual. That
                # is a signal that cannot be computed, not a reason to abandon
                # the run: it is recorded unavailable and the remaining
                # signals carry on. Found by the end-to-end test, where a
                # noiseless synthetic scene crashed the detector outright.
                signals["brightness_increase"] = _unavailable_signal(
                    "brightness_increase", change, shape, str(exc)
                )
                threshold = None
            else:
                method = (
                    f"brightness increase >= {threshold:.4f} "
                    f"(median {median:.4f} + {optical.brightness_min_z} x MAD sigma "
                    f"{sigma:.4f})"
                )
        if "brightness_increase" not in signals:
            signals["brightness_increase"] = ChangeSignal(
                name="brightness_increase",
                change=change,
                indicates_landslide=(change >= threshold) & available,
                available=available,
                threshold=float(threshold),
                method=method,
            )

    if sar_db_pre is not None and sar_db_post is not None:
        pre = np.asarray(sar_db_pre, dtype=np.float64)
        post = np.asarray(sar_db_post, dtype=np.float64)
        change = post - pre
        available = np.isfinite(change) & assessable
        sar = settings.sar
        # Magnitude, not sign: backscatter rises on some parts of a landslide
        # and falls on others (Burrows et al. 2022; Mondini et al. 2021).
        magnitude = np.abs(change)
        if sar.change_method == "fixed":
            threshold = float(sar.fixed_min_abs_db)
            method = f"|backscatter change| >= {threshold} dB (configured)"
        else:
            try:
                threshold, median, sigma = robust_change_threshold(
                    change, sar.min_abs_z, valid=available, absolute=True
                )
            except ValueError as exc:
                signals["sar_change"] = _unavailable_signal(
                    "sar_change", change, shape, str(exc)
                )
                threshold = None
            else:
                method = (
                    f"|backscatter change| >= {threshold:.3f} dB "
                    f"({sar.min_abs_z} x MAD sigma {sigma:.3f}, median {median:.3f})"
                )
        if "sar_change" not in signals:
            signals["sar_change"] = ChangeSignal(
                name="sar_change",
                change=change,
                indicates_landslide=(magnitude >= threshold) & available,
                available=available,
                threshold=float(threshold),
                method=method,
            )

    if not signals:
        raise ValueError(
            "no change signal could be computed: detect_change() needs at least "
            "one matched pre/post pair (ndvi, brightness or sar)"
        )

    # ---- agreement -------------------------------------------------------- #
    agreeing = np.zeros(shape, dtype=np.int16)
    available_count = np.zeros(shape, dtype=np.int16)
    for signal in signals.values():
        agreeing += signal.indicates_landslide.astype(np.int16)
        available_count += signal.available.astype(np.int16)

    required = settings.min_agreeing_signals
    # A pixel can only meet the requirement where enough signals were actually
    # available to meet it -- otherwise a data gap would read as "no change"
    # on evidence that was never collected.
    decidable = assessable & (available_count >= required)
    change_map = decidable & (agreeing >= required)

    if required > len(signals):
        log.warning(
            "min_agreeing_signals is %d but only %d signal(s) could be computed, "
            "so no pixel can be flagged",
            required,
            len(signals),
        )

    result = LandslideChangeResult(
        change=change_map,
        agreeing=agreeing,
        valid=decidable,
        signals=signals,
        excluded=excluded,
    )
    log.info("landslide change -- %s", result.summary())
    for name, signal in signals.items():
        log.info("  %s: %s", name, signal.method)
    return result


def landslide_polygons(
    result: LandslideChangeResult,
    transform: Any,
    crs: Any,
    cfg: "Config",
    *,
    slope_deg: np.ndarray | None = None,
) -> "gpd.GeoDataFrame":
    """Polygons for the change map, with area and a median-slope filter.

    Notti et al. (2023) filter their mapped polygons by median slope (17 deg
    and 20 deg at their two sites) as well as by pixel slope, because a
    polygon straddling flat ground is unlikely to be a landslide even if some
    of its pixels are steep. That second filter is applied here when
    ``slope_deg`` is supplied.
    """
    import geopandas as gpd
    import rasterio.features
    from shapely.geometry import shape as to_shape

    from utils.crs import ensure_projected, pixel_area_m2

    projected = ensure_projected(crs, context="landslide polygon area")
    settings = cfg.detection.landslide_change.polygons
    gating = cfg.detection.landslide_change.gating

    binary = np.asarray(result.change, dtype=bool)
    cell_area = pixel_area_m2(transform, projected)

    records: list[dict[str, Any]] = []
    for geometry, value in rasterio.features.shapes(
        binary.astype(np.uint8),
        mask=binary,
        transform=transform,
        connectivity=int(settings.connectivity),
    ):
        if not value:
            continue
        records.append({"geometry": to_shape(geometry)})

    if not records:
        log.info("no landslide change polygons")
        return _empty_frame(projected)

    # Per-polygon statistics need the pixels inside each polygon.
    kept: list[dict[str, Any]] = []
    dropped_small = 0
    dropped_gentle = 0
    for record in records:
        polygon = record["geometry"]
        area = float(polygon.area)
        if area < settings.min_area_m2:
            dropped_small += 1
            continue

        median_slope = float("nan")
        mean_agreeing = float("nan")
        footprint = rasterio.features.rasterize(
            [(polygon, 1)],
            out_shape=binary.shape,
            transform=transform,
            dtype="uint8",
        ).astype(bool)
        if slope_deg is not None and footprint.any():
            values = np.asarray(slope_deg, dtype=np.float64)[footprint]
            values = values[np.isfinite(values)]
            if values.size:
                median_slope = float(np.median(values))
        if footprint.any():
            mean_agreeing = float(result.agreeing[footprint].mean())

        if (
            slope_deg is not None
            and np.isfinite(median_slope)
            and median_slope < gating.min_median_slope_deg
        ):
            dropped_gentle += 1
            continue

        kept.append(
            {
                "geometry": polygon,
                "area_m2": area,
                "perimeter_m": float(polygon.length),
                "pixel_count": int(round(area / cell_area)),
                "median_slope_deg": median_slope,
                "mean_agreeing_signals": mean_agreeing,
            }
        )

    if dropped_small or dropped_gentle:
        log.info(
            "dropped %d polygon(s) below %.0f m^2 and %d below a median slope of "
            "%.1f deg; kept %d",
            dropped_small,
            settings.min_area_m2,
            dropped_gentle,
            gating.min_median_slope_deg,
            len(kept),
        )

    if not kept:
        return _empty_frame(projected)

    kept.sort(key=lambda record: record["area_m2"], reverse=True)
    frame = gpd.GeoDataFrame(
        {
            "landslide_id": [index + 1 for index in range(len(kept))],
            "area_m2": [r["area_m2"] for r in kept],
            "perimeter_m": [r["perimeter_m"] for r in kept],
            "pixel_count": [r["pixel_count"] for r in kept],
            "median_slope_deg": [r["median_slope_deg"] for r in kept],
            "mean_agreeing_signals": [r["mean_agreeing_signals"] for r in kept],
            "centroid_x": [r["geometry"].centroid.x for r in kept],
            "centroid_y": [r["geometry"].centroid.y for r in kept],
        },
        geometry=[r["geometry"] for r in kept],
        crs=projected,
    )

    centroids = (
        frame.set_geometry(gpd.points_from_xy(frame["centroid_x"], frame["centroid_y"]))
        .set_crs(projected)
        .to_crs("EPSG:4326")
        .geometry
    )
    frame["centroid_lon"] = centroids.x.to_numpy()
    frame["centroid_lat"] = centroids.y.to_numpy()

    log.info(
        "%d landslide polygon(s), largest %.0f m^2, total %.0f m^2",
        len(frame),
        frame["area_m2"].iloc[0],
        frame["area_m2"].sum(),
    )
    return frame[list(LANDSLIDE_COLUMNS)]


def _empty_frame(crs: Any) -> "gpd.GeoDataFrame":
    import geopandas as gpd

    empty = gpd.GeoDataFrame(
        {name: [] for name in LANDSLIDE_COLUMNS if name != "geometry"},
        geometry=[],
        crs=crs,
    )
    return empty[list(LANDSLIDE_COLUMNS)]


def _common_shape(*arrays: np.ndarray | None) -> tuple[int, int]:
    shapes = {np.asarray(a).shape for a in arrays if a is not None}
    if not shapes:
        raise ValueError("no arrays supplied")
    if len(shapes) > 1:
        raise ValueError(f"arrays have mismatched shapes: {sorted(shapes)}")
    shape = shapes.pop()
    if len(shape) != 2:
        raise ValueError(f"arrays must be 2-D, got shape {shape}")
    return shape  # type: ignore[return-value]
