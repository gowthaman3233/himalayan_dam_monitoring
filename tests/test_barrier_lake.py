"""Barrier lake detection and tracking (brief, Section 7.7).

Scenes are hand-built: a channel down a grid, a blockage part-way along it,
and water masks before and after. The sharpest assertions are about what the
tracker refuses to say -- that a lake hidden by cloud has disappeared.
"""

from __future__ import annotations

from datetime import date, timedelta

import numpy as np
import pytest

from config.schema import Config
from detection.barrier_lake import (
    EVENT_APPEARED,
    EVENT_CONTINUED,
    EVENT_DISAPPEARED,
    EVENT_MERGED,
    EVENT_NOT_OBSERVED,
    EVENT_REPARTITIONED,
    EVENT_SPLIT,
    STATE_ABSENT,
    STATE_NOT_OBSERVED,
    STATE_OBSERVED,
    LakeTracker,
    find_barrier_lakes,
)

pytestmark = pytest.mark.synthetic

CELLSIZE = 10.0
PIXEL_AREA = CELLSIZE * CELLSIZE
SIZE = 60
CHANNEL_COL = 30
BLOCK_ROW = 30
START = date(2023, 10, 1)


def replace_lake_config(cfg: Config, **overrides) -> Config:
    data = cfg.model_dump(mode="python")
    data["detection"]["barrier_lake"].update(overrides)
    return Config.model_validate(data)


def valley():
    """Channel top (upstream) to bottom; accumulation rises with row."""
    streams = np.zeros((SIZE, SIZE), dtype=bool)
    streams[:, CHANNEL_COL] = True
    accumulation = np.tile((np.arange(SIZE, dtype=float) + 1.0) * 100.0, (SIZE, 1)).T
    water = np.zeros((SIZE, SIZE), dtype=bool)
    water[:, CHANNEL_COL - 1 : CHANNEL_COL + 2] = True
    site = np.zeros((SIZE, SIZE), dtype=bool)
    site[BLOCK_ROW : BLOCK_ROW + 3, CHANNEL_COL] = True
    return {
        "streams": streams,
        "flow_accumulation": accumulation,
        "water_pre": water,
        "blockage_site": site,
    }


def lake_mask(top: int, bottom: int, half_width: int = 6) -> np.ndarray:
    mask = np.zeros((SIZE, SIZE), dtype=bool)
    mask[top:bottom, CHANNEL_COL - half_width : CHANNEL_COL + half_width + 1] = True
    return mask


def find(cfg: Config, water_post, **overrides):
    base = valley()
    kwargs = dict(
        blockage_site=base["blockage_site"],
        streams=base["streams"],
        water_post=water_post,
        water_pre=base["water_pre"],
        flow_accumulation=base["flow_accumulation"],
        cellsize_m=CELLSIZE,
        pixel_area_m2=PIXEL_AREA,
        dam_code="ND-001",
    )
    kwargs.update(overrides)
    return find_barrier_lakes(cfg, **kwargs)


# --------------------------------------------------------------------------- #
# Finding the lake
# --------------------------------------------------------------------------- #


