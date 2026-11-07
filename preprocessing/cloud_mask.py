"""Sentinel-2 cloud and cloud-shadow masking.

Brief, Section 7.1: cloud and cloud shadow are masked, and **cloud shadow is
kept strictly separate from terrain shadow**. This module therefore returns
named components rather than one merged "bad pixel" flag, and it never produces
a terrain-shadow mask -- that is :mod:`preprocessing.terrain`'s job.

The distinction is not pedantic. Terrain shadow is a *stable, predictable*
property of topography and sun geometry, and it is the signal the shadow
rejection in Phase 4 reasons about. Cloud shadow moves between scenes and is
genuinely unusable data. Merging them would both discard usable observations and
destroy the evidence the project depends on.

**SCL class 2 ("dark area pixels") is not treated as cloud.** In steep terrain it
is dominated by topographic shadow. The config schema refuses to let it be
listed as cloud or cloud shadow.

References
----------
Pasquarella, V. J., Brown, C. F., Czerwinski, W. and Rucklidge, W. J. (2023).
    "Comprehensive Quality Assessment of Optical Satellite Imagery Using Weakly
    Supervised Video Learning." *IEEE/CVF CVPR Workshops*, 2125-2135.
    doi:10.1109/CVPRW59228.2023.00206 -- Cloud Score+, and the 0.60 clear
    threshold (0.50-0.65 usable range).
Sentinel-2 Level-2A Algorithm Theoretical Basis Document -- the SCL class
    definitions used below.
"""

from __future__ import annotations

from dataclasses import dataclass, field

import numpy as np

from config.schema import Config
from utils.logging import get_logger

log = get_logger(__name__)

#: Sentinel-2 Level-2A scene classification codes, for readable reporting.
SCL_CLASSES = {
    0: "no data",
    1: "saturated or defective",
    2: "dark area pixels",  # mostly TERRAIN shadow in steep terrain -- not cloud
    3: "cloud shadow",
    4: "vegetation",
    5: "bare soil",
    6: "water",
    7: "unclassified",
    8: "cloud medium probability",
    9: "cloud high probability",
    10: "thin cirrus",
    11: "snow or ice",
}

#: The SCL code this project must never mask as cloud (see module docstring).
SCL_DARK_AREA = 2


@dataclass(frozen=True)
class CloudMasks:
    """Cloud-related masks for one scene, kept as separate components.

    All arrays are boolean and share the scene's grid. ``True`` marks the
    condition named by the attribute.
    """

    cloud: np.ndarray
    cloud_shadow: np.ndarray
    defective: np.ndarray
    method: str
    stats: dict[str, float] = field(default_factory=dict)

    @property
    def unusable(self) -> np.ndarray:
        """Pixels that carry no trustworthy surface reflectance.

        The union of cloud, cloud shadow and defective pixels. Note this is
        deliberately **not** called "mask": terrain shadow is excluded, because
        a terrain-shadowed pixel is still a real observation of the ground.
        """
        return self.cloud | self.cloud_shadow | self.defective

    @property
    def valid(self) -> np.ndarray:
        """The complement of :attr:`unusable`."""
        return ~self.unusable

    @property
    def valid_fraction(self) -> float:
        return float(self.valid.mean())

    def summary(self) -> str:
        return (
            f"cloud {self.cloud.mean() * 100:.2f}%, "
            f"cloud shadow {self.cloud_shadow.mean() * 100:.2f}%, "
            f"defective {self.defective.mean() * 100:.2f}%, "
            f"usable {self.valid_fraction * 100:.2f}% "
            f"(method: {self.method})"
        )


def dilate(mask: np.ndarray, pixels: int) -> np.ndarray:
    """Grow a boolean mask by ``pixels``, to catch soft cloud edges.

    Uses scipy where it is importable and an exact numpy equivalent otherwise.
    The fallback is not a degraded approximation: see :func:`dilate_square`.
    It exists because scipy's compiled extensions are intermittently blocked
    on this project's Windows machine by Smart App Control (see README), and a
    cloud mask is not worth making the whole pipeline fragile for.
    """
    if pixels <= 0:
        return mask

    size = 2 * int(pixels) + 1
    try:
        from scipy import ndimage
    except ImportError as exc:  # pragma: no cover - environment-dependent
        log.debug("scipy unavailable (%s); using the numpy dilation", exc)
        return dilate_square(mask, int(pixels))

    return ndimage.binary_dilation(mask, structure=np.ones((size, size), dtype=bool))


