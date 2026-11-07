"""Lake depth and volume, under the strict rules of brief Section 8.

**Depth is never estimated from image colour.** Every value this module emits
is traceable to exactly one branch, the branch is recorded alongside the
value, and a quantity that cannot be traced to a branch is returned as
``unavailable`` with a reason rather than as a number.

The three branches
------------------
``A`` -- the lake formed **after** the DEM was acquired, so the DEM shows the
    pre-lake valley floor. ``depth = WSE - DEM`` per pixel, clipped at 0;
    ``volume = sum(depth x pixel area)``. Marked ``estimated``, with
    uncertainty propagated from the DEM's vertical error and the WSE spread.

``B`` -- the lake already existed when the DEM was acquired, so the DEM
    recorded the **water surface** and the bed is unknown. Returns
    ``unavailable``, reason *DEM records water surface; no bathymetry*. An
    empirical area-volume relationship may be added only with approval and a
    cited formula (see ``branch_b_empirical_formula``).

``C`` -- insufficient data: no reliable shoreline, a cloudy observation, or
    evidence that cannot establish which of A or B applies. Returns
    ``unavailable`` with the reason.

Why the branch test is not just a date comparison
-------------------------------------------------
Comparing the lake's first observation against the DEM epoch is necessary but
not sufficient -- it fails whenever the first observation is itself late, or
the epoch is uncertain. This module therefore also tests the DEM *directly*,
using two signatures of a recorded water surface:

1. **Flatness.** Copernicus GLO-30 flattens water bodies to a constant
   elevation. Measured over Tsho Rolpa the DEM inside the lake has a standard
   deviation of **0.00 m** across 15 501 pixels; a real valley floor never
   does.
2. **A zero height-error mask.** GLO-30's HEM band is 0.00 m inside flattened
   water. That is not a claim of perfect accuracy -- it means no measurement
   was made there, which is itself evidence for Branch B.

Why this matters, measured rather than asserted: applying the Branch A formula
to Tsho Rolpa -- a Branch B lake -- yields 14.3, 21.7 or 30.9 million m3 purely
according to whether the shoreline ring is 10, 30 or 50 m wide. A plausible
number, varying by a factor of 2.2 with an arbitrary parameter, traceable to
nothing. That is the failure mode Section 8 exists to prevent.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date
from typing import TYPE_CHECKING, Any

import numpy as np

from preprocessing.cloud_mask import dilate_square
from utils.logging import get_logger

if TYPE_CHECKING:  # pragma: no cover
    from config.schema import Config

log = get_logger(__name__)

BRANCH_A = "A"
BRANCH_B = "B"
BRANCH_C = "C"

#: Section 10 vocabulary.
VALUE_TYPE_ESTIMATED = "estimated"
VALUE_TYPE_UNAVAILABLE = "unavailable"
VALUE_TYPE_EMPIRICAL = "empirical"

#: Reason text required by Section 8 for Branch B.
BRANCH_B_REASON = "DEM records water surface; no bathymetry"

#: IQR of a normal distribution in units of sigma, for converting a spread.
IQR_TO_SIGMA = 1.349
MAD_TO_SIGMA = 1.4826


@dataclass(frozen=True)
class WaterSurfaceElevation:
    """WSE read from a ring just outside the water polygon."""

    wse_m: float
    spread_m: float
    samples: int
    statistic: str
    spread_statistic: str
    buffer_m: float

    def describe(self) -> str:
        return (
            f"WSE {self.wse_m:.2f} m +/- {self.spread_m:.2f} m "
            f"({self.statistic} of {self.samples} shoreline samples in a "
            f"{self.buffer_m:.0f} m ring, spread as {self.spread_statistic})"
        )


@dataclass(frozen=True)
class BranchDecision:
    """Which branch applies, and the evidence that chose it."""

    branch: str
    reason: str
    evidence: dict[str, Any] = field(default_factory=dict)

    def describe(self) -> str:
        return f"Branch {self.branch}: {self.reason}"


@dataclass(frozen=True)
class DepthVolumeEstimate:
    """A depth/volume result, or a documented refusal to produce one.

    Field names mirror the ``depth_volume_estimates`` table of brief Section
    10 so that storing a result is a direct mapping, not a translation.
    """

    branch: str
    value_type: str
    method: str
    wse_m: float | None = None
    wse_uncertainty_m: float | None = None
    mean_depth_m: float | None = None
    max_depth_m: float | None = None
    volume_m3: float | None = None
    volume_low_m3: float | None = None
    volume_high_m3: float | None = None
    area_m2: float | None = None
    reason: str | None = None
    evidence: dict[str, Any] = field(default_factory=dict)

    @property
    def available(self) -> bool:
        return self.value_type != VALUE_TYPE_UNAVAILABLE

    def as_record(self, site_id: Any, obs_date: date | str) -> dict[str, Any]:
        """A row for the ``depth_volume_estimates`` table (Section 10)."""
        return {
            "site_id": site_id,
            "obs_date": str(obs_date),
            "branch": self.branch,
            "wse_m": self.wse_m,
            "wse_uncertainty_m": self.wse_uncertainty_m,
            "mean_depth_m": self.mean_depth_m,
            "max_depth_m": self.max_depth_m,
            "volume_m3": self.volume_m3,
            "volume_low_m3": self.volume_low_m3,
            "volume_high_m3": self.volume_high_m3,
            "value_type": self.value_type,
            "method": self.method,
            "notes": self.reason,
        }

    def describe(self) -> str:
        if not self.available:
            return f"Branch {self.branch}: {self.value_type} -- {self.reason}"
        return (
            f"Branch {self.branch} ({self.value_type}): mean depth "
            f"{self.mean_depth_m:.2f} m, max {self.max_depth_m:.2f} m, volume "
            f"{self.volume_m3 / 1e6:.3f} million m3 "
            f"[{self.volume_low_m3 / 1e6:.3f}-{self.volume_high_m3 / 1e6:.3f}]"
        )


def shoreline_ring(water: np.ndarray, buffer_px: int) -> np.ndarray:
    """The ring of pixels just outside a water mask."""
    mask = np.asarray(water, dtype=bool)
    if buffer_px < 1:
        raise ValueError(f"buffer must be at least one pixel, got {buffer_px}")
    return dilate_square(mask, buffer_px) & ~mask


def water_surface_elevation(
    dem: np.ndarray,
    water: np.ndarray,
    cfg: "Config",
    *,
    cellsize_m: float,
    valid: np.ndarray | None = None,
) -> WaterSurfaceElevation | None:
    """WSE from the shoreline ring, or ``None`` if too few samples.

    Brief, Section 8: the median DEM elevation along a buffer just outside the
    water polygon, with its spread stored as uncertainty.

    The median is the prescribed statistic, but note it is biased **upward**
    on a steep shoreline: every sample in the ring sits upslope of the
    waterline. ``p25`` and ``min`` are available for sensitivity testing.
    """
    settings = cfg.analysis.depth_volume.shoreline
    buffer_px = max(1, int(round(settings.buffer_m / cellsize_m)))

    ring = shoreline_ring(water, buffer_px)
    elevations = np.asarray(dem, dtype=np.float64)
    selection = ring & np.isfinite(elevations)
    if valid is not None:
        selection &= np.asarray(valid, dtype=bool)

    samples = elevations[selection]
    if samples.size < settings.min_samples:
        log.warning(
            "only %d shoreline sample(s), fewer than the %d required: no WSE",
            samples.size,
            settings.min_samples,
        )
        return None

    if settings.statistic == "median":
        wse = float(np.median(samples))
    elif settings.statistic == "p25":
        wse = float(np.percentile(samples, 25))
    else:
        wse = float(samples.min())

    if settings.spread_statistic == "iqr":
        q1, q3 = np.percentile(samples, [25, 75])
        spread = float(q3 - q1)
    elif settings.spread_statistic == "std":
        spread = float(samples.std())
    else:
        spread = float(np.median(np.abs(samples - np.median(samples))) * MAD_TO_SIGMA)

    result = WaterSurfaceElevation(
        wse_m=wse,
        spread_m=spread,
        samples=int(samples.size),
        statistic=settings.statistic,
        spread_statistic=settings.spread_statistic,
        buffer_m=float(buffer_px * cellsize_m),
    )
    log.info("%s", result.describe())
    return result


def decide_branch(
    cfg: "Config",
    dem: np.ndarray,
    water: np.ndarray,
    *,
    wse: WaterSurfaceElevation | None,
    dem_water_mask: np.ndarray | None = None,
    dem_height_error: np.ndarray | None = None,
    dem_epoch_end: date | None = None,
    lake_first_observed: date | None = None,
    observation_is_usable: bool = True,
) -> BranchDecision:
    """Choose branch A, B or C, recording every line of evidence considered."""
    settings = cfg.analysis.depth_volume.branch
    mask = np.asarray(water, dtype=bool)
    elevations = np.asarray(dem, dtype=np.float64)
    evidence: dict[str, Any] = {}

    if not observation_is_usable:
        return BranchDecision(
            BRANCH_C, "the observation is not usable (cloud or no valid data)", evidence
        )
    if not mask.any():
        return BranchDecision(BRANCH_C, "no water polygon to measure", evidence)
    if wse is None:
        return BranchDecision(
            BRANCH_C,
            "no reliable shoreline: too few valid DEM samples around the water body",
            evidence,
        )

    inside = elevations[mask & np.isfinite(elevations)]
    if inside.size == 0:
        return BranchDecision(BRANCH_C, "no DEM values inside the water body", evidence)

    # --- Branch B evidence 1: the DEM is flat inside the lake --------------- #
    flat_std = float(inside.std())
    evidence["dem_std_inside_m"] = flat_std
    evidence["dem_median_inside_m"] = float(np.median(inside))
    is_flat = flat_std <= settings.flat_std_tolerance_m

    # --- Branch B evidence 2: the DEM's own water mask covers the lake ------ #
    overlap: float | None = None
    if dem_water_mask is not None:
        dem_water = np.asarray(dem_water_mask, dtype=bool)
        overlap = float(np.count_nonzero(dem_water & mask) / np.count_nonzero(mask))
        evidence["dem_water_mask_overlap"] = overlap

    # --- Branch B evidence 3: the height-error mask is zero inside ---------- #
    if dem_height_error is not None:
        errors = np.asarray(dem_height_error, dtype=np.float64)[mask]
        errors = errors[np.isfinite(errors)]
        if errors.size:
            zero_error = float(np.count_nonzero(errors == 0.0) / errors.size)
            evidence["zero_height_error_fraction"] = zero_error

    # --- dates --------------------------------------------------------------- #
    if dem_epoch_end is not None and lake_first_observed is not None:
        postdates = lake_first_observed > dem_epoch_end
        evidence["lake_first_observed"] = str(lake_first_observed)
        evidence["dem_epoch_end"] = str(dem_epoch_end)
        evidence["lake_postdates_dem"] = postdates
    else:
        postdates = None

    # --- decision ------------------------------------------------------------ #
    # Direct evidence from the DEM outranks the date comparison: if the DEM
    # plainly recorded a water surface, no date can make its bed knowable.
    if is_flat:
        return BranchDecision(
            BRANCH_B,
            (
                f"{BRANCH_B_REASON} -- DEM elevation inside the lake has a "
                f"standard deviation of {flat_std:.3f} m, at or below the "
                f"{settings.flat_std_tolerance_m} m flatness tolerance, which is "
                "the signature of a flattened water body"
            ),
            evidence,
        )

    if overlap is not None and overlap >= settings.dem_water_overlap_fraction:
        return BranchDecision(
            BRANCH_B,
            (
                f"{BRANCH_B_REASON} -- the DEM product's own water-body mask "
                f"covers {overlap:.1%} of the lake"
            ),
            evidence,
        )

    implied = float(np.mean(np.clip(wse.wse_m - inside, 0.0, None)))
    evidence["implied_mean_depth_m"] = implied

    if postdates is True:
        if implied < settings.min_depth_for_branch_a_m:
            return BranchDecision(
                BRANCH_C,
                (
                    f"the lake postdates the DEM, but the implied mean depth is "
                    f"only {implied:.2f} m (below the "
                    f"{settings.min_depth_for_branch_a_m} m minimum), so the DEM "
                    "and the water surface are effectively the same surface and "
                    "Branch A would be measuring noise"
                ),
                evidence,
            )
        return BranchDecision(
            BRANCH_A,
            (
                f"the lake was first observed on {lake_first_observed}, after the "
                f"DEM epoch ended on {dem_epoch_end}, and the DEM inside the lake "
                f"is not flat (sd {flat_std:.2f} m), so it records the pre-lake "
                "valley floor"
            ),
            evidence,
        )

    if postdates is False:
        return BranchDecision(
            BRANCH_B,
            (
                f"{BRANCH_B_REASON} -- the lake was already observed on "
                f"{lake_first_observed}, within the DEM epoch ending "
                f"{dem_epoch_end}"
            ),
            evidence,
        )

    return BranchDecision(
        BRANCH_C,
        (
            "cannot establish whether the lake predates the DEM: no first "
            "observation date or no DEM epoch was supplied, and the DEM inside "
            f"the lake is not flat enough (sd {flat_std:.2f} m) to settle it"
        ),
        evidence,
    )


def estimate_depth_volume(
    cfg: "Config",
    water: np.ndarray,
    dem: np.ndarray,
    *,
    cellsize_m: float,
    pixel_area_m2: float,
    dem_water_mask: np.ndarray | None = None,
    dem_height_error: np.ndarray | None = None,
    dem_epoch_end: date | None = None,
    lake_first_observed: date | None = None,
    observation_is_usable: bool = True,
    dem_valid: np.ndarray | None = None,
) -> DepthVolumeEstimate:
    """Depth and volume for one lake on one date, per brief Section 8.

    Args:
        water: the lake mask.
        dem: elevation, in metres, on the same grid.
        pixel_area_m2: from :func:`utils.crs.pixel_area_m2`, which refuses a
            geographic CRS -- so an area in square degrees cannot reach here.
        dem_height_error: GLO-30 HEM. Used for the uncertainty bounds when
            ``dem_vertical_error_m`` is not configured.
        observation_is_usable: ``False`` for a cloudy or empty observation,
            which is Branch C by definition.

    Returns:
        A :class:`DepthVolumeEstimate`. For branches B and C every numeric
        field except ``wse_m``/``area_m2`` is ``None`` -- deliberately, so that
        an unavailable depth cannot be mistaken for zero.
    """
    settings = cfg.analysis.depth_volume

    if settings.branch_b_empirical_formula is not None:
        raise NotImplementedError(
            "branch_b_empirical_formula is set to "
            f"{settings.branch_b_empirical_formula!r}, but no empirical "
            "area-volume relationship has been approved for this project. The "
            "brief (Section 8) requires approval and a cited formula, and that "
            "the result be reported as 'empirical' with wide uncertainty "
            "bounds. Refusing rather than inventing one."
        )

    mask = np.asarray(water, dtype=bool)
    area = float(np.count_nonzero(mask) * pixel_area_m2)

    wse = (
        water_surface_elevation(dem, mask, cfg, cellsize_m=cellsize_m, valid=dem_valid)
        if mask.any() and observation_is_usable
        else None
    )

    decision = decide_branch(
        cfg,
        dem,
        mask,
        wse=wse,
        dem_water_mask=dem_water_mask,
        dem_height_error=dem_height_error,
        dem_epoch_end=dem_epoch_end,
        lake_first_observed=lake_first_observed,
        observation_is_usable=observation_is_usable,
    )
    log.info("%s", decision.describe())

    if decision.branch != BRANCH_A:
        estimate = DepthVolumeEstimate(
            branch=decision.branch,
            value_type=VALUE_TYPE_UNAVAILABLE,
            method="brief Section 8 branch logic",
            wse_m=wse.wse_m if wse else None,
            wse_uncertainty_m=wse.spread_m if wse else None,
            area_m2=area,
            reason=decision.reason,
            evidence=decision.evidence,
        )
        log.info("%s", estimate.describe())
        return estimate

    # ---- Branch A ---------------------------------------------------------- #
    assert wse is not None  # decide_branch returns C without a WSE
    elevations = np.asarray(dem, dtype=np.float64)

    # A lake can be part Branch A and part Branch B, and Section 8's branches
    # are per-lake.
    #
    # A barrier lake routinely floods new ground AND deepens the river it dams.
    # Over the new ground the DEM holds the pre-lake surface, so Branch A is
    # exactly right. Over the old channel it recorded a WATER SURFACE, so the
    # bed is unknown -- Branch B -- and `WSE - DEM` there measures the RISE in
    # water level, not the depth.
    #
    # The GLO-30 height-error mask distinguishes them per pixel: a value of
    # exactly zero means no height was measured, which over water is the
    # product stating it recorded a surface rather than a bed. On the Baige
    # lake it reads 62.8% zero against 64.2% of the lake being pre-existing
    # river -- an independent agreement to within 1.4 points. The mask was
    # already being read into the evidence dictionary and then discarded.
    #
    # So Branch A is computed over the measured part only, and the rest is
    # declared unmeasurable. The volume is then a LOWER BOUND on the
    # impoundment: it omits whatever the river already held below its DEM-epoch
    # surface. That is traceable to Section 8 pixel by pixel, which summing the
    # two together was not.
    measurable = mask.copy()
    branch_b_fraction = 0.0
    hem_split = False
    if settings.branch.use_height_error_mask and dem_height_error is not None:
        hem = np.asarray(dem_height_error, dtype=np.float64)
        recorded_surface = mask & np.isfinite(hem) & (hem == 0.0)
        total_px = int(np.count_nonzero(mask))
        if total_px:
            branch_b_fraction = float(
                np.count_nonzero(recorded_surface) / total_px
            )
        if branch_b_fraction >= settings.branch.min_branch_b_fraction_to_split:
            measurable = mask & ~recorded_surface
            hem_split = True
            log.info(
                "height-error mask splits this lake: %.1f%% of it has a "
                "GLO-30 height error of exactly zero, meaning the DEM "
                "recorded a water surface there and the bed is unknown "
                "(Branch B). Branch A is computed over the remaining %.1f%% "
                "and the volume is a LOWER BOUND",
                100 * branch_b_fraction,
                100 * (1.0 - branch_b_fraction),
            )

    if hem_split and not measurable.any():
        estimate = DepthVolumeEstimate(
            branch=BRANCH_B,
            value_type=VALUE_TYPE_UNAVAILABLE,
            method="brief Section 8 branch logic, per-pixel via the GLO-30 HEM",
            wse_m=wse.wse_m,
            wse_uncertainty_m=wse.spread_m,
            area_m2=area,
            reason=(
                f"{BRANCH_B_REASON} -- the GLO-30 height-error mask is zero "
                f"across the entire lake, so the DEM recorded a water surface "
                f"everywhere and no pixel has a known bed"
            ),
            evidence={**decision.evidence, "branch_b_fraction": branch_b_fraction},
        )
        log.info("%s", estimate.describe())
        return estimate

    depth = np.clip(wse.wse_m - elevations, 0.0, None)
    depth = np.where(measurable & np.isfinite(elevations), depth, 0.0)

    if settings.dem_vertical_error_m is not None:
        dem_error = float(settings.dem_vertical_error_m)
        error_field = np.full(elevations.shape, dem_error)
        error_source = f"configured {dem_error} m"
    elif dem_height_error is not None:
        error_field = np.asarray(dem_height_error, dtype=np.float64)
        error_field = np.where(np.isfinite(error_field), error_field, 0.0)
        error_source = "GLO-30 HEM band"
    else:
        error_field = np.zeros(elevations.shape)
        error_source = "none supplied (uncertainty from the WSE spread only)"

    # Bounds: the lowest plausible water surface over the highest plausible
    # bed, and the reverse. Both error terms push the same way, so this is a
    # conservative envelope rather than a statistical confidence interval.
    low = np.clip((wse.wse_m - wse.spread_m) - (elevations + error_field), 0.0, None)
    high = np.clip((wse.wse_m + wse.spread_m) - (elevations - error_field), 0.0, None)
    low = np.where(measurable & np.isfinite(elevations), low, 0.0)
    high = np.where(measurable & np.isfinite(elevations), high, 0.0)

    inside = depth[measurable]
    estimate = DepthVolumeEstimate(
        branch=BRANCH_A,
        value_type=VALUE_TYPE_ESTIMATED,
        method=(
            f"depth = WSE - DEM, clipped at 0; WSE = {wse.statistic} of "
            f"{wse.samples} shoreline samples in a {wse.buffer_m:.0f} m ring; "
            f"DEM vertical error from {error_source}"
            + (
                f"; computed over the {100 * (1 - branch_b_fraction):.1f}% of "
                f"the lake with a measured DEM height, the remaining "
                f"{100 * branch_b_fraction:.1f}% being Branch B by the GLO-30 "
                f"height-error mask -- the volume is a LOWER BOUND"
                if hem_split else ""
            )
        ),
        wse_m=wse.wse_m,
        wse_uncertainty_m=wse.spread_m,
        mean_depth_m=float(inside.mean()) if inside.size else 0.0,
        max_depth_m=float(inside.max()) if inside.size else 0.0,
        volume_m3=float(depth.sum() * pixel_area_m2),
        volume_low_m3=float(low.sum() * pixel_area_m2),
        volume_high_m3=float(high.sum() * pixel_area_m2),
        area_m2=area,
        reason=(
            decision.reason
            + (
                f" The GLO-30 height-error mask is zero over "
                f"{100 * branch_b_fraction:.1f}% of the lake, so the DEM "
                f"recorded a water surface there and those pixels are Branch "
                f"B. Depth and volume cover the rest only, and the volume is "
                f"therefore a LOWER BOUND on the impoundment: it omits "
                f"whatever the river already held below its DEM-epoch surface."
                if hem_split else ""
            )
        ),
        evidence={
            **decision.evidence,
            "branch_b_fraction": branch_b_fraction,
            "height_error_split_applied": hem_split,
            "measured_px": int(np.count_nonzero(measurable)),
            "volume_is_lower_bound": hem_split,
        },
    )
    log.info("%s", estimate.describe())
    return estimate