class TestFindBarrierLakes:
    def test_6_water_accumulating_upstream_is_a_barrier_lake(
        self, cfg: Config
    ) -> None:
        """Required system test 6."""
        base = valley()
        post = base["water_pre"] | lake_mask(BLOCK_ROW - 15, BLOCK_ROW - 1)
        candidates = find(cfg, post)
        assert len(candidates) == 1
        assert candidates[0].upstream_of == "ND-001"
        assert candidates[0].new_area_m2 > 0

    def test_a_lake_downstream_is_not_a_barrier_lake(self, cfg: Config) -> None:
        """Direction is the point: water below a blockage is not impounded."""
        base = valley()
        post = base["water_pre"] | lake_mask(BLOCK_ROW + 6, BLOCK_ROW + 20)
        assert find(cfg, post) == []

    def test_unchanged_pre_existing_water_is_not_a_barrier_lake(
        self, cfg: Config
    ) -> None:
        """Section 7.7 requires new or expanding, not merely present."""
        base = valley()
        assert find(cfg, base["water_pre"]) == []

    def test_an_expanding_pre_existing_lake_qualifies(self, cfg: Config) -> None:
        base = valley()
        pre = base["water_pre"] | lake_mask(BLOCK_ROW - 10, BLOCK_ROW - 5, 3)
        post = base["water_pre"] | lake_mask(BLOCK_ROW - 15, BLOCK_ROW - 1, 6)
        candidates = find(cfg, post, water_pre=pre)
        assert len(candidates) == 1
        assert candidates[0].qualifies_as == "expanding"
        assert candidates[0].expansion_fraction > 0.1

    def test_a_slightly_changed_lake_does_not_qualify(self, cfg: Config) -> None:
        base = valley()
        pre = base["water_pre"] | lake_mask(BLOCK_ROW - 15, BLOCK_ROW - 1, 6)
        post = pre.copy()
        post[BLOCK_ROW - 16, CHANNEL_COL] = True  # one extra pixel
        assert find(cfg, post, water_pre=pre) == []

    def test_without_flow_accumulation_nothing_is_returned(
        self, cfg: Config
    ) -> None:
        """Upstream cannot be guessed."""
        base = valley()
        post = base["water_pre"] | lake_mask(BLOCK_ROW - 15, BLOCK_ROW - 1)
        assert find(cfg, post, flow_accumulation=None) == []

    def test_reversing_the_flow_reverses_which_lake_qualifies(
        self, cfg: Config
    ) -> None:
        base = valley()
        upstream_lake = base["water_pre"] | lake_mask(BLOCK_ROW - 15, BLOCK_ROW - 1)
        flipped = base["flow_accumulation"][::-1, :].copy()
        assert find(cfg, upstream_lake) != []
        assert find(cfg, upstream_lake, flow_accumulation=flipped) == []

    def test_no_blockage_site_gives_nothing(self, cfg: Config) -> None:
        base = valley()
        post = base["water_pre"] | lake_mask(BLOCK_ROW - 15, BLOCK_ROW - 1)
        assert find(cfg, post, blockage_site=np.zeros((SIZE, SIZE), bool)) == []

    def test_small_bodies_are_ignored(self, cfg: Config) -> None:
        base = valley()
        tiny = np.zeros((SIZE, SIZE), dtype=bool)
        tiny[BLOCK_ROW - 5, CHANNEL_COL] = True
        assert find(cfg, base["water_pre"] | tiny) == []


# --------------------------------------------------------------------------- #
# Tracking identity
# --------------------------------------------------------------------------- #


class TestTracking:
    def tracker(self, cfg: Config) -> LakeTracker:
        return LakeTracker(cfg, pixel_area_m2=PIXEL_AREA)

    def test_a_lake_keeps_its_id_across_dates(self, cfg: Config) -> None:
        tracker = self.tracker(cfg)
        tracker.update(START, lakes=[lake_mask(10, 20)])
        tracker.update(START + timedelta(days=5), lakes=[lake_mask(10, 22)])
        assert len(tracker.lakes) == 1
        lake = next(iter(tracker.lakes.values()))
        assert lake.lake_id == "BL-001"
        assert len(lake.observations) == 2
        assert tracker.events_of(EVENT_CONTINUED)

    def test_ids_follow_the_configured_prefix(self, cfg: Config) -> None:
        tracker = LakeTracker(
            replace_lake_config(cfg, code_prefix="LAKE"), pixel_area_m2=PIXEL_AREA
        )
        tracker.update(START, lakes=[lake_mask(10, 20)])
        assert next(iter(tracker.lakes)).startswith("LAKE-")

    def test_a_growing_lake_series_feeds_the_trend_analysis(
        self, cfg: Config
    ) -> None:
        """The series hands straight to analysis.change."""
        from analysis.change import AreaObservation, analyse_trend

        tracker = self.tracker(cfg)
        for step, bottom in enumerate((16, 20, 24, 28)):
            tracker.update(
                START + timedelta(days=step * 10), lakes=[lake_mask(10, bottom)]
            )
        lake = next(iter(tracker.lakes.values()))

        observations = [
            AreaObservation(obs_date=d, area_m2=a)
            for d, a in lake.area_series()
            if a is not None
        ]
        trend = analyse_trend(cfg, observations, reference_date=observations[-1].obs_date)
        assert trend.trend == "Increasing"

    def test_a_new_unrelated_lake_appears(self, cfg: Config) -> None:
        tracker = self.tracker(cfg)
        tracker.update(START, lakes=[lake_mask(10, 20)])
        tracker.update(
            START + timedelta(days=5), lakes=[lake_mask(10, 20), lake_mask(40, 50)]
        )
        assert len(tracker.lakes) == 2
        assert len(tracker.events_of(EVENT_APPEARED)) == 2  # both first sightings

    def test_two_lakes_merging_keep_the_larger_identity(self, cfg: Config) -> None:
        """Identity follows mass."""
        tracker = self.tracker(cfg)
        big, small = lake_mask(10, 24), lake_mask(28, 32)
        tracker.update(START, lakes=[big, small])
        big_id, small_id = "BL-001", "BL-002"
        assert set(tracker.lakes) == {big_id, small_id}

        tracker.update(START + timedelta(days=5), lakes=[lake_mask(10, 32)])
        merged = tracker.events_of(EVENT_MERGED)
        assert len(merged) == 1
        assert merged[0].lake_id == big_id
        assert small_id in merged[0].related_ids
        assert tracker.lakes[big_id].active
        assert not tracker.lakes[small_id].active
        assert small_id in tracker.lakes[big_id].merged_from

    def test_a_lake_splitting_keeps_the_identity_on_the_larger_part(
        self, cfg: Config
    ) -> None:
        tracker = self.tracker(cfg)
        tracker.update(START, lakes=[lake_mask(10, 32)])
        tracker.update(
            START + timedelta(days=5), lakes=[lake_mask(10, 24), lake_mask(28, 32)]
        )
        assert tracker.lakes["BL-001"].active
        splits = tracker.events_of(EVENT_SPLIT)
        assert len(splits) == 1
        fragment = tracker.lakes[splits[0].lake_id]
        assert fragment.split_from == "BL-001"

    def test_summary_counts_the_events(self, cfg: Config) -> None:
        tracker = self.tracker(cfg)
        tracker.update(START, lakes=[lake_mask(10, 20)])
        assert "1 lake(s) tracked" in tracker.summary()