def dilate_square(mask: np.ndarray, pixels: int) -> np.ndarray:
    """Binary dilation by a ``(2*pixels+1)``-square, in pure numpy.

    Exact rather than approximate: a square structuring element is separable,
    so dilating along rows and then along columns gives precisely the same
    result as the 2-D element. Outside the array is treated as ``False``, so
    the mask does not wrap around the edges.
    """
    out = np.asarray(mask, dtype=bool)
    if pixels <= 0:
        return out

    for axis in (0, 1):
        pad_width = [(0, 0), (0, 0)]
        pad_width[axis] = (pixels, pixels)
        padded = np.pad(out, pad_width, constant_values=False)

        grown = np.zeros_like(out)
        for offset in range(2 * pixels + 1):
            window: list[slice] = [slice(None), slice(None)]
            window[axis] = slice(offset, offset + out.shape[axis])
            grown |= padded[tuple(window)]
        out = grown

    return out


def masks_from_scl(scl: np.ndarray, cfg: Config) -> CloudMasks:
    """Cloud masks from the Sentinel-2 scene classification layer.

    SCL is a categorical band, so it is compared by exact class membership --
    never thresholded, which would be meaningless for class codes.
    """
    settings = cfg.preprocessing.cloud
    codes = np.asarray(scl)

    cloud = np.isin(codes, np.asarray(settings.scl_cloud_classes))
    cloud_shadow = np.isin(codes, np.asarray(settings.scl_cloud_shadow_classes))
    defective = np.isin(codes, np.asarray(settings.scl_defective_classes))

    cloud = dilate(cloud, settings.dilate_px)
    cloud_shadow = dilate(cloud_shadow, settings.dilate_px)

    masks = CloudMasks(
        cloud=cloud,
        cloud_shadow=cloud_shadow,
        defective=defective,
        method="scl",
        stats=_scl_histogram(codes),
    )
    log.info("SCL cloud masking: %s", masks.summary())
    return masks


def select_cloud_score(
    bands: dict[str, np.ndarray], cfg: Config
) -> np.ndarray:
    """The Cloud Score+ band the configuration asks for.

    ``preprocessing.cloud.cloud_score_band`` chooses between ``cs`` (the
    per-pixel clear score) and ``cs_cdf`` (distribution-adjusted). Nothing
    read it before this: callers picked a band by hand, so setting it to
    ``cs_cdf`` silently changed nothing. A control that looks real and does
    nothing is worse than no control.

    Args:
        bands: band name -> array, as read from the exported Cloud Score+
            raster.

    Raises:
        ValueError: naming the configured band and what was supplied, rather
            than falling back to whichever band happens to be present.
    """
    wanted = cfg.preprocessing.cloud.cloud_score_band
    if wanted not in bands:
        raise ValueError(
            f"preprocessing.cloud.cloud_score_band is {wanted!r} but the "
            f"supplied bands are {sorted(bands)}. Export it with "
            f"acquisition.sentinel2.cloud_score_bands, or change the setting."
        )
    log.debug("using Cloud Score+ band %s", wanted)
    return np.asarray(bands[wanted], dtype=np.float64)


def masks_from_cloud_score(
    cloud_score: np.ndarray, cfg: Config, *, scl: np.ndarray | None = None
) -> CloudMasks:
    """Cloud masks from Cloud Score+ (Pasquarella et al. 2023).

    Cloud Score+ gives a continuous 0-1 *clear* score; low values mean the pixel
    is obscured. It does not distinguish cloud from cloud shadow, so when SCL is
    supplied it is used for the cloud-shadow component, keeping the two
    categories separate as the brief requires.
    """
    settings = cfg.preprocessing.cloud
    score = np.asarray(cloud_score, dtype=np.float64)

    obscured = score < settings.cloud_score_threshold

    if scl is not None:
        codes = np.asarray(scl)
        cloud_shadow = np.isin(codes, np.asarray(settings.scl_cloud_shadow_classes))
        defective = np.isin(codes, np.asarray(settings.scl_defective_classes))
        # Avoid double-counting: anything already attributed to cloud shadow is
        # not also reported as cloud.
        cloud = obscured & ~cloud_shadow
    else:
        cloud = obscured
        cloud_shadow = np.zeros_like(obscured)
        defective = ~np.isfinite(score)

    cloud = dilate(cloud, settings.dilate_px)
    cloud_shadow = dilate(cloud_shadow, settings.dilate_px)

    masks = CloudMasks(
        cloud=cloud,
        cloud_shadow=cloud_shadow,
        defective=defective,
        method=f"cloud_score_plus<{settings.cloud_score_threshold}",
        stats={
            "cloud_score_mean": float(np.nanmean(score)),
            "cloud_score_median": float(np.nanmedian(score)),
        },
    )
    log.info("Cloud Score+ masking: %s", masks.summary())
    return masks


