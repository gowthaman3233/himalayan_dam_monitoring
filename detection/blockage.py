"""River blockage (potential landslide dam) candidate detection.

Brief, Section 7.6: a candidate is created when a new landslide polygon
intersects or comes within a configurable distance of the stream network,
**and** there is evidence of obstruction -- channel narrowing, loss of
downstream water continuity, and/or new upstream water.

The conjunction is the whole module
-----------------------------------
A landslide beside a river is a landslide beside a river. It is not a dam.
Nepal's steep valleys put failures next to channels constantly, so proximity
is abundant and almost always means nothing. ``min_evidence_types`` cannot be
set below 1, and :func:`detect_blockages` refuses to emit a candidate on
proximity alone no matter how close the landslide comes -- required system
test 4.

The system also never says a dam *has* formed. The type is "Potential
Landslide Dam", the score is a confidence in the *evidence*, and every
candidate lists the factors behind it (Section 9's principle, applied here).

Upstream and downstream, without a graph
----------------------------------------
Obstruction evidence is directional: water gained *above* a blockage and lost
*below* it. Direction comes from the D8 flow accumulation computed in Phase 2:
accumulation rises monotonically downstream, so stream pixels near the
blockage with lower accumulation are upstream of it and those with higher
accumulation are downstream. This avoids building and traversing a channel
graph, and it degrades gracefully -- where accumulation is unavailable the
directional signals are simply absent rather than guessed.

Morphology here uses :func:`preprocessing.cloud_mask.dilate_square`, a pure
numpy dilation, rather than a scipy distance transform. scipy's compiled
extensions are intermittently blocked on this project's machine (see
docs/validation.md 8), and a detector that cannot run is worse than one that
measures distance in whole pixels.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Any, Sequence

import numpy as np

from preprocessing.cloud_mask import dilate_square
from utils.logging import get_logger

if TYPE_CHECKING:  # pragma: no cover
    import geopandas as gpd

    from config.schema import Config

log = get_logger(__name__)

#: Obstruction signals, in the order the brief lists them (Section 7.6).
OBSTRUCTION_SIGNALS = (
    "channel_narrowing",
    "downstream_water_loss",
    "new_upstream_water",
)


@dataclass(frozen=True)
class BlockageFactor:
    """One contributing factor, with the measurement behind it."""

    name: str
    present: bool
    weight: float
    value: float | None = None
    unit: str = ""
    threshold: float | None = None
    reason: str | None = None

    @property
    def contribution(self) -> float:
        return self.weight if self.present else 0.0

    def describe(self) -> str:
        if self.value is None:
            state = "present" if self.present else "absent"
            return f"{self.name}: {state} ({self.reason or 'not measured'})"
        unit = f" {self.unit}" if self.unit else ""
        verdict = "PRESENT" if self.present else "absent"
        threshold = (
            f" (threshold {self.threshold:g}{unit})" if self.threshold is not None else ""
        )
        return f"{self.name}: {self.value:,.0f}{unit} -> {verdict}{threshold}"

    def as_dict(self) -> dict[str, Any]:
        return {
            "name": self.name,
            "present": self.present,
            "weight": self.weight,
            "value": self.value,
            "unit": self.unit,
            "threshold": self.threshold,
            "contribution": self.contribution,
            "reason": self.reason,
        }


@dataclass(frozen=True)
class BlockageCandidate:
    """A potential landslide dam, with its evidence and dates."""

    dam_code: str
    site_type: str
    confidence: float
    factors: list[BlockageFactor]
    landslide_area_m2: float
    distance_to_stream_m: float
    centroid_x: float
    centroid_y: float
    centroid_lon: float | None = None
    centroid_lat: float | None = None
    pre_date: str | None = None
    post_date: str | None = None
    geometry_wkt: str | None = None
    #: The stream pixels the landslide reaches. Phase 8 needs these to find
    #: what is upstream of the blockage, so they are carried on the candidate
    #: rather than recomputed from the centroid.
    site_mask: np.ndarray | None = field(default=None, repr=False, compare=False)
    #: The landslide component that produced this candidate.
    landslide_mask: np.ndarray | None = field(default=None, repr=False, compare=False)

    @property
    def obstruction_factors(self) -> list[BlockageFactor]:
        return [f for f in self.factors if f.name in OBSTRUCTION_SIGNALS]

    @property
    def evidence_count(self) -> int:
        return sum(1 for f in self.obstruction_factors if f.present)

    def contributing_factors(self) -> list[BlockageFactor]:
        """Present factors, most influential first (brief, Section 9)."""
        return sorted(
            (f for f in self.factors if f.present),
            key=lambda f: f.contribution,
            reverse=True,
        )

    def describe(self) -> str:
        lines = [
            f"{self.dam_code}  {self.site_type}",
            f"  confidence {self.confidence:.2f} from {self.evidence_count} "
            f"obstruction signal(s)",
            f"  landslide {self.landslide_area_m2:,.0f} m2, "
            f"{self.distance_to_stream_m:.0f} m from the stream network",
        ]
        if self.pre_date or self.post_date:
            lines.append(f"  evidence dates: {self.pre_date} -> {self.post_date}")
        lines.append("  factors:")
        lines.extend(f"    - {f.describe()}" for f in self.factors)
        return "\n".join(lines)

    def as_dict(self) -> dict[str, Any]:
        return {
            "dam_code": self.dam_code,
            "site_type": self.site_type,
            "confidence": self.confidence,
            "evidence_count": self.evidence_count,
            "landslide_area_m2": self.landslide_area_m2,
            "distance_to_stream_m": self.distance_to_stream_m,
            "centroid_lon": self.centroid_lon,
            "centroid_lat": self.centroid_lat,
            "pre_date": self.pre_date,
            "post_date": self.post_date,
            "factors": [f.as_dict() for f in self.factors],
        }


def _components(mask: np.ndarray) -> list[np.ndarray]:
    """Connected components of a boolean mask, 8-connected, in pure numpy.

    Written here rather than taken from scipy.ndimage.label for the reason in
    the module docstring. Iterative flood fill, so deep recursion is not a
    risk on a large component.
    """
    binary = np.asarray(mask, dtype=bool)
    seen = np.zeros(binary.shape, dtype=bool)
    rows, cols = binary.shape
    out: list[np.ndarray] = []

    for start_row, start_col in zip(*np.nonzero(binary)):
        if seen[start_row, start_col]:
            continue
        component = np.zeros(binary.shape, dtype=bool)
        stack = [(int(start_row), int(start_col))]
        seen[start_row, start_col] = True
        while stack:
            row, col = stack.pop()
            component[row, col] = True
            for d_row in (-1, 0, 1):
                for d_col in (-1, 0, 1):
                    r, c = row + d_row, col + d_col
                    if 0 <= r < rows and 0 <= c < cols and binary[r, c] and not seen[r, c]:
                        seen[r, c] = True
                        stack.append((r, c))
        out.append(component)
    return out


def _stream_reach(
    site: np.ndarray, stream_mask: np.ndarray, steps: int
) -> np.ndarray:
    """Stream pixels within ``steps`` of ``site``, walking along the network.

    Growth is restricted to stream pixels, so the distance is measured along
    the channel rather than across country. Two deposits on opposite banks of
    a gorge are a few pixels apart along the channel; two deposits the same
    straight-line distance apart but on different tributaries are not
    connected at all.
    """
    reach = np.asarray(site, dtype=bool) | (
        np.asarray(site, dtype=bool) & np.asarray(stream_mask, dtype=bool)
    )
    streams = np.asarray(stream_mask, dtype=bool)
    for _ in range(max(0, int(steps))):
        grown = (dilate_square(reach, 1) & streams) | reach
        if grown.sum() == reach.sum():
            break
        reach = grown
    return reach


def _merge_along_stream(
    components: Sequence[np.ndarray],
    stream_mask: np.ndarray,
    reach_px: int,
    merge_px: int,
) -> list[np.ndarray]:
    """Group landslide components that obstruct the same reach.

    One landslide dam is routinely detected as several components. Phase 5's
    slope gate carves the channel-crossing part out of a deposit lying on a
    flat valley floor (see methods 5.9), cloud and snow fragment it further,
    and each fragment then becomes its own candidate.

    That is not merely untidy. **The obstruction evidence is measured over a
    reach**, so fragments of one dam all see the same impounded water and
    report it as if independently confirmed. Measured on Baige 2018: the four
    highest-ranked candidates sat within 173,000-181,000 drainage cells of each
    other and claimed 136,500-154,800 m2 of gained water upstream -- the same
    water, counted four times. Choosing "the candidate with the most impounded
    water" was then choosing an arbitrary fragment.

    Components are merged when their channel reaches overlap, with distance
    measured **along the stream network**, not across country.

    Args:
        reach_px: how far a component may lie from the channel at all.
        merge_px: how far along the channel the grouping extends. Zero does
            not disable grouping -- components reaching the same stream pixels
            are one obstruction regardless, which is the slope-gate case.

    Returns:
        One mask per blockage: the union of each group's components.
    """
    streams = np.asarray(stream_mask, dtype=bool)
    reaches = [
        _stream_reach(dilate_square(c, reach_px) & streams, streams, merge_px)
        for c in components
    ]

    # Union-find over components whose reaches intersect.
    parent = list(range(len(components)))

    def find(i: int) -> int:
        while parent[i] != i:
            parent[i] = parent[parent[i]]
            i = parent[i]
        return i

    for i in range(len(components)):
        if not reaches[i].any():
            continue
        for j in range(i + 1, len(components)):
            if reaches[j].any() and (reaches[i] & reaches[j]).any():
                parent[find(i)] = find(j)

    grouped: dict[int, np.ndarray] = {}
    for i, component in enumerate(components):
        root = find(i)
        grouped[root] = (
            component if root not in grouped else grouped[root] | component
        )
    return list(grouped.values())


def _pixels(distance_m: float, cellsize_m: float) -> int:
    """Whole pixels covering a distance, at least one."""
    return max(1, int(round(distance_m / cellsize_m)))


def detect_blockages(
    cfg: "Config",
    *,
    landslides: np.ndarray,
    streams: np.ndarray,
    cellsize_m: float,
    pixel_area_m2: float,
    flow_accumulation: np.ndarray | None = None,
    water_pre: np.ndarray | None = None,
    water_post: np.ndarray | None = None,
    transform: Any | None = None,
    crs: Any | None = None,
    pre_date: str | None = None,
    post_date: str | None = None,
    start_index: int = 1,
) -> list[BlockageCandidate]:
    """Find potential landslide dams where a new landslide obstructs a channel.

    Args:
        landslides: new landslide mask, from Phase 5. "New" must come from
            change detection, never from single-date classification.
        streams: the stream network from Phase 2.
        flow_accumulation: D8 accumulation, used to tell upstream from
            downstream. Without it the directional signals are reported absent
            rather than guessed.
        water_pre, water_post: water masks either side of the event, for the
            obstruction evidence.
        transform, crs: supply both to get geographic centroids.
        start_index: first number for the generated dam codes.

    Returns:
        Candidates above ``min_confidence``, each with at least
        ``min_evidence_types`` obstruction signals. **Proximity alone never
        produces a candidate.**
    """
    settings = cfg.detection.blockage
    weights = settings.weights

    landslide_mask = np.asarray(landslides, dtype=bool)
    stream_mask = np.asarray(streams, dtype=bool)
    if landslide_mask.shape != stream_mask.shape:
        raise ValueError(
            f"landslides {landslide_mask.shape} and streams {stream_mask.shape} "
            "are on different grids"
        )

    reach_px = _pixels(settings.max_distance_to_stream_m, cellsize_m)
    search_px = _pixels(settings.evidence_search_m, cellsize_m)
    channel_px = _pixels(settings.channel_zone_m, cellsize_m)

    candidates: list[BlockageCandidate] = []
    index = start_index

    min_component_px = int(np.ceil(settings.min_landslide_area_m2 / pixel_area_m2))
    too_small = 0

    components = [
        c for c in _components(landslide_mask)
        if int(c.sum()) >= min_component_px
    ]
    too_small = len(_components(landslide_mask)) - len(components)
    groups = _merge_along_stream(
        components, stream_mask, reach_px,
        _pixels(settings.merge_along_stream_m, cellsize_m),
    )
    if len(groups) != len(components):
        log.info(
            "%d landslide component(s) merged into %d blockage(s) within %.0f m "
            "along the channel",
            len(components), len(groups), settings.merge_along_stream_m,
        )

    for component in groups:
        near = dilate_square(component, reach_px)
        touching = near & stream_mask
        if not touching.any():
            continue  # not near the channel at all

        # Distance in whole pixels: the smallest dilation that still reaches.
        distance_px = 0
        for step in range(0, reach_px + 1):
            grown = component if step == 0 else dilate_square(component, step)
            if (grown & stream_mask).any():
                distance_px = step
                break
        distance_m = float(distance_px * cellsize_m)

        factors = [
            BlockageFactor(
                name="intersects_stream",
                present=True,
                weight=weights.intersects_stream,
                value=distance_m,
                unit="m",
                threshold=settings.max_distance_to_stream_m,
                reason="precondition, not evidence of obstruction",
            )
        ]
        factors.extend(
            _obstruction_factors(
                settings,
                weights,
                touching=touching,
                stream_mask=stream_mask,
                flow_accumulation=flow_accumulation,
                water_pre=water_pre,
                water_post=water_post,
                search_px=search_px,
                channel_px=channel_px,
                pixel_area_m2=pixel_area_m2,
            )
        )

        evidence_count = sum(
            1 for f in factors if f.present and f.name in OBSTRUCTION_SIGNALS
        )
        if evidence_count < settings.min_evidence_types:
            log.info(
                "landslide near the channel (%.0f m) rejected: %d obstruction "
                "signal(s), %d required. Proximity alone is not a dam",
                distance_m,
                evidence_count,
                settings.min_evidence_types,
            )
            continue

        # Confidence is normalised over the total weight, so a candidate
        # carrying only the proximity precondition could never reach 1.0.
        confidence = float(
            sum(f.contribution for f in factors) / weights.total()
        )
        if confidence < settings.min_confidence:
            log.info(
                "candidate rejected: confidence %.2f below the %.2f minimum",
                confidence,
                settings.min_confidence,
            )
            continue

        rows, cols = np.nonzero(component)
        centroid_col, centroid_row = float(cols.mean()), float(rows.mean())
        if transform is not None:
            x, y = transform @ (centroid_col + 0.5, centroid_row + 0.5)
        else:
            x, y = centroid_col, centroid_row

        lon = lat = None
        if transform is not None and crs is not None:
            lon, lat = _to_wgs84(x, y, crs)

        candidate = BlockageCandidate(
            dam_code=f"{settings.code_prefix}-{index:03d}",
            site_type=settings.site_type,
            confidence=confidence,
            factors=factors,
            landslide_area_m2=float(np.count_nonzero(component) * pixel_area_m2),
            distance_to_stream_m=distance_m,
            centroid_x=float(x),
            centroid_y=float(y),
            centroid_lon=lon,
            centroid_lat=lat,
            pre_date=pre_date,
            post_date=post_date,
            site_mask=touching,
            landslide_mask=component,
        )
        candidates.append(candidate)
        log.info("blockage candidate:\n%s", candidate.describe())
        index += 1

    candidates.sort(key=lambda c: c.confidence, reverse=True)
    log.info(
        "%d blockage candidate(s) from %d landslide component(s); "
        "%d component(s) below the %.0f m2 minimum area",
        len(candidates),
        len(_components(landslide_mask)),
        too_small,
        settings.min_landslide_area_m2,
    )
    return candidates


def _obstruction_factors(
    settings: Any,
    weights: Any,
    *,
    touching: np.ndarray,
    stream_mask: np.ndarray,
    flow_accumulation: np.ndarray | None,
    water_pre: np.ndarray | None,
    water_post: np.ndarray | None,
    search_px: int,
    channel_px: int,
    pixel_area_m2: float,
) -> list[BlockageFactor]:
    """The three obstruction signals of Section 7.6."""
    search_zone = dilate_square(touching, search_px)
    channel_zone = dilate_square(touching, channel_px)

    # --- channel narrowing ------------------------------------------------- #
    if water_pre is None or water_post is None:
        narrowing = BlockageFactor(
            name="channel_narrowing",
            present=False,
            weight=weights.channel_narrowing,
            reason="no pre/post water masks supplied",
        )
    else:
        before = int(np.count_nonzero(np.asarray(water_pre, bool) & channel_zone))
        after = int(np.count_nonzero(np.asarray(water_post, bool) & channel_zone))
        fraction = (before - after) / before if before > 0 else 0.0
        narrowing = BlockageFactor(
            name="channel_narrowing",
            present=fraction >= settings.min_channel_narrowing_fraction,
            weight=weights.channel_narrowing,
            value=float(fraction),
            unit="fraction",
            threshold=settings.min_channel_narrowing_fraction,
            reason=f"{before} -> {after} water px in the channel zone",
        )

    # --- directional signals ----------------------------------------------- #
    if flow_accumulation is None:
        absent = "no flow accumulation supplied, so upstream cannot be told from downstream"
        return [
            narrowing,
            BlockageFactor(
                "downstream_water_loss", False, weights.downstream_water_loss,
                reason=absent,
            ),
            BlockageFactor(
                "new_upstream_water", False, weights.new_upstream_water, reason=absent
            ),
        ]

    if water_pre is None or water_post is None:
        absent = "no pre/post water masks supplied"
        return [
            narrowing,
            BlockageFactor(
                "downstream_water_loss", False, weights.downstream_water_loss,
                reason=absent,
            ),
            BlockageFactor(
                "new_upstream_water", False, weights.new_upstream_water, reason=absent
            ),
        ]

    accumulation = np.asarray(flow_accumulation, dtype=np.float64)
    at_site = accumulation[touching]
    at_site = at_site[np.isfinite(at_site)]
    if at_site.size == 0:
        absent = "flow accumulation is undefined at the blockage site"
        return [
            narrowing,
            BlockageFactor(
                "downstream_water_loss", False, weights.downstream_water_loss,
                reason=absent,
            ),
            BlockageFactor(
                "new_upstream_water", False, weights.new_upstream_water, reason=absent
            ),
        ]

    site_accumulation = float(np.median(at_site))
    # Accumulation rises monotonically downstream.
    nearby_stream = search_zone & stream_mask & np.isfinite(accumulation)
    upstream = nearby_stream & (accumulation < site_accumulation)
    downstream = nearby_stream & (accumulation > site_accumulation)

    upstream_zone = dilate_square(upstream, channel_px)
    downstream_zone = dilate_square(downstream, channel_px)

    pre = np.asarray(water_pre, dtype=bool)
    post = np.asarray(water_post, dtype=bool)

    gained = float(np.count_nonzero(post & ~pre & upstream_zone) * pixel_area_m2)
    lost = float(np.count_nonzero(pre & ~post & downstream_zone) * pixel_area_m2)

    return [
        narrowing,
        BlockageFactor(
            name="downstream_water_loss",
            present=lost >= settings.min_downstream_water_loss_m2,
            weight=weights.downstream_water_loss,
            value=lost,
            unit="m2",
            threshold=settings.min_downstream_water_loss_m2,
            reason=f"{int(np.count_nonzero(downstream))} downstream stream px",
        ),
        BlockageFactor(
            name="new_upstream_water",
            present=gained >= settings.min_new_upstream_water_m2,
            weight=weights.new_upstream_water,
            value=gained,
            unit="m2",
            threshold=settings.min_new_upstream_water_m2,
            reason=f"{int(np.count_nonzero(upstream))} upstream stream px",
        ),
    ]


def _to_wgs84(x: float, y: float, crs: Any) -> tuple[float, float]:
    from pyproj import CRS, Transformer

    transformer = Transformer.from_crs(
        CRS.from_user_input(crs), CRS.from_epsg(4326), always_xy=True
    )
    lon, lat = transformer.transform(x, y)
    return float(lon), float(lat)


def candidates_to_frame(
    candidates: Sequence[BlockageCandidate], crs: Any
) -> "gpd.GeoDataFrame":
    """Candidates as a point GeoDataFrame, for mapping and storage."""
    import geopandas as gpd

    from utils.crs import ensure_projected

    projected = ensure_projected(crs, context="blockage candidate positions")
    if not candidates:
        return gpd.GeoDataFrame(
            {
                name: []
                for name in (
                    "dam_code",
                    "site_type",
                    "confidence",
                    "evidence_count",
                    "landslide_area_m2",
                    "distance_to_stream_m",
                )
            },
            geometry=[],
            crs=projected,
        )

    return gpd.GeoDataFrame(
        {
            "dam_code": [c.dam_code for c in candidates],
            "site_type": [c.site_type for c in candidates],
            "confidence": [c.confidence for c in candidates],
            "evidence_count": [c.evidence_count for c in candidates],
            "landslide_area_m2": [c.landslide_area_m2 for c in candidates],
            "distance_to_stream_m": [c.distance_to_stream_m for c in candidates],
        },
        geometry=gpd.points_from_xy(
            [c.centroid_x for c in candidates], [c.centroid_y for c in candidates]
        ),
        crs=projected,
    )