# --------------------------------------------------------------------------- #
# A lake that cannot be seen has not disappeared
# --------------------------------------------------------------------------- #


class TestDisappearanceRequiresVisibility:
    def tracker(self, cfg: Config) -> LakeTracker:
        return LakeTracker(cfg, pixel_area_m2=PIXEL_AREA)

    def test_cloud_over_the_lake_is_not_a_disappearance(self, cfg: Config) -> None:
        """The central rule. A breach signal must not come from weather."""
        tracker = self.tracker(cfg)
        footprint = lake_mask(10, 20)
        tracker.update(START, lakes=[footprint])

        clouded = np.ones((SIZE, SIZE), dtype=bool)
        clouded[footprint] = False  # nothing of the lake is observable
        # A dry water mask is supplied so visibility is the ONLY thing under
        # test: the footprint really is empty, and must still not be called a
        # disappearance because it could not be seen.
        events = tracker.update(
            START + timedelta(days=5), lakes=[], observable=clouded,
            water=np.zeros((SIZE, SIZE), dtype=bool),
        )

        assert [e.kind for e in events] == [EVENT_NOT_OBSERVED]
        assert tracker.lakes["BL-001"].active, "identity is kept while unseen"
        last = tracker.lakes["BL-001"].observations[-1]
        assert last.state == STATE_NOT_OBSERVED
        assert last.area_m2 is None
        assert "below the" in last.reason

    def test_a_visible_empty_footprint_is_a_disappearance(self, cfg: Config) -> None:
        tracker = self.tracker(cfg)
        tracker.update(START, lakes=[lake_mask(10, 20)])
        events = tracker.update(
            START + timedelta(days=5),
            lakes=[],
            observable=np.ones((SIZE, SIZE), dtype=bool),
            water=np.zeros((SIZE, SIZE), dtype=bool),
        )
        assert [e.kind for e in events] == [EVENT_DISAPPEARED]
        assert not tracker.lakes["BL-001"].active
        assert tracker.lakes["BL-001"].observations[-1].state == STATE_ABSENT

    def test_partial_visibility_below_the_threshold_is_not_observed(
        self, cfg: Config
    ) -> None:
        tracker = self.tracker(cfg)
        footprint = lake_mask(10, 20)
        tracker.update(START, lakes=[footprint])

        rows = np.nonzero(footprint.any(axis=1))[0]
        observable = np.ones((SIZE, SIZE), dtype=bool)
        observable[rows[: int(len(rows) * 0.8)], :] = False  # only 20% visible
        events = tracker.update(
            START + timedelta(days=5), lakes=[], observable=observable
        )
        assert [e.kind for e in events] == [EVENT_NOT_OBSERVED]

    def test_the_visibility_threshold_is_configurable(self, cfg: Config) -> None:
        lenient = replace_lake_config(cfg, min_observable_fraction=0.1)
        tracker = LakeTracker(lenient, pixel_area_m2=PIXEL_AREA)
        footprint = lake_mask(10, 20)
        tracker.update(START, lakes=[footprint])

        rows = np.nonzero(footprint.any(axis=1))[0]
        observable = np.ones((SIZE, SIZE), dtype=bool)
        observable[rows[: int(len(rows) * 0.8)], :] = False
        events = tracker.update(
            START + timedelta(days=5), lakes=[], observable=observable,
            water=np.zeros((SIZE, SIZE), dtype=bool),
        )
        assert [e.kind for e in events] == [EVENT_DISAPPEARED]

    def test_without_an_observability_mask_absence_is_not_a_disappearance(
        self, cfg: Config
    ) -> None:
        """The cautious reading when we were not told what could be seen."""
        tracker = self.tracker(cfg)
        tracker.update(START, lakes=[lake_mask(10, 20)])
        events = tracker.update(START + timedelta(days=5), lakes=[])
        assert [e.kind for e in events] == [EVENT_NOT_OBSERVED]
        assert tracker.lakes["BL-001"].active

    def test_an_unseen_lake_can_be_picked_up_again(self, cfg: Config) -> None:
        tracker = self.tracker(cfg)
        footprint = lake_mask(10, 20)
        tracker.update(START, lakes=[footprint])

        clouded = np.ones((SIZE, SIZE), dtype=bool)
        clouded[footprint] = False
        tracker.update(START + timedelta(days=5), lakes=[], observable=clouded)
        tracker.update(START + timedelta(days=10), lakes=[lake_mask(10, 22)])

        lake = tracker.lakes["BL-001"]
        assert len(tracker.lakes) == 1, "it did not become a second lake"
        states = [o.state for o in lake.observations]
        assert states == [STATE_OBSERVED, STATE_NOT_OBSERVED, STATE_OBSERVED]

    def test_a_not_observed_date_is_a_gap_in_the_series(self, cfg: Config) -> None:
        """Hands to analysis.change as a gap, which is never interpolated."""
        tracker = self.tracker(cfg)
        footprint = lake_mask(10, 20)
        tracker.update(START, lakes=[footprint])
        clouded = np.ones((SIZE, SIZE), dtype=bool)
        clouded[footprint] = False
        tracker.update(START + timedelta(days=5), lakes=[], observable=clouded)

        series = tracker.lakes["BL-001"].area_series()
        assert series[1][1] is None