def build_masks(
    cfg: Config,
    *,
    scl: np.ndarray | None = None,
    cloud_score: np.ndarray | None = None,
) -> CloudMasks:
    """Cloud masks by the configured method.

    ``both`` takes the **union** of the two cloud estimates, which is the
    conservative choice: a pixel either method doubts is treated as cloud.

    Raises:
        ValueError: if the configured method's inputs were not supplied. The
            caller is told exactly what is missing rather than silently falling
            back to a weaker method.
    """
    method = cfg.preprocessing.cloud.method

    if method == "scl":
        if scl is None:
            raise ValueError("cloud.method is 'scl' but no SCL band was supplied")
        return masks_from_scl(scl, cfg)

    if method == "cloud_score_plus":
        if cloud_score is None:
            raise ValueError(
                "cloud.method is 'cloud_score_plus' but no Cloud Score+ band was "
                "supplied. Export it with acquisition.sentinel2, or set "
                "preprocessing.cloud.method to 'scl'."
            )
        return masks_from_cloud_score(cloud_score, cfg, scl=scl)

    # method == "both"
    if scl is None and cloud_score is None:
        raise ValueError("cloud.method is 'both' but neither band was supplied")
    if cloud_score is None:
        log.warning(
            "cloud.method is 'both' but no Cloud Score+ band was supplied; "
            "falling back to SCL alone, which is weaker. This is reported, not "
            "silent."
        )
        return masks_from_scl(scl, cfg)
    if scl is None:
        log.warning(
            "cloud.method is 'both' but no SCL band was supplied; cloud shadow "
            "cannot be separated from cloud by Cloud Score+ alone."
        )
        return masks_from_cloud_score(cloud_score, cfg)

    from_scl = masks_from_scl(scl, cfg)
    from_score = masks_from_cloud_score(cloud_score, cfg, scl=scl)

    masks = CloudMasks(
        cloud=from_scl.cloud | from_score.cloud,
        cloud_shadow=from_scl.cloud_shadow | from_score.cloud_shadow,
        defective=from_scl.defective | from_score.defective,
        method="both (union of SCL and Cloud Score+)",
        stats={**from_scl.stats, **from_score.stats},
    )
    log.info("combined cloud masking: %s", masks.summary())
    return masks


def terrain_shadow_overlap(
    masks: CloudMasks, terrain_shadow: np.ndarray
) -> dict[str, float]:
    """How much terrain shadow would be lost by treating it as cloud shadow.

    Reported so the separation the brief insists on can be shown to matter
    rather than merely asserted. All values are fractions of the scene.
    """
    terrain = np.asarray(terrain_shadow, dtype=bool)
    both = terrain & masks.cloud_shadow

    return {
        "terrain_shadow_fraction": float(terrain.mean()),
        "cloud_shadow_fraction": float(masks.cloud_shadow.mean()),
        "overlap_fraction": float(both.mean()),
        "terrain_shadow_not_cloud_shadow": float((terrain & ~masks.cloud_shadow).mean()),
        "terrain_shadow_also_usable": float((terrain & masks.valid).mean()),
    }


def _scl_histogram(codes: np.ndarray) -> dict[str, float]:
    total = codes.size
    values, counts = np.unique(codes, return_counts=True)
    return {
        f"scl_{int(v)}_{SCL_CLASSES.get(int(v), 'unknown').replace(' ', '_')}": float(
            c / total
        )
        for v, c in zip(values, counts)
    }
