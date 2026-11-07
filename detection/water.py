"""Rule-based water detection: optical indices and Sentinel-1 backscatter.

Brief, Section 7.2. This is the baseline built *before* the U-Net and *before*
the shadow-rejection fusion, and it is deliberately shadow-naive: nothing in
this module reads the terrain-shadow mask. Section 7.3 requires Phase 4 to
report how many false water pixels it removes "compared with the index-only
mask", so that mask has to exist here, unimproved, as the thing to measure
against.

Three rules are enforced here rather than left to the caller:

1. **No pixel is called water without evidence.** Cloud, cloud shadow,
   defective and out-of-swath pixels are *invalid*, not *dry*. They are tracked
   in a separate `valid` mask so that "not water" and "not observed" can never
   be confused -- the distinction the brief's gap handling (Section 7.8) rests
   on.
2. **A threshold that the data do not support is not invented.** Otsu's method
   assumes a histogram with two classes of comparable mass. Where that fails,
   :func:`sar_water_threshold` returns a decision with ``available=False`` and
   a reason, and the SAR mask is empty-and-invalid rather than arbitrary. There
   is no default dB fallback.
3. **Areas are measured in metres, never degrees.** :func:`water_bodies`
   refuses a geographic CRS through :func:`utils.crs.ensure_projected`.

References
----------
McFeeters, S. K. (1996). The use of the Normalized Difference Water Index
    (NDWI) in the delineation of open water features. *International Journal of
    Remote Sensing*, 17(7), 1425-1432. doi:10.1080/01431169608948714
Xu, H. (2006). Modification of normalised difference water index (NDWI) to
    enhance open water features in remotely sensed imagery. *International
    Journal of Remote Sensing*, 27(14), 3025-3033.
    doi:10.1080/01431160600589179
Otsu, N. (1979). A threshold selection method from gray-level histograms.
    *IEEE Transactions on Systems, Man, and Cybernetics*, 9(1), 62-66.
    doi:10.1109/TSMC.1979.4310076
Chini, M., Hostache, R., Giustarini, L., & Matgen, P. (2017). A hierarchical
    split-based approach for parametric thresholding of SAR images: Flood
    inundation as a test case. *IEEE Transactions on Geoscience and Remote
    Sensing*, 55(12), 6975-6988. doi:10.1109/TGRS.2017.2737664
Ashman, K. M., Bird, C. M., & Zepf, S. E. (1994). Detecting bimodality in
    astronomical datasets. *The Astronomical Journal*, 108, 2348-2361.
    doi:10.1086/117248
Hall, D. K., Riggs, G. A., & Salomonson, V. V. (1995). Development of methods
    for mapping global snow cover using Moderate Resolution Imaging
    Spectroradiometer data. *Remote Sensing of Environment*, 54(2), 127-140.
    doi:10.1016/0034-4257(95)00137-P
Hall, D. K., Riggs, G. A., Salomonson, V. V., DiGirolamo, N. E., & Bayr, K. J.
    (2002). MODIS snow-cover products. *Remote Sensing of Environment*, 83(1-2),
    181-194. doi:10.1016/S0034-4257(02)00095-0
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Any

import numpy as np

from utils.logging import get_logger

if TYPE_CHECKING:  # pragma: no cover
    import geopandas as gpd

    from config.schema import Config, SARWaterConfig

log = get_logger(__name__)

#: Denominators below this are treated as unmeasurable rather than divided by.
#: Sentinel-2 L2A reflectance is scaled 0-10000, so a green+NIR sum this small
#: carries no usable signal either way.
_MIN_INDEX_DENOMINATOR = 1e-6


# --------------------------------------------------------------------------- #
# Spectral indices
# --------------------------------------------------------------------------- #


def spectral_index(band_a: np.ndarray, band_b: np.ndarray) -> np.ndarray:
    """Normalised difference ``(a - b) / (a + b)``, NaN where undefined.

    Returning NaN rather than 0 where the denominator vanishes matters: zero is
    a meaningful index value (it is the land/water boundary both index authors
    propose), so using it as a fill would place unmeasurable pixels exactly on
    the decision boundary.
    """
    a = np.asarray(band_a, dtype=np.float64)
    b = np.asarray(band_b, dtype=np.float64)
    if a.shape != b.shape:
        raise ValueError(f"band shapes differ: {a.shape} vs {b.shape}")

    denominator = a + b
    usable = np.isfinite(denominator) & (np.abs(denominator) > _MIN_INDEX_DENOMINATOR)

    out = np.full(a.shape, np.nan, dtype=np.float64)
    np.divide(a - b, denominator, out=out, where=usable)
    return out


def ndwi(green: np.ndarray, nir: np.ndarray) -> np.ndarray:
    """NDWI = (Green - NIR) / (Green + NIR).

    McFeeters (1996). Sentinel-2: B3 green, B8 NIR. Water is positive.
    """
    return spectral_index(green, nir)


def mndwi(green: np.ndarray, swir1: np.ndarray) -> np.ndarray:
    """MNDWI = (Green - SWIR1) / (Green + SWIR1).

    Xu (2006). Sentinel-2: B3 green, B11 SWIR1. Water is positive.

    Preferred over NDWI in this project's terrain: snow is bright in NIR, so
    NDWI of snow sits near water's range, whereas snow absorbs strongly in
    SWIR1 and separates cleanly.
    """
    return spectral_index(green, swir1)


# --------------------------------------------------------------------------- #
# Thresholding
# --------------------------------------------------------------------------- #


def otsu_threshold(
    values: np.ndarray,
    *,
    bins: int = 256,
    value_range: tuple[float, float] | None = None,
) -> float:
    """Otsu's (1979) threshold: the bin centre maximising between-class variance.

    Implemented from the histogram rather than taken from scikit-image so that
    the arithmetic is unit-testable without the dependency; the test suite
    cross-checks it against ``skimage.filters.threshold_otsu``.

    Args:
        values: samples. Non-finite entries are dropped.
        bins: histogram bin count.
        value_range: ``(low, high)`` clip applied before binning, so that a few
            extreme outliers cannot dominate the variance.

    Raises:
        ValueError: if no finite sample survives, or all samples are identical
            (a single-valued histogram has no between-class variance to
            maximise, so any "threshold" would be arbitrary).
    """
    samples = np.asarray(values, dtype=np.float64).ravel()
    samples = samples[np.isfinite(samples)]
    if samples.size == 0:
        raise ValueError("no finite samples to threshold")

    if value_range is not None:
        low, high = float(value_range[0]), float(value_range[1])
        samples = samples[(samples >= low) & (samples <= high)]
        if samples.size == 0:
            raise ValueError(
                f"no finite samples inside the search range [{low}, {high}]"
            )

    if np.ptp(samples) == 0.0:
        raise ValueError(
            f"all {samples.size} samples equal {samples[0]}: a single-valued "
            "histogram has no between-class variance, so no threshold is defined"
        )

    counts, edges = np.histogram(samples, bins=int(bins))
    centres = 0.5 * (edges[:-1] + edges[1:])
    total = counts.sum()

    # Cumulative class-0 weight and mean at each possible split point.
    weight_low = np.cumsum(counts) / total
    mean_low_cum = np.cumsum(counts * centres) / total
    mean_total = mean_low_cum[-1]

    # Between-class variance, in the form that needs only cumulative sums:
    #   sigma_b^2(t) = (mean_total * w(t) - mu(t))^2 / (w(t) * (1 - w(t)))
    denominator = weight_low * (1.0 - weight_low)
    with np.errstate(divide="ignore", invalid="ignore"):
        between = np.where(
            denominator > 0.0,
            (mean_total * weight_low - mean_low_cum) ** 2 / denominator,
            -np.inf,
        )

    return float(centres[int(np.argmax(between))])


#: EM stopping rule for the two-component fit. Fixed rather than configurable:
#: these govern numerical convergence, not a scientific choice.
_EM_MAX_ITERATIONS = 200
_EM_TOLERANCE = 1e-6

#: Cap on samples fed to the EM fit, for speed. The subsample is taken by a
#: deterministic stride, not randomly, so that a threshold is reproducible.
_EM_MAX_SAMPLES = 200_000


@dataclass(frozen=True)
class Bimodality:
    """How well a sample separates into two Gaussian modes.

    The two modes are **fitted** by expectation-maximisation rather than taken
    as the two sides of the threshold, and that distinction is not a detail --
    see docs/methods.md 3.4. Hard-splitting a sample at a threshold truncates
    each side, which pushes the two means apart and shrinks both standard
    deviations, inflating any separation statistic computed from them. Measured
    on a single Gaussian split at its own Otsu threshold, the hard-split
    statistic is 2.67 -- above the criterion below, so it would certify every
    unimodal histogram as bimodal. The fitted statistic for the same sample is
    0.99.

    ``separation`` is the dimensionless separation of the fitted mode means. For
    equal variances this is Ashman, Bird & Zepf (1994) eq. 3.1,
    ``(mu_2 - mu_1) / sigma``, whose two-peak condition (eq. 3.2, after Everitt
    & Hand 1981) is ``>= 2``. The form used here,
    ``sqrt(2) * |mu_2 - mu_1| / sqrt(s_1^2 + s_2^2)``, is the standard
    unequal-variance generalisation and reduces to eq. 3.1 when ``s_1 == s_2``;
    the generalisation is not itself from that paper.
    """

    threshold: float
    mean_low: float
    mean_high: float
    sd_low: float
    sd_high: float
    weight_low: float
    separation: float
    min_separation: float
    count_low: int
    count_high: int
    converged: bool
    iterations: int

    @property
    def is_bimodal(self) -> bool:
        return self.separation >= self.min_separation

    def describe(self) -> str:
        return (
            f"threshold {self.threshold:.2f}: fitted modes "
            f"{self.mean_low:.2f}+/-{self.sd_low:.2f} (w={self.weight_low:.3f}) "
            f"and {self.mean_high:.2f}+/-{self.sd_high:.2f}, "
            f"separation {self.separation:.2f} "
            f"({'bimodal' if self.is_bimodal else 'NOT bimodal'} at "
            f">= {self.min_separation})"
        )


def fit_two_gaussians(
    samples: np.ndarray, initial_split: float
) -> tuple[np.ndarray, np.ndarray, np.ndarray, bool, int]:
    """Fit a two-component 1-D Gaussian mixture by expectation-maximisation.

    Initialised from the two sides of ``initial_split`` (in practice an Otsu
    threshold), which is both a good starting point and deterministic.
    Responsibilities are computed in log space so a well-separated component
    cannot underflow to zero density.

    Returns:
        ``(means, sds, weights, converged, iterations)``, components ordered by
        mean, lowest first.
    """
    data = np.asarray(samples, dtype=np.float64).ravel()
    data = data[np.isfinite(data)]
    if data.size < 4:
        raise ValueError(
            f"need at least 4 finite samples to fit two modes, got {data.size}"
        )

    if data.size > _EM_MAX_SAMPLES:
        data = data[:: int(np.ceil(data.size / _EM_MAX_SAMPLES))]

    low = data[data <= initial_split]
    high = data[data > initial_split]
    if low.size == 0 or high.size == 0:
        # The split leaves one side empty, so it says nothing about where the
        # modes are. Fall back to splitting at the median.
        median = float(np.median(data))
        low, high = data[data <= median], data[data > median]
        if low.size == 0 or high.size == 0:
            raise ValueError("cannot initialise a two-mode fit: the sample is constant")

    # Floor on component width, so a component cannot collapse onto a single
    # repeated value and claim infinite separation.
    floor = max(1e-9, 1e-6 * float(data.std()))

    means = np.array([low.mean(), high.mean()], dtype=np.float64)
    sds = np.maximum(np.array([low.std(), high.std()], dtype=np.float64), floor)
    weights = np.array([low.size / data.size, high.size / data.size], dtype=np.float64)

    previous = None
    converged = False
    iteration = 0
    for iteration in range(1, _EM_MAX_ITERATIONS + 1):
        # E step, in log space.
        log_density = (
            np.log(np.maximum(weights, 1e-300))[:, None]
            - 0.5 * np.log(2.0 * np.pi * sds[:, None] ** 2)
            - (data[None, :] - means[:, None]) ** 2 / (2.0 * sds[:, None] ** 2)
        )
        peak = log_density.max(axis=0)
        log_likelihood = peak + np.log(np.exp(log_density - peak).sum(axis=0))
        responsibility = np.exp(log_density - log_likelihood[None, :])

        # M step.
        mass = responsibility.sum(axis=1) + 1e-300
        weights = mass / data.size
        means = (responsibility * data[None, :]).sum(axis=1) / mass
        variance = (responsibility * (data[None, :] - means[:, None]) ** 2).sum(
            axis=1
        ) / mass
        sds = np.maximum(np.sqrt(np.maximum(variance, 0.0)), floor)

        current = float(log_likelihood.mean())
        if previous is not None and abs(current - previous) < _EM_TOLERANCE:
            converged = True
            break
        previous = current

    order = np.argsort(means)
    return means[order], sds[order], weights[order], converged, iteration


def bimodality(
    values: np.ndarray, threshold: float, *, min_separation: float = 2.0
) -> Bimodality:
    """Measure how well ``values`` separates into two modes around ``threshold``.

    This is the guard on Otsu's assumption. Otsu always returns *a* number: it
    maximises between-class variance even for a single-moded histogram, where
    the two "classes" are two halves of one population and the threshold means
    nothing. Chini et al. (2017) identify exactly this failure for SAR water
    mapping, where the water class covers only a small part of the image.

    ``threshold`` initialises the fit and is reported back, but the separation
    is measured from the fitted components (see :class:`Bimodality`).
    """
    samples = np.asarray(values, dtype=np.float64).ravel()
    samples = samples[np.isfinite(samples)]

    count_low = int(np.count_nonzero(samples <= threshold))
    count_high = int(samples.size - count_low)

    def _no_separation() -> Bimodality:
        return Bimodality(
            threshold=float(threshold),
            mean_low=float("nan"),
            mean_high=float("nan"),
            sd_low=0.0,
            sd_high=0.0,
            weight_low=0.0,
            separation=0.0,
            min_separation=float(min_separation),
            count_low=count_low,
            count_high=count_high,
            converged=False,
            iterations=0,
        )

    if samples.size < 4 or np.ptp(samples) == 0.0:
        return _no_separation()

    try:
        means, sds, weights, converged, iterations = fit_two_gaussians(
            samples, float(threshold)
        )
    except ValueError:
        return _no_separation()

    spread = float(np.sqrt(sds[0] ** 2 + sds[1] ** 2))
    separation = (
        float(np.sqrt(2.0) * abs(means[1] - means[0]) / spread) if spread > 0.0 else 0.0
    )

    return Bimodality(
        threshold=float(threshold),
        mean_low=float(means[0]),
        mean_high=float(means[1]),
        sd_low=float(sds[0]),
        sd_high=float(sds[1]),
        weight_low=float(weights[0]),
        separation=separation,
        min_separation=float(min_separation),
        count_low=count_low,
        count_high=count_high,
        converged=converged,
        iterations=iterations,
    )


@dataclass(frozen=True)
class ThresholdDecision:
    """A backscatter threshold, or a documented refusal to produce one."""

    value: float | None
    method: str
    available: bool
    reason: str | None = None
    bimodality: Bimodality | None = None
    tiles_tested: int = 0
    tiles_accepted: int = 0

    @property
    def value_type(self) -> str:
        """Brief, Section 10 vocabulary."""
        return "derived" if self.available else "unavailable"

    def describe(self) -> str:
        if not self.available:
            return f"{self.method}: unavailable -- {self.reason}"
        detail = f"{self.method}: {self.value:.2f} dB"
        if self.tiles_tested:
            detail += f" from {self.tiles_accepted}/{self.tiles_tested} tile(s)"
        if self.bimodality is not None:
            detail += f"; {self.bimodality.describe()}"
        return detail


def _tile_slices(shape: tuple[int, int], tile_px: int):
    """Row/column slice pairs tiling ``shape``."""
    rows, cols = shape
    for row in range(0, rows, tile_px):
        for col in range(0, cols, tile_px):
            yield (
                slice(row, min(row + tile_px, rows)),
                slice(col, min(col + tile_px, cols)),
            )


def tiled_otsu_threshold(
    image: np.ndarray,
    *,
    valid: np.ndarray | None = None,
    tile_px: int = 128,
    bins: int = 256,
    value_range: tuple[float, float] | None = None,
    min_separation: float = 2.0,
    min_tile_valid_fraction: float = 0.5,
    min_tiles: int = 1,
) -> ThresholdDecision:
    """One threshold, derived only from tiles whose histogram actually separates.

    A simplification of the hierarchical split-based approach of Chini et al.
    (2017): that method searches tile size hierarchically, whereas this works at
    a single configured scale. The shared idea is the one that matters -- a
    threshold is parameterised only where both classes are present in
    comparable measure, instead of from a whole-scene histogram in which water
    is a few percent and leaves no second mode to find.

    Pixels from the accepted tiles are pooled and thresholded once, so the
    result is a single scene-wide threshold rather than a per-tile patchwork
    (which would produce seams at tile boundaries).
    """
    data = np.asarray(image, dtype=np.float64)
    if valid is None:
        valid = np.isfinite(data)
    else:
        valid = np.asarray(valid, dtype=bool) & np.isfinite(data)

    accepted: list[np.ndarray] = []
    tested = 0
    for row_slice, col_slice in _tile_slices(data.shape, int(tile_px)):
        tile = data[row_slice, col_slice]
        tile_valid = valid[row_slice, col_slice]
        if tile.size == 0:
            continue
        tested += 1

        if tile_valid.mean() < min_tile_valid_fraction:
            continue
        samples = tile[tile_valid]
        if samples.size < 2:
            continue

        try:
            candidate = otsu_threshold(samples, bins=bins, value_range=value_range)
        except ValueError:
            # A flat or empty tile: no threshold is defined for it. Skipping it
            # is the point of the method, not an error.
            continue

        if bimodality(samples, candidate, min_separation=min_separation).is_bimodal:
            accepted.append(samples)

    if len(accepted) < min_tiles:
        return ThresholdDecision(
            value=None,
            method="tiled_otsu",
            available=False,
            reason=(
                f"only {len(accepted)} of {tested} tile(s) had a histogram "
                f"separating at >= {min_separation}; fewer than the {min_tiles} "
                "required, so no threshold is supported by these data"
            ),
            tiles_tested=tested,
            tiles_accepted=len(accepted),
        )

    pooled = np.concatenate(accepted)
    threshold = otsu_threshold(pooled, bins=bins, value_range=value_range)
    measure = bimodality(pooled, threshold, min_separation=min_separation)

    if not measure.is_bimodal:
        return ThresholdDecision(
            value=None,
            method="tiled_otsu",
            available=False,
            reason=(
                f"{len(accepted)} tile(s) passed individually, but their pooled "
                f"histogram separates at only {measure.separation:.2f} "
                f"(< {min_separation})"
            ),
            bimodality=measure,
            tiles_tested=tested,
            tiles_accepted=len(accepted),
        )

    return ThresholdDecision(
        value=threshold,
        method="tiled_otsu",
        available=True,
        bimodality=measure,
        tiles_tested=tested,
        tiles_accepted=len(accepted),
    )


def sar_water_threshold(
    backscatter_db: np.ndarray,
    cfg: "Config",
    *,
    valid: np.ndarray | None = None,
) -> ThresholdDecision:
    """The configured Sentinel-1 water threshold for one scene.

    Dispatches on ``detection.water.sar.threshold_method``. Where a data-driven
    method finds no support in the histogram, the configured
    ``fixed_threshold_db`` is used only if one has been *explicitly set*; it is
    ``None`` by default, and the decision is then an honest ``unavailable``.
    """
    sar_cfg: SARWaterConfig = cfg.detection.water.sar
    method = sar_cfg.threshold_method
    search_range = (
        float(sar_cfg.search_range_db[0]),
        float(sar_cfg.search_range_db[1]),
    )

    if method == "fixed":
        # The schema guarantees the value is set when this method is chosen.
        return ThresholdDecision(
            value=float(sar_cfg.fixed_threshold_db),
            method="fixed",
            available=True,
            reason="configured threshold, not derived from these data",
        )

    if method == "tiled_otsu":
        decision = tiled_otsu_threshold(
            backscatter_db,
            valid=valid,
            tile_px=sar_cfg.tile_px,
            bins=sar_cfg.histogram_bins,
            value_range=search_range,
            min_separation=sar_cfg.min_separation,
            min_tile_valid_fraction=sar_cfg.min_tile_valid_fraction,
            min_tiles=sar_cfg.min_tiles,
        )
    else:  # "otsu" -- a single whole-image histogram
        data = np.asarray(backscatter_db, dtype=np.float64)
        selection = np.isfinite(data)
        if valid is not None:
            selection &= np.asarray(valid, dtype=bool)
        samples = data[selection]
        try:
            candidate = otsu_threshold(
                samples, bins=sar_cfg.histogram_bins, value_range=search_range
            )
        except ValueError as exc:
            decision = ThresholdDecision(
                value=None, method="otsu", available=False, reason=str(exc)
            )
        else:
            measure = bimodality(
                samples, candidate, min_separation=sar_cfg.min_separation
            )
            decision = ThresholdDecision(
                value=candidate if measure.is_bimodal else None,
                method="otsu",
                available=measure.is_bimodal,
                bimodality=measure,
                reason=(
                    None
                    if measure.is_bimodal
                    else (
                        f"whole-image histogram separates at only "
                        f"{measure.separation:.2f} (< {sar_cfg.min_separation}); "
                        "water is probably too small a fraction of this scene "
                        "for a global threshold (Chini et al. 2017)"
                    )
                ),
            )

    if decision.available or sar_cfg.fixed_threshold_db is None:
        log.info("SAR water threshold -- %s", decision.describe())
        return decision

    log.warning(
        "%s found no supported threshold (%s); falling back to the configured "
        "fixed_threshold_db = %.2f dB",
        decision.method,
        decision.reason,
        sar_cfg.fixed_threshold_db,
    )
    return ThresholdDecision(
        value=float(sar_cfg.fixed_threshold_db),
        method=f"{decision.method}->fixed",
        available=True,
        reason=f"fell back to the configured threshold: {decision.reason}",
        bimodality=decision.bimodality,
        tiles_tested=decision.tiles_tested,
        tiles_accepted=decision.tiles_accepted,
    )


# --------------------------------------------------------------------------- #
# Masks
# --------------------------------------------------------------------------- #


@dataclass(frozen=True)
class WaterEvidence:
    """A binary water mask from one source, with the pixels it could judge.

    ``water`` and ``valid`` are both needed. ``~water`` means "not water
    *where it could be observed*"; outside ``valid`` the source says nothing,
    and conflating the two would turn a data gap into a dry-land observation.
    """

    water: np.ndarray
    valid: np.ndarray
    source: str
    method: str
    threshold: ThresholdDecision | None = None
    stats: dict[str, float] = field(default_factory=dict)

    #: The mask before the snow screen was applied -- the pure index-only mask
    #: that brief Section 7.3 requires Phase 4's false-water reduction to be
    #: measured against. ``None`` where no screen ran, in which case ``water``
    #: is already index-only.
    pre_screen_water: np.ndarray | None = None

    @property
    def available(self) -> bool:
        return bool(self.valid.any())

    @property
    def water_pixels(self) -> int:
        return int(np.count_nonzero(self.water))

    @property
    def water_fraction_of_valid(self) -> float:
        valid_count = int(np.count_nonzero(self.valid))
        return float(self.water_pixels / valid_count) if valid_count else 0.0

    def describe(self) -> str:
        return (
            f"{self.source}: {self.water_pixels} water px "
            f"({self.water_fraction_of_valid * 100:.2f}% of "
            f"{int(np.count_nonzero(self.valid))} valid px) via {self.method}"
        )


def optical_water_mask(
    green: np.ndarray,
    nir: np.ndarray,
    swir1: np.ndarray,
    cfg: "Config",
    *,
    invalid: np.ndarray | None = None,
) -> WaterEvidence:
    """Index-based water mask from Sentinel-2 (brief, Section 7.2).

    Applies **no** shadow reasoning whatsoever: that is Phase 4's job, and this
    mask is the baseline it is measured against. A snow screen *is* applied
    when configured, because MNDWI and NDSI are the same expression and so
    cannot tell snow from water at all (see below); the mask as it stood before
    that screen is kept in ``pre_screen_water`` so the index-only baseline
    remains available.

    The snow screen is the water/snow discriminator of the MODIS snow-mapping
    algorithm: water reflects less than 11% in the near infrared while snow
    reflects far more, which is the test that algorithm uses to stop water
    being mapped as snow (Hall et al. 1995; Hall et al. 2002). Here it runs in
    the other direction, to stop snow being mapped as water.

    Args:
        green, nir, swir1: Sentinel-2 B3, B8 and B11 **as stored**, i.e. scaled
            integers. ``detection.water.optical.reflectance_scale`` converts
            them to reflectance for the snow screen; the indices themselves are
            scale-invariant.
        invalid: pixels carrying no trustworthy reflectance -- cloud, cloud
            shadow, defective. Pass ``CloudMasks.unusable``. Terrain shadow
            must **not** be passed here: a terrain-shadowed pixel is a real
            observation of the ground, and excluding it would hide exactly the
            false water this project exists to study.
    """
    optical_cfg = cfg.detection.water.optical

    ndwi_values = ndwi(green, nir)
    mndwi_values = mndwi(green, swir1)

    ndwi_water = ndwi_values > optical_cfg.ndwi_threshold
    mndwi_water = mndwi_values > optical_cfg.mndwi_threshold

    rule = optical_cfg.rule
    if rule == "ndwi":
        water = ndwi_water
        measurable = np.isfinite(ndwi_values)
    elif rule == "mndwi":
        water = mndwi_water
        measurable = np.isfinite(mndwi_values)
    elif rule == "both_and":
        water = ndwi_water & mndwi_water
        measurable = np.isfinite(ndwi_values) & np.isfinite(mndwi_values)
    elif rule == "both_or":
        water = ndwi_water | mndwi_water
        measurable = np.isfinite(ndwi_values) & np.isfinite(mndwi_values)
    else:  # pragma: no cover - the schema restricts the literal
        raise ValueError(f"unknown optical rule: {rule!r}")

    valid = measurable
    if invalid is not None:
        valid = valid & ~np.asarray(invalid, dtype=bool)

    index_only = water & valid

    method = (
        f"{rule} > "
        f"{optical_cfg.mndwi_threshold if 'mndwi' in rule else optical_cfg.ndwi_threshold}"
        if rule in {"ndwi", "mndwi"}
        else f"{rule} (NDWI > {optical_cfg.ndwi_threshold}, "
        f"MNDWI > {optical_cfg.mndwi_threshold})"
    )
    stats = {
        "ndwi_water_fraction": float(np.mean(ndwi_water & valid)),
        "mndwi_water_fraction": float(np.mean(mndwi_water & valid)),
        "valid_fraction": float(np.mean(valid)),
        "index_only_px": float(np.count_nonzero(index_only)),
    }

    nir_ceiling = optical_cfg.snow_screen_nir_max_reflectance
    if nir_ceiling is None:
        screened = index_only
        pre_screen = None
    else:
        nir_reflectance = np.asarray(nir, dtype=np.float64) * optical_cfg.reflectance_scale
        not_snow = nir_reflectance < nir_ceiling
        screened = index_only & not_snow
        pre_screen = index_only
        removed = int(np.count_nonzero(index_only & ~not_snow))
        stats["snow_screened_px"] = float(removed)
        method += f", NIR < {nir_ceiling} reflectance (snow screen)"
        log.info(
            "snow screen (NIR < %.2f reflectance, Hall et al. 1995) removed "
            "%d of %d index-only water pixels (%.1f%%)",
            nir_ceiling,
            removed,
            int(np.count_nonzero(index_only)),
            100.0 * removed / max(int(np.count_nonzero(index_only)), 1),
        )

    evidence = WaterEvidence(
        water=screened,
        valid=valid,
        source="optical",
        method=method,
        stats=stats,
        pre_screen_water=pre_screen,
    )
    log.info("optical water -- %s", evidence.describe())
    return evidence


def sar_water_mask(
    backscatter_db: np.ndarray,
    cfg: "Config",
    *,
    invalid: np.ndarray | None = None,
    decision: ThresholdDecision | None = None,
) -> WaterEvidence:
    """Water mask from Sentinel-1 backscatter: low dB is water-like.

    Args:
        invalid: pixels where the SAR measurement itself is not usable -- no
            data, or outside the swath. Layover and shadow are **not** passed
            here: Section 7.3 makes a SAR-water-like pixel inside the
            layover/shadow mask *uncertain*, which is a Phase 4 judgement, so
            this stage reports the raw SAR evidence and leaves it intact.
        decision: a threshold already derived (so it is not recomputed when the
            same scene feeds several calls). Derived from the data if omitted.
    """
    data = np.asarray(backscatter_db, dtype=np.float64)
    measurable = np.isfinite(data)
    if invalid is not None:
        measurable = measurable & ~np.asarray(invalid, dtype=bool)

    if decision is None:
        decision = sar_water_threshold(data, cfg, valid=measurable)

    if not decision.available:
        # No threshold means no evidence either way -- not "no water". The valid
        # mask is empty so that nothing downstream can read this as dry land.
        evidence = WaterEvidence(
            water=np.zeros(data.shape, dtype=bool),
            valid=np.zeros(data.shape, dtype=bool),
            source="sar",
            method=f"{decision.method} (unavailable)",
            threshold=decision,
            stats={"valid_fraction": 0.0},
        )
        log.warning("SAR water mask unavailable: %s", decision.reason)
        return evidence

    water = (data <= decision.value) & measurable
    evidence = WaterEvidence(
        water=water,
        valid=measurable,
        source="sar",
        method=f"{cfg.detection.water.sar.band} <= {decision.value:.2f} dB "
        f"({decision.method})",
        threshold=decision,
        stats={"valid_fraction": float(np.mean(measurable))},
    )
    log.info("SAR water -- %s", evidence.describe())
    return evidence


@dataclass(frozen=True)
class WaterDetection:
    """The Phase 3 result: per-source evidence plus the combined mask."""

    water: np.ndarray
    valid: np.ndarray
    combine: str
    optical: WaterEvidence | None = None
    sar: WaterEvidence | None = None

    @property
    def water_pixels(self) -> int:
        return int(np.count_nonzero(self.water))

    def agreement(self) -> dict[str, float] | None:
        """How the two sources compare where both could judge.

        ``None`` unless both sources are present and valid somewhere. The
        intersection-over-union is reported over the mutually valid area only,
        so a data gap in one source cannot look like a disagreement.
        """
        if self.optical is None or self.sar is None:
            return None
        both_valid = self.optical.valid & self.sar.valid
        if not both_valid.any():
            return None

        optical_water = self.optical.water & both_valid
        sar_water = self.sar.water & both_valid
        union = np.count_nonzero(optical_water | sar_water)
        intersection = np.count_nonzero(optical_water & sar_water)
        return {
            "mutually_valid_px": float(np.count_nonzero(both_valid)),
            "optical_only_px": float(np.count_nonzero(optical_water & ~sar_water)),
            "sar_only_px": float(np.count_nonzero(sar_water & ~optical_water)),
            "both_px": float(intersection),
            "iou": float(intersection / union) if union else 0.0,
        }

    def summary(self) -> str:
        parts = [e.describe() for e in (self.optical, self.sar) if e is not None]
        parts.append(
            f"combined ({self.combine}): {self.water_pixels} px over "
            f"{int(np.count_nonzero(self.valid))} valid px"
        )
        return " | ".join(parts)


def combine_evidence(
    optical: WaterEvidence | None,
    sar: WaterEvidence | None,
    cfg: "Config",
) -> WaterDetection:
    """Combine per-source masks per ``detection.water.combine``.

    ``union`` is the configured default and is a baseline choice, not a claim
    that union is the most accurate rule: it is the most inclusive combination,
    so it presents Phase 4 with the full set of candidate false water and makes
    the reduction measurable.

    For ``union``, a pixel is valid where *either* source could judge. For
    ``intersection``, only where *both* could -- an intersection over a pixel
    one source never saw would silently mean "not water".
    """
    mode = cfg.detection.water.combine

    def _require(evidence: WaterEvidence | None, name: str) -> WaterEvidence:
        if evidence is None:
            raise ValueError(
                f"combine={mode!r} needs {name} evidence, but none was supplied"
            )
        return evidence

    if mode == "optical":
        chosen = _require(optical, "optical")
        water, valid = chosen.water, chosen.valid
    elif mode == "sar":
        chosen = _require(sar, "sar")
        water, valid = chosen.water, chosen.valid
    elif mode == "union":
        left = _require(optical, "optical")
        right = _require(sar, "sar")
        valid = left.valid | right.valid
        water = (left.water | right.water) & valid
    elif mode == "intersection":
        left = _require(optical, "optical")
        right = _require(sar, "sar")
        valid = left.valid & right.valid
        water = left.water & right.water & valid
    else:  # pragma: no cover - the schema restricts the literal
        raise ValueError(f"unknown combine mode: {mode!r}")

    detection = WaterDetection(
        water=water, valid=valid, combine=mode, optical=optical, sar=sar
    )
    log.info("water detection -- %s", detection.summary())
    return detection


# --------------------------------------------------------------------------- #
# Water bodies
# --------------------------------------------------------------------------- #

#: Columns every water-body frame carries (brief, Section 7.2: area, perimeter,
#: centroid and boundary per water body).
WATER_BODY_COLUMNS = (
    "body_id",
    "area_m2",
    "perimeter_m",
    "pixel_count",
    "centroid_x",
    "centroid_y",
    "centroid_lon",
    "centroid_lat",
    "geometry",
)


def water_bodies(
    mask: np.ndarray,
    transform: Any,
    crs: Any,
    *,
    min_area_m2: float = 0.0,
    connectivity: int = 8,
) -> "gpd.GeoDataFrame":
    """Per-water-body polygons with area, perimeter and centroid.

    Areas and perimeters come from the projected geometry, so ``crs`` must be
    projected -- :func:`utils.crs.ensure_projected` refuses a geographic one
    (brief, Section 6: never measure in degrees). Polygon area accounts for
    interior rings, so an island inside a lake is not counted as water.

    Args:
        min_area_m2: bodies smaller than this are dropped, and the count is
            logged rather than discarded silently.
        connectivity: 4 or 8. 8 keeps a diagonal channel as a single body.

    Returns:
        A GeoDataFrame with :data:`WATER_BODY_COLUMNS`, sorted largest first and
        with ``body_id`` assigned in that order. The ``geometry`` column holds
        the polygon; ``boundaries`` derives the outline from it.
    """
    import geopandas as gpd
    import rasterio.features
    from shapely.geometry import shape

    from utils.crs import ensure_projected

    projected = ensure_projected(crs, context="water-body area and perimeter")
    if connectivity not in (4, 8):
        raise ValueError(f"connectivity must be 4 or 8, got {connectivity}")

    binary = np.asarray(mask, dtype=bool)
    records: list[dict[str, Any]] = []

    # uint8 because rasterio.features.shapes does not accept a boolean array.
    for geometry, value in rasterio.features.shapes(
        binary.astype(np.uint8),
        mask=binary,
        transform=transform,
        connectivity=int(connectivity),
    ):
        if not value:
            continue
        polygon = shape(geometry)
        records.append({"geometry": polygon, "area_m2": float(polygon.area)})

    dropped = 0
    kept: list[dict[str, Any]] = []
    for record in records:
        if record["area_m2"] < min_area_m2:
            dropped += 1
            continue
        kept.append(record)

    if dropped:
        log.info(
            "dropped %d water body/bodies below the %.0f m^2 minimum "
            "(kept %d)", dropped, min_area_m2, len(kept)
        )

    if not kept:
        empty = gpd.GeoDataFrame(
            {name: [] for name in WATER_BODY_COLUMNS if name != "geometry"},
            geometry=[],
            crs=projected,
        )
        log.info("no water bodies at or above %.0f m^2", min_area_m2)
        return empty[list(WATER_BODY_COLUMNS)]

    kept.sort(key=lambda record: record["area_m2"], reverse=True)

    from utils.crs import pixel_area_m2

    cell_area = pixel_area_m2(transform, projected)

    frame = gpd.GeoDataFrame(
        {
            "body_id": [index + 1 for index in range(len(kept))],
            "area_m2": [record["area_m2"] for record in kept],
            "perimeter_m": [record["geometry"].length for record in kept],
            # Derived from area, not counted again: the polygon is built from
            # whole pixels, so the two agree by construction.
            "pixel_count": [
                int(round(record["area_m2"] / cell_area)) for record in kept
            ],
            "centroid_x": [record["geometry"].centroid.x for record in kept],
            "centroid_y": [record["geometry"].centroid.y for record in kept],
        },
        geometry=[record["geometry"] for record in kept],
        crs=projected,
    )

    # Geographic centroid for mapping and for the sites table, converted from
    # the projected centroid rather than computed in degrees.
    centroids_wgs84 = (
        frame.set_geometry(gpd.points_from_xy(frame["centroid_x"], frame["centroid_y"]))
        .set_crs(projected)
        .to_crs("EPSG:4326")
        .geometry
    )
    frame["centroid_lon"] = centroids_wgs84.x.to_numpy()
    frame["centroid_lat"] = centroids_wgs84.y.to_numpy()

    log.info(
        "%d water body/bodies, largest %.0f m^2 (%.3f km^2), total %.0f m^2",
        len(frame),
        frame["area_m2"].iloc[0],
        frame["area_m2"].iloc[0] / 1e6,
        frame["area_m2"].sum(),
    )
    return frame[list(WATER_BODY_COLUMNS)]


def boundaries(bodies: "gpd.GeoDataFrame") -> "gpd.GeoDataFrame":
    """The water-body outlines (brief, Section 7.2: "boundary" per body).

    Kept as a derived view rather than a stored column: the boundary is exactly
    the polygon's exterior, and storing both would let them drift apart.
    """
    outlined = bodies.copy()
    outlined["geometry"] = bodies.geometry.boundary
    return outlined