# --------------------------------------------------------------------------- #
# The upstream/downstream partition
# --------------------------------------------------------------------------- #


class TestProximityPartition:
    """Two wide dilations overlap and cancel; a joint growth does not."""

    def test_each_pixel_joins_the_nearer_side(self) -> None:
        from detection.barrier_lake import _partition_by_proximity

        up_seed = np.zeros((21, 21), dtype=bool)
        up_seed[0, 10] = True          # top of the grid
        down_seed = np.zeros((21, 21), dtype=bool)
        down_seed[20, 10] = True       # bottom

        upstream, downstream = _partition_by_proximity(up_seed, down_seed, 20)
        assert upstream[3, 10] and not downstream[3, 10]
        assert downstream[17, 10] and not upstream[17, 10]

    def test_the_two_regions_never_overlap(self) -> None:
        from detection.barrier_lake import _partition_by_proximity

        up_seed = np.zeros((21, 21), dtype=bool)
        up_seed[0, :] = True
        down_seed = np.zeros((21, 21), dtype=bool)
        down_seed[20, :] = True

        upstream, downstream = _partition_by_proximity(up_seed, down_seed, 30)
        assert not (upstream & downstream).any()

    def test_a_contested_midline_joins_neither(self) -> None:
        from detection.barrier_lake import _partition_by_proximity

        up_seed = np.zeros((11, 11), dtype=bool)
        up_seed[0, :] = True
        down_seed = np.zeros((11, 11), dtype=bool)
        down_seed[10, :] = True

        upstream, downstream = _partition_by_proximity(up_seed, down_seed, 10)
        assert not upstream[5].any() and not downstream[5].any()

    def test_zero_steps_returns_the_seeds(self) -> None:
        from detection.barrier_lake import _partition_by_proximity

        up_seed = np.zeros((5, 5), dtype=bool)
        up_seed[0, 0] = True
        down_seed = np.zeros((5, 5), dtype=bool)
        down_seed[4, 4] = True

        upstream, downstream = _partition_by_proximity(up_seed, down_seed, 0)
        assert np.array_equal(upstream, up_seed)
        assert np.array_equal(downstream, down_seed)


