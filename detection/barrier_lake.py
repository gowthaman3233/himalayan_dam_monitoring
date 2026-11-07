"""Barrier lake detection and tracking.

Brief, Section 7.7: a water body **upstream** of a blockage candidate, on the
same stream, that is **new or expanding** relative to the pre-event baseline;
tracked through time with stable IDs, handling merging, splitting and
disappearance.

The rule that governs this module
---------------------------------
**A lake that cannot be seen has not disappeared.**

A barrier lake vanishing between two scenes is the single most alarming signal
this system can produce: it reads as "the dam has breached". Cloud over the
lake produces exactly that appearance, and cloud over a Himalayan valley is
the normal condition for much of the year.

So absence is only ever reported as *disappearance* when the lake's own
previous footprint was observable on the new date. Below
``min_observable_fraction`` the lake is marked ``not_observed``, keeps its
identity, and waits. This is the same distinction Phase 9 draws between a gap
and a measurement, applied where getting it wrong would be most costly.

Identity through merging and splitting
--------------------------------------
Lakes are matched between dates by overlap. One previous lake matching one
current lake continues its identity. Several previous lakes matching one
current lake is a **merge**: the survivor keeps the identity of the largest
contributor and records what it absorbed. One previous lake matching several
current lakes is a **split**: the largest fragment keeps the identity and the
others become new lakes that record their parent. Identity therefore follows
mass, which is the only choice that keeps a growing impoundment's history
intact when a rising shoreline swallows a neighbouring pond.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date
from typing import TYPE_CHECKING, Any, Sequence

import numpy as np

from preprocessing.cloud_mask import dilate_square
from utils.logging import get_logger

if TYPE_CHECKING:  # pragma: no cover
    from config.schema import Config

log = get_logger(__name__)

#: A lake was measured on this date.
STATE_OBSERVED = "observed"
#: The lake's footprint was not observable; its state is unknown.
STATE_NOT_OBSERVED = "not_observed"
#: The footprint was observable and held no water.
STATE_ABSENT = "absent"

LAKE_STATES = (STATE_OBSERVED, STATE_NOT_OBSERVED, STATE_ABSENT)

EVENT_APPEARED = "appeared"
EVENT_CONTINUED = "continued"
EVENT_MERGED = "merged"
EVENT_SPLIT = "split"
EVENT_DISAPPEARED = "disappeared"
EVENT_NOT_OBSERVED = "not_observed"
#: The footprint still holds water, but no qualifying lake matched it. The
#: water body was re-partitioned -- it has NOT disappeared. Raised instead of
#: EVENT_DISAPPEARED, which on real data fired on a lake that was growing.
EVENT_REPARTITIONED = "repartitioned"

EVENTS = (
    EVENT_APPEARED,
    EVENT_CONTINUED,
    EVENT_MERGED,
    EVENT_SPLIT,
    EVENT_DISAPPEARED,
    EVENT_NOT_OBSERVED,
    EVENT_REPARTITIONED,
)


def _components(mask: np.ndarray) -> list[np.ndarray]:
    """8-connected components, in pure numpy (see detection.blockage)."""
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


def _pixels(distance_m: float, cellsize_m: float) -> int:
    return max(1, int(round(distance_m / cellsize_m)))


def _trace_along_stream(
    site: np.ndarray,
    stream_mask: np.ndarray,
    accumulation: np.ndarray,
    site_accumulation: float,
    steps: int,
    *,
    upstream: bool,
) -> np.ndarray:
    """Stream pixels reachable from the blockage, walking one way along it.

    Brief, Section 7.7: a barrier lake is upstream of the blockage **on the
    same stream**. Selecting pixels by accumulation alone does not honour the
    second half of that: in a 4 km box around a main-stem blockage, every small
    tributary has a low accumulation value and so reads as "upstream", whether
    or not it drains to the blockage at all.

    The cost was measured on Baige 2018. The impounded reach reported for one
    date spanned rows 154-289; for the next date, rows 424-598 -- a different
    part of the valley entirely, because the sprawling zone picked up whichever
    unrelated tributaries happened to hold water that day. Consecutive dates'
    lakes overlapped by **exactly 0 pixels** while 40% of the water persisted,
    so no lake could keep a stable identity and trend analysis was impossible.

    This grows outward from the blockage one pixel at a time, staying on stream
    pixels whose accumulation lies the right side of the site's. A tributary
    that does not connect to the blockage through such pixels is never
    reached. ``steps`` then bounds the distance **along the channel**, which is
    what "how far upstream to look" means, rather than a box radius.

    Args:
        upstream: True to walk against the flow (accumulation below the site's),
            False to walk with it.

    Returns:
        The traced reach, excluding the blockage pixels themselves.
    """
    allowed = (
        np.asarray(stream_mask, dtype=bool)
        & np.isfinite(accumulation)
        & (
            (accumulation < site_accumulation)
            if upstream
            else (accumulation > site_accumulation)
        )
    )
    reach = np.asarray(site, dtype=bool).copy()
    for _ in range(max(0, int(steps))):
        grown = (dilate_square(reach, 1) & allowed) | reach
        if grown.sum() == reach.sum():
            break
        reach = grown
    return reach & allowed


def _partition_by_proximity(
    upstream_seed: np.ndarray, downstream_seed: np.ndarray, steps: int
) -> tuple[np.ndarray, np.ndarray]:
    """Grow two seed regions together, assigning each pixel to the nearer one.

    A multi-source growth: both regions expand one pixel per step, so a pixel
    joins whichever seed reaches it first -- that is, whichever side of the
    blockage is nearer in Chebyshev distance. Pixels reached by both in the
    same step are a boundary and join neither, which keeps the two regions
    disjoint.

    This replaces two independent wide dilations, which overlap around the
    blockage so heavily that subtracting one from the other erases both.
    """
    upstream = np.asarray(upstream_seed, dtype=bool).copy()
    downstream = np.asarray(downstream_seed, dtype=bool).copy()

    for _ in range(max(0, int(steps))):
        unclaimed = ~(upstream | downstream)
        reached_up = dilate_square(upstream, 1) & unclaimed
        reached_down = dilate_square(downstream, 1) & unclaimed
        contested = reached_up & reached_down
        upstream |= reached_up & ~contested
        downstream |= reached_down & ~contested
        if not (reached_up | reached_down).any():
            break

    return upstream, downstream


@dataclass(frozen=True)
class BarrierLakeCandidate:
    """Impounded water upstream of a blockage, before tracking begins."""

    mask: np.ndarray
    area_m2: float
    baseline_area_m2: float
    new_area_m2: float
    expansion_fraction: float | None
    qualifies_as: str  # "new" or "expanding"
    upstream_of: str | None = None

    def describe(self) -> str:
        growth = (
            f"{self.expansion_fraction:+.1%} vs baseline"
            if self.expansion_fraction is not None
            else "no baseline water"
        )
        return (
            f"{self.area_m2:,.0f} m2 ({self.qualifies_as}; {growth}; "
            f"{self.new_area_m2:,.0f} m2 of it new)"
        )


def find_barrier_lakes(
    cfg: "Config",
    *,
    blockage_site: np.ndarray,
    streams: np.ndarray,
    water_post: np.ndarray,
    water_pre: np.ndarray,
    cellsize_m: float,
    pixel_area_m2: float,
    flow_accumulation: np.ndarray | None = None,
    dam_code: str | None = None,
) -> list[BarrierLakeCandidate]:
    """Water bodies upstream of a blockage that are new or expanding.

    Args:
        blockage_site: the stream pixels the landslide reaches, from Phase 7.
        flow_accumulation: used to find *upstream*. Without it no candidate is
            returned -- "upstream" cannot be guessed, and a lake downstream of
            a blockage is not a barrier lake.

    Returns:
        Candidates meeting Section 7.7's new-or-expanding test. Pre-existing,
        unchanged water is excluded however close to the blockage it lies.
    """
    settings = cfg.detection.barrier_lake
    site = np.asarray(blockage_site, dtype=bool)
    stream_mask = np.asarray(streams, dtype=bool)
    post = np.asarray(water_post, dtype=bool)
    pre = np.asarray(water_pre, dtype=bool)

    if not site.any():
        return []

    if flow_accumulation is None:
        log.warning(
            "no flow accumulation supplied: upstream cannot be identified, so "
            "no barrier lake candidate is returned rather than guessing"
        )
        return []

    accumulation = np.asarray(flow_accumulation, dtype=np.float64)
    at_site = accumulation[site]
    at_site = at_site[np.isfinite(at_site)]
    if at_site.size == 0:
        log.warning("flow accumulation is undefined at the blockage site")
        return []
    # The MOST DOWNSTREAM point the blockage touches, not the median.
    #
    # Accumulation rises monotonically downstream, so the blockage's own
    # maximum marks its outlet: everything upstream of the obstruction lies
    # strictly below it, on every contributing branch. The median fails
    # wherever a blockage straddles a confluence, which is common -- a
    # landslide dams a main stem just below a tributary mouth. On Baige 2018
    # the ND-007 site spanned 20,817 to 56,484 cells; the median of 20,856 was
    # dragged down by the tributary pixels and put the Jinsha main stem, at
    # 56,484 and carrying the actual impoundment, on the DOWNSTREAM side. Every
    # water component was then rejected as "growth not upstream".
    #
    # Taking the maximum is safe only because the reaches are traced along the
    # network (see _trace_along_stream): a parallel tributary that joins below
    # the blockage also has accumulation under this value, but cannot be
    # reached by walking upstream from the site, so it is never included.
    site_accumulation = float(np.max(at_site))

    search_px = _pixels(settings.upstream_search_m, cellsize_m)
    # Accumulation rises downstream, so upstream is strictly lower -- but a low
    # accumulation value alone does not put a pixel on the blocked stream.
    # Section 7.7 requires the lake to be upstream "on the same stream", and
    # both reaches are therefore TRACED from the blockage along the network.
    upstream_stream = _trace_along_stream(
        site, stream_mask, accumulation, site_accumulation, search_px,
        upstream=True,
    )
    if not upstream_stream.any():
        log.info("no upstream stream pixels within %.0f m along the channel "
                 "from the blockage", settings.upstream_search_m)
        return []

    downstream_stream = _trace_along_stream(
        site, stream_mask, accumulation, site_accumulation, search_px,
        upstream=False,
    )

    # Impounded water fills the valley floor, so the zones must reach the
    # width a lake could occupy -- but two independent dilations that wide
    # overlap heavily around the blockage, and subtracting one from the other
    # then erases both. The zones are therefore grown together, each pixel
    # going to whichever side of the blockage is nearer.
    width_px = _pixels(settings.lake_width_m, cellsize_m)
    upstream_zone, downstream_zone = _partition_by_proximity(
        upstream_stream, downstream_stream, width_px
    )

    candidates: list[BarrierLakeCandidate] = []
    for component in _components(post):
        if float(np.count_nonzero(component) * pixel_area_m2) < settings.min_area_m2:
            continue

        # Judge the NEW water, not the component. A barrier lake is joined to
        # the river it dams, so the component routinely spans both sides of
        # the blockage -- testing the component would qualify a river whose
        # every gain lay downstream. What makes a lake a barrier lake is where
        # the water ARRIVED.
        gained = component & ~pre
        gained_upstream = gained & upstream_zone & ~downstream_zone
        gained_downstream = gained & downstream_zone & ~upstream_zone

        new_area = float(np.count_nonzero(gained_upstream) * pixel_area_m2)
        downstream_gain = float(np.count_nonzero(gained_downstream) * pixel_area_m2)
        if new_area <= downstream_gain:
            continue  # the growth is not upstream of the blockage

        # Area and baseline are measured over the impounded reach only, so the
        # reported lake is the water held back rather than the whole river.
        impounded = component & upstream_zone & ~downstream_zone
        area = float(np.count_nonzero(impounded) * pixel_area_m2)
        if area < settings.min_area_m2:
            continue
        baseline = float(np.count_nonzero(impounded & pre) * pixel_area_m2)
        expansion = (new_area / baseline) if baseline > 0 else None

        if baseline == 0.0:
            if new_area < settings.min_new_area_m2:
                continue
            qualifies = "new"
        elif (
            expansion is not None
            and expansion >= settings.min_expansion_fraction
            and new_area >= settings.min_new_area_m2
        ):
            qualifies = "expanding"
        else:
            continue  # pre-existing and unchanged: not a barrier lake

        component = impounded

        candidate = BarrierLakeCandidate(
            mask=component,
            area_m2=area,
            baseline_area_m2=baseline,
            new_area_m2=new_area,
            expansion_fraction=expansion,
            qualifies_as=qualifies,
            upstream_of=dam_code,
        )
        candidates.append(candidate)
        log.info("barrier lake candidate: %s", candidate.describe())

    candidates.sort(key=lambda c: c.area_m2, reverse=True)
    return candidates


@dataclass(frozen=True)
class LakeObservation:
    """One lake on one date: a measurement, a gap, or a confirmed absence."""

    lake_id: str
    obs_date: date
    state: str
    area_m2: float | None = None
    observable_fraction: float | None = None
    reason: str | None = None

    def describe(self) -> str:
        if self.state == STATE_OBSERVED:
            return f"{self.obs_date} {self.lake_id}: {self.area_m2:,.0f} m2"
        return f"{self.obs_date} {self.lake_id}: {self.state} ({self.reason})"


@dataclass(frozen=True)
class LakeEvent:
    """Something that happened to a lake's identity on a date."""

    kind: str
    obs_date: date
    lake_id: str
    related_ids: tuple[str, ...] = ()
    reason: str | None = None

    def describe(self) -> str:
        related = f" <- {', '.join(self.related_ids)}" if self.related_ids else ""
        reason = f" ({self.reason})" if self.reason else ""
        return f"{self.obs_date} {self.lake_id} {self.kind}{related}{reason}"


@dataclass
class TrackedLake:
    """A lake's identity and history across dates."""

    lake_id: str
    first_seen: date
    last_observed: date | None = None
    footprint: np.ndarray | None = None
    observations: list[LakeObservation] = field(default_factory=list)
    merged_from: tuple[str, ...] = ()
    split_from: str | None = None
    upstream_of: str | None = None
    active: bool = True

    @property
    def latest_area_m2(self) -> float | None:
        for observation in reversed(self.observations):
            if observation.state == STATE_OBSERVED:
                return observation.area_m2
        return None

    def area_series(self) -> list[tuple[date, float | None]]:
        """(date, area) with ``None`` where the lake was not observed.

        Feeds ``analysis.change``, which treats a ``None`` as a gap and never
        interpolates it.
        """
        return [(o.obs_date, o.area_m2) for o in self.observations]

    def describe(self) -> str:
        lineage = []
        if self.merged_from:
            lineage.append(f"absorbed {', '.join(self.merged_from)}")
        if self.split_from:
            lineage.append(f"split from {self.split_from}")
        suffix = f" [{'; '.join(lineage)}]" if lineage else ""
        return (
            f"{self.lake_id}: {len(self.observations)} observation(s), "
            f"first seen {self.first_seen}, "
            f"latest area {self.latest_area_m2:,.0f} m2"
            if self.latest_area_m2 is not None
            else f"{self.lake_id}: {len(self.observations)} observation(s)"
        ) + suffix


class LakeTracker:
    """Assigns stable identities to lakes across dates.

    Usage::

        tracker = LakeTracker(cfg, pixel_area_m2=100.0)
        tracker.update(date(2023, 10, 19), lakes=[mask_a], observable=valid)
        tracker.update(date(2023, 10, 24), lakes=[mask_a2, mask_b], observable=valid)
    """

    def __init__(
        self,
        cfg: "Config",
        *,
        pixel_area_m2: float,
        start_index: int = 1,
    ) -> None:
        self.cfg = cfg
        self.settings = cfg.detection.barrier_lake
        self.pixel_area_m2 = float(pixel_area_m2)
        self.lakes: dict[str, TrackedLake] = {}
        self.events: list[LakeEvent] = []
        self._next_index = start_index

    # -- identity ---------------------------------------------------------- #

    def _new_id(self) -> str:
        code = f"{self.settings.code_prefix}-{self._next_index:03d}"
        self._next_index += 1
        return code

    @staticmethod
    def _overlap_fraction(a: np.ndarray, b: np.ndarray) -> float:
        """Shared pixels as a fraction of the smaller mask."""
        smaller = min(int(np.count_nonzero(a)), int(np.count_nonzero(b)))
        if smaller == 0:
            return 0.0
        return float(np.count_nonzero(a & b) / smaller)

    # -- the step ----------------------------------------------------------- #

    def update(
        self,
        obs_date: date,
        *,
        lakes: Sequence[np.ndarray],
        observable: np.ndarray | None = None,
        water: np.ndarray | None = None,
        upstream_of: str | None = None,
    ) -> list[LakeEvent]:
        """Fold one date's lakes into the tracked set.

        Args:
            lakes: this date's lake masks, each a connected water body.
            observable: where this date could be measured at all. Used to tell
                a disappearance from a missed observation; without it, absence
                is treated as **not observed**, the cautious reading.
            water: all water on this date, not only the qualifying lakes.
                Needed to tell a lake that has gone from one that was merely
                re-partitioned -- being unmatched means no *lake* overlapped
                the footprint, which is not the same as the footprint being
                dry. Without it no disappearance is claimed at all.
            upstream_of: the dam code these lakes sit behind, recorded on any
                newly created lake.

        Returns:
            The events raised on this date.
        """
        current = [np.asarray(m, dtype=bool) for m in lakes]
        current = [m for m in current if m.any()]
        previous = {
            lake_id: lake
            for lake_id, lake in self.lakes.items()
            if lake.active and lake.footprint is not None
        }

        threshold = self.settings.match_min_overlap_fraction
        matches: dict[int, list[str]] = {i: [] for i in range(len(current))}
        reverse: dict[str, list[int]] = {lake_id: [] for lake_id in previous}
        for index, mask in enumerate(current):
            for lake_id, lake in previous.items():
                if self._overlap_fraction(mask, lake.footprint) >= threshold:
                    matches[index].append(lake_id)
                    reverse[lake_id].append(index)

        events: list[LakeEvent] = []
        claimed: set[str] = set()

        for index, mask in enumerate(current):
            area = float(np.count_nonzero(mask) * self.pixel_area_m2)
            candidates = [lid for lid in matches[index] if lid not in claimed]

            if not candidates:
                lake_id = self._new_id()
                # A new body that overlaps a lake which also matched elsewhere
                # is a split fragment, not an unrelated appearance.
                parent = next(
                    (lid for lid in matches[index] if len(reverse[lid]) > 1), None
                )
                lake = TrackedLake(
                    lake_id=lake_id,
                    first_seen=obs_date,
                    split_from=parent,
                    upstream_of=upstream_of,
                )
                self.lakes[lake_id] = lake
                events.append(
                    LakeEvent(
                        kind=EVENT_SPLIT if parent else EVENT_APPEARED,
                        obs_date=obs_date,
                        lake_id=lake_id,
                        related_ids=(parent,) if parent else (),
                    )
                )
            else:
                # Identity follows mass: the largest contributor survives.
                candidates.sort(
                    key=lambda lid: int(np.count_nonzero(previous[lid].footprint)),
                    reverse=True,
                )
                lake_id = candidates[0]
                lake = self.lakes[lake_id]
                absorbed = tuple(candidates[1:])
                if absorbed:
                    lake.merged_from = tuple(lake.merged_from) + absorbed
                    for other in absorbed:
                        self.lakes[other].active = False
                        claimed.add(other)
                    events.append(
                        LakeEvent(
                            kind=EVENT_MERGED,
                            obs_date=obs_date,
                            lake_id=lake_id,
                            related_ids=absorbed,
                        )
                    )
                else:
                    events.append(
                        LakeEvent(
                            kind=EVENT_CONTINUED, obs_date=obs_date, lake_id=lake_id
                        )
                    )
                claimed.add(lake_id)

            lake = self.lakes[lake_id]
            lake.footprint = mask
            lake.last_observed = obs_date
            lake.active = True
            lake.observations.append(
                LakeObservation(
                    lake_id=lake_id,
                    obs_date=obs_date,
                    state=STATE_OBSERVED,
                    area_m2=area,
                )
            )

        # Lakes that were not matched this date.
        for lake_id, lake in previous.items():
            if lake_id in claimed:
                continue
            events.append(self._unmatched(lake, obs_date, observable, water))

        self.events.extend(events)
        for event in events:
            log.info("%s", event.describe())
        return events

    def _residual_water_fraction(
        self, footprint: np.ndarray, water: np.ndarray | None
    ) -> float:
        """How much of a lake's last footprint still holds water.

        Returns 0.0 when there is no water mask to test against, which is only
        ever used alongside an explicit check that ``water is None`` -- a lake
        is never declared absent on the strength of this zero.
        """
        if water is None:
            return 0.0
        total = int(np.count_nonzero(footprint))
        if not total:
            return 0.0
        wet = np.asarray(water, dtype=bool)
        return float(np.count_nonzero(footprint & wet) / total)

    def _unmatched(
        self,
        lake: TrackedLake,
        obs_date: date,
        observable: np.ndarray | None,
        water: np.ndarray | None = None,
    ) -> LakeEvent:
        """Decide whether an unmatched lake disappeared or was simply unseen.

        This is the module's central judgement. A barrier lake vanishing reads
        as a breach, so the bar for saying it is set deliberately high.

        **The bar used to be high on observability and absent on water.** Being
        "unmatched" means no *qualifying lake* overlapped the footprint, which
        is not the same as the footprint being dry: a growing lake that merges
        into the river channel, or stops qualifying as new or expanding, is
        unmatched while plainly still full of water. On the Baige 2018 event
        this reported four lakes as disappeared -- claiming each "held no
        water" -- on a date when the lake had grown from 166,800 to 294,000 m2
        and 40.9% of the largest footprint was still water. That is the
        false-breach signal this module exists to avoid.

        So ``water`` is now tested directly. Without it, no absence is claimed
        at all, because the message would be asserting something unmeasured.
        """
        footprint = lake.footprint
        if observable is None:
            fraction = None
            reason = (
                "no observability mask supplied, so an absence cannot be "
                "distinguished from a missed observation"
            )
            state, kind = STATE_NOT_OBSERVED, EVENT_NOT_OBSERVED
        else:
            visible = np.asarray(observable, dtype=bool)
            total = int(np.count_nonzero(footprint))
            fraction = (
                float(np.count_nonzero(footprint & visible) / total) if total else 0.0
            )
            residual = self._residual_water_fraction(footprint, water)

            if water is None:
                # Cannot say the footprint held no water without looking.
                state, kind = STATE_NOT_OBSERVED, EVENT_NOT_OBSERVED
                reason = (
                    "no water mask supplied for this date, so a disappearance "
                    "cannot be distinguished from a re-partitioned water body"
                )
            elif residual >= self.settings.min_residual_water_fraction:
                # Still wet: the body was re-partitioned, not lost.
                state, kind = STATE_OBSERVED, EVENT_REPARTITIONED
                reason = (
                    f"no qualifying lake matched this footprint, but "
                    f"{residual:.0%} of it still holds water (at or above the "
                    f"{self.settings.min_residual_water_fraction:.0%} "
                    f"threshold), so this is a re-partitioned water body and "
                    f"NOT a disappearance"
                )
            elif fraction >= self.settings.min_observable_fraction:
                state, kind = STATE_ABSENT, EVENT_DISAPPEARED
                reason = (
                    f"{fraction:.0%} of the last known footprint was observable "
                    f"and only {residual:.0%} of it still holds water"
                )
            else:
                state, kind = STATE_NOT_OBSERVED, EVENT_NOT_OBSERVED
                reason = (
                    f"only {fraction:.0%} of the last known footprint was "
                    f"observable, below the "
                    f"{self.settings.min_observable_fraction:.0%} required to "
                    "call this a disappearance"
                )

        # A re-partitioned lake was measured, so it reports the area that is
        # still water rather than None. Its footprint narrows to that water, so
        # the next date is matched against what is actually there.
        residual_area = None
        if kind == EVENT_REPARTITIONED:
            still_wet = footprint & np.asarray(water, dtype=bool)
            residual_area = float(np.count_nonzero(still_wet) * self.pixel_area_m2)
            lake.footprint = still_wet

        lake.observations.append(
            LakeObservation(
                lake_id=lake.lake_id,
                obs_date=obs_date,
                state=state,
                area_m2=residual_area,
                observable_fraction=fraction,
                reason=reason,
            )
        )
        if state == STATE_ABSENT:
            lake.active = False
        return LakeEvent(
            kind=kind, obs_date=obs_date, lake_id=lake.lake_id, reason=reason
        )

    # -- reporting ---------------------------------------------------------- #

    def active_lakes(self) -> list[TrackedLake]:
        return [lake for lake in self.lakes.values() if lake.active]

    def events_of(self, kind: str) -> list[LakeEvent]:
        return [event for event in self.events if event.kind == kind]

    def summary(self) -> str:
        counts = {kind: len(self.events_of(kind)) for kind in EVENTS}
        parts = ", ".join(f"{k} {v}" for k, v in counts.items() if v)
        return (
            f"{len(self.lakes)} lake(s) tracked, {len(self.active_lakes())} active"
            + (f"; events: {parts}" if parts else "")
        )