# --------------------------------------------------------------------------- #
# A lake that is still wet has not disappeared -- forced by Baige 2018
# --------------------------------------------------------------------------- #
class TestWetFootprintIsNotADisappearance:
    """Being unmatched is not the same as being dry.

    A lake that grows into the river channel, or stops qualifying as new or
    expanding, matches nothing and yet is plainly still full of water. The old
    logic called that a disappearance and said the footprint "held no water",
    which it had never tested. On the real Baige 2018 event it reported four
    lakes gone on a date when the lake had grown from 166,800 to 294,000 m2
    and 40.9% of the largest footprint was still water.

    A false breach signal is the worst output this system can produce, so
    these tests are the ones that matter most in this module.
    """

    def tracker(self, cfg: Config) -> LakeTracker:
        return LakeTracker(cfg, pixel_area_m2=PIXEL_AREA)

    def test_a_wet_unmatched_footprint_is_repartitioned_not_gone(
        self, cfg: Config
    ) -> None:
        tracker = self.tracker(cfg)
        footprint = lake_mask(10, 20)
        tracker.update(START, lakes=[footprint])

        # The water is all still there; it simply did not qualify as a lake.
        events = tracker.update(
            START + timedelta(days=5),
            lakes=[],
            observable=np.ones((SIZE, SIZE), dtype=bool),
            water=footprint,
        )
        assert [e.kind for e in events] == [EVENT_REPARTITIONED]
        assert tracker.lakes["BL-001"].active, "a wet lake must keep its identity"

    def test_a_repartitioned_lake_reports_the_area_still_wet(
        self, cfg: Config
    ) -> None:
        """It was measured, so it reports a number rather than a gap."""
        tracker = self.tracker(cfg)
        footprint = lake_mask(10, 20)
        tracker.update(START, lakes=[footprint])

        half = footprint.copy()
        rows = np.nonzero(footprint.any(axis=1))[0]
        half[rows[: len(rows) // 2], :] = False

        tracker.update(
            START + timedelta(days=5),
            lakes=[],
            observable=np.ones((SIZE, SIZE), dtype=bool),
            water=half,
        )
        last = tracker.lakes["BL-001"].observations[-1]
        assert last.state == STATE_OBSERVED
        assert last.area_m2 == pytest.approx(int(half.sum()) * PIXEL_AREA)
        assert "NOT a disappearance" in last.reason

    def test_a_truly_dry_footprint_still_disappears(self, cfg: Config) -> None:
        """The fix must not disable the disappearance it guards."""
        tracker = self.tracker(cfg)
        tracker.update(START, lakes=[lake_mask(10, 20)])
        events = tracker.update(
            START + timedelta(days=5),
            lakes=[],
            observable=np.ones((SIZE, SIZE), dtype=bool),
            water=np.zeros((SIZE, SIZE), dtype=bool),
        )
        assert [e.kind for e in events] == [EVENT_DISAPPEARED]
        assert not tracker.lakes["BL-001"].active

    def test_without_a_water_mask_no_disappearance_is_claimed(
        self, cfg: Config
    ) -> None:
        """The message asserted something unmeasured; now it refuses to."""
        tracker = self.tracker(cfg)
        tracker.update(START, lakes=[lake_mask(10, 20)])
        events = tracker.update(
            START + timedelta(days=5),
            lakes=[],
            observable=np.ones((SIZE, SIZE), dtype=bool),
        )
        assert [e.kind for e in events] == [EVENT_NOT_OBSERVED]
        assert tracker.lakes["BL-001"].active
        assert "re-partitioned" in tracker.lakes["BL-001"].observations[-1].reason

    def test_the_residual_threshold_is_read_from_config(self, cfg: Config) -> None:
        """A trace of water is enough by default; a strict setting overrides."""
        footprint = lake_mask(10, 20)
        rows = np.nonzero(footprint.any(axis=1))[0]
        trace = footprint.copy()
        trace[rows[1:], :] = False  # roughly a tenth of the footprint
        residual = int(trace.sum()) / int(footprint.sum())

        lenient = replace_lake_config(
            cfg, min_residual_water_fraction=residual / 2.0
        )
        tracker = LakeTracker(lenient, pixel_area_m2=PIXEL_AREA)
        tracker.update(START, lakes=[footprint])
        events = tracker.update(
            START + timedelta(days=5), lakes=[],
            observable=np.ones((SIZE, SIZE), dtype=bool), water=trace,
        )
        assert [e.kind for e in events] == [EVENT_REPARTITIONED]

        strict = replace_lake_config(
            cfg, min_residual_water_fraction=min(residual * 2.0, 1.0)
        )
        tracker = LakeTracker(strict, pixel_area_m2=PIXEL_AREA)
        tracker.update(START, lakes=[footprint])
        events = tracker.update(
            START + timedelta(days=5), lakes=[],
            observable=np.ones((SIZE, SIZE), dtype=bool), water=trace,
        )
        assert [e.kind for e in events] == [EVENT_DISAPPEARED]

    def test_cloud_still_outranks_a_dry_footprint(self, cfg: Config) -> None:
        """Visibility is checked before absence, and that order is kept."""
        tracker = self.tracker(cfg)
        footprint = lake_mask(10, 20)
        tracker.update(START, lakes=[footprint])

        clouded = np.ones((SIZE, SIZE), dtype=bool)
        clouded[footprint] = False
        events = tracker.update(
            START + timedelta(days=5), lakes=[], observable=clouded,
            water=np.zeros((SIZE, SIZE), dtype=bool),
        )
        assert [e.kind for e in events] == [EVENT_NOT_OBSERVED]


# --------------------------------------------------------------------------- #
# "On the same stream" -- Section 7.7's other half, forced by Baige 2018
# --------------------------------------------------------------------------- #
class TestUpstreamMustBeOnTheSameStream:
    """A low accumulation value does not put a pixel upstream of a blockage.

    Section 7.7 requires the lake to be upstream of the candidate **on the
    same stream**. Selecting by accumulation inside a box around the blockage
    honours only the first half: every small tributary in that box has a low
    value and so reads as upstream, connected to the dam or not.

    Baige 2018 showed what it costs. The impounded reach reported for one date
    spanned rows 154-289 and for the next rows 424-598 -- a different part of
    the valley -- because the zone picked up whichever unrelated tributaries
    held water that day. Consecutive dates' lakes overlapped by exactly 0
    pixels while 40% of the water persisted, so no lake kept an identity and
    trend analysis was impossible. Tracing the reach along the network cut the
    IDs minted over four dates from eight to one.
    """

    def _with_detached_tributary(self):
        """A valley plus a separate low-accumulation stream that never joins.

        The tributary sits well away from the channel and drains off the far
        side of the grid, so nothing connects it to the blockage. Its
        accumulation is low, which is exactly what used to make it 'upstream'.
        """
        base = valley()
        streams = base["streams"].copy()
        accumulation = base["flow_accumulation"].copy()
        detached_col = CHANNEL_COL + 20
        streams[:, detached_col] = True
        accumulation[:, detached_col] = 50.0  # far below the site's value
        base["streams"] = streams
        base["flow_accumulation"] = accumulation
        base["detached_col"] = detached_col
        return base

    def test_water_on_a_detached_stream_is_not_a_barrier_lake(
        self, cfg: Config
    ) -> None:
        base = self._with_detached_tributary()
        col = base["detached_col"]

        # A large new water body on the detached stream, upstream-ish by row.
        water_post = base["water_pre"].copy()
        water_post[BLOCK_ROW - 20 : BLOCK_ROW - 2, col - 4 : col + 5] = True

        # lake_width_m is narrowed so the zone cannot reach the detached
        # stream by sheer width. At the shipped 300 m the zone legitimately
        # dilates 30 px in every direction and would cover a tributary only
        # 20 px away -- which is a real residual limitation, recorded as an
        # open item, but not what this test is about.
        narrow = replace_lake_config(cfg, lake_width_m=50.0)
        lakes = find(
            narrow, water_post,
            streams=base["streams"],
            flow_accumulation=base["flow_accumulation"],
            water_pre=base["water_pre"],
        )
        for lake in lakes:
            assert not lake.mask[:, col - 4 : col + 5].any(), (
                "water on a stream that does not reach the blockage was "
                "reported as impounded behind it"
            )

    def test_a_real_impoundment_on_the_blocked_stream_is_still_found(
        self, cfg: Config
    ) -> None:
        """The connectivity requirement must not cost the true detection."""
        base = self._with_detached_tributary()
        water_post = base["water_pre"].copy()
        water_post[BLOCK_ROW - 20 : BLOCK_ROW - 2,
                   CHANNEL_COL - 6 : CHANNEL_COL + 7] = True

        lakes = find(
            replace_lake_config(cfg, lake_width_m=50.0), water_post,
            streams=base["streams"],
            flow_accumulation=base["flow_accumulation"],
            water_pre=base["water_pre"],
        )
        assert lakes, "the impoundment on the blocked stream was lost"
        assert max(l.area_m2 for l in lakes) > 0.0


class TestBlockageStraddlingAConfluence:
    """The upstream reference is the blockage's own most downstream point.

    Accumulation rises monotonically downstream, so a blockage's MAXIMUM marks
    its outlet and everything above the obstruction lies strictly below that.
    The median fails wherever a blockage straddles a confluence, which is the
    common case -- a landslide dams a main stem just below a tributary mouth.

    On Baige 2018 the ND-007 site spanned 20,817 to 56,484 cells. The median
    of 20,856 was dragged down by tributary pixels and put the main stem, at
    56,484 and carrying the whole impoundment, on the DOWNSTREAM side; every
    water component was then rejected as 'growth not upstream'.
    """

    def _confluence(self):
        """A main stem joined by a tributary, blocked across both."""
        streams = np.zeros((SIZE, SIZE), dtype=bool)
        streams[:, CHANNEL_COL] = True  # main stem, top to bottom
        tributary_col = CHANNEL_COL - 8
        streams[:BLOCK_ROW, tributary_col] = True
        streams[BLOCK_ROW, tributary_col:CHANNEL_COL] = True  # the junction

        accumulation = np.tile(
            (np.arange(SIZE, dtype=float) + 1.0) * 1000.0, (SIZE, 1)
        ).T
        # The tributary carries far less water than the main stem.
        accumulation[:BLOCK_ROW, tributary_col] = 50.0
        accumulation[BLOCK_ROW, tributary_col:CHANNEL_COL] = 60.0

        water = np.zeros((SIZE, SIZE), dtype=bool)
        water[:, CHANNEL_COL - 1 : CHANNEL_COL + 2] = True

        # The blockage spans the junction, so its accumulation values range
        # from the tributary's 60 to the main stem's thousands.
        site = np.zeros((SIZE, SIZE), dtype=bool)
        site[BLOCK_ROW, tributary_col:CHANNEL_COL + 1] = True
        site[BLOCK_ROW : BLOCK_ROW + 2, CHANNEL_COL] = True
        return {
            "streams": streams, "flow_accumulation": accumulation,
            "water_pre": water, "blockage_site": site,
        }

    def test_the_main_stem_impoundment_is_found_across_a_confluence(
        self, cfg: Config
    ) -> None:
        base = self._confluence()
        water_post = base["water_pre"].copy()
        water_post[BLOCK_ROW - 20 : BLOCK_ROW - 2,
                   CHANNEL_COL - 6 : CHANNEL_COL + 7] = True

        lakes = find_barrier_lakes(
            cfg,
            blockage_site=base["blockage_site"],
            streams=base["streams"],
            water_post=water_post,
            water_pre=base["water_pre"],
            flow_accumulation=base["flow_accumulation"],
            cellsize_m=CELLSIZE,
            pixel_area_m2=PIXEL_AREA,
            dam_code="ND-001",
        )
        assert lakes, (
            "a blockage straddling a confluence found no lake: the upstream "
            "reference put the main stem downstream of the dam"
        )

    def test_the_site_spans_a_wide_accumulation_range(self) -> None:
        """Guards the fixture: without the spread the test proves nothing."""
        base = self._confluence()
        values = base["flow_accumulation"][base["blockage_site"]]
        assert values.max() > 10.0 * values.min()
