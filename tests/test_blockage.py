"""River blockage candidates (brief, Section 7.6).

Scenes are hand-built: a straight channel running down a grid, a landslide
stamped onto it, and water masks before and after. The central assertion is
negative -- proximity to a river must never, on its own, produce a dam.
"""

from __future__ import annotations

import numpy as np
import pytest
from affine import Affine

from config.schema import Config
from detection.blockage import (
    OBSTRUCTION_SIGNALS,
    candidates_to_frame,
    detect_blockages,
)

pytestmark = pytest.mark.synthetic

CELLSIZE = 10.0
PIXEL_AREA = CELLSIZE * CELLSIZE
UTM45N = "EPSG:32645"
TRANSFORM = Affine(CELLSIZE, 0.0, 450000.0, 0.0, -CELLSIZE, 3085000.0)

SIZE = 60
CHANNEL_COL = 30
BLOCK_ROW = 30


def replace_blockage_config(cfg: Config, **overrides) -> Config:
    data = cfg.model_dump(mode="python")
    section = data["detection"]["blockage"]
    weights = overrides.pop("weights", None)
    if weights is not None:
        section["weights"].update(weights)
    section.update(overrides)
    return Config.model_validate(data)


def scene():
    """A channel running top (upstream) to bottom (downstream).

    Flow accumulation increases with row index, so row 0 is the head of the
    catchment and row 59 its outlet -- which is what tells the detector which
    side of a blockage is upstream.
    """
    streams = np.zeros((SIZE, SIZE), dtype=bool)
    streams[:, CHANNEL_COL] = True

    accumulation = np.tile(
        (np.arange(SIZE, dtype=float) + 1.0) * 100.0, (SIZE, 1)
    ).T  # rises with row

    water = np.zeros((SIZE, SIZE), dtype=bool)
    water[:, CHANNEL_COL - 1 : CHANNEL_COL + 2] = True  # a 3-pixel-wide river

    return {
        "streams": streams,
        "flow_accumulation": accumulation,
        "water_pre": water,
    }


def landslide(touching: bool = True, *, rows=4, far_cols: int = 0):
    """A landslide block reaching the channel, or stopping short of it."""
    mask = np.zeros((SIZE, SIZE), dtype=bool)
    start = CHANNEL_COL + 2 + far_cols
    mask[BLOCK_ROW : BLOCK_ROW + rows, start : start + 8] = True
    if touching:
        mask[BLOCK_ROW : BLOCK_ROW + rows, CHANNEL_COL - 3 : CHANNEL_COL + 3] = True
    return mask


def dammed_water(base: np.ndarray) -> np.ndarray:
    """Water after a blockage: a lake upstream, a dry channel downstream."""
    after = base.copy()
    # New water pooled above the blockage. Deliberately set back from the
    # blockage itself: a real impoundment backs up upstream while the channel
    # at the obstruction is buried under debris, and the narrowing test must
    # measure the buried cross-section, not the lake.
    after[BLOCK_ROW - 22 : BLOCK_ROW - 6, CHANNEL_COL - 6 : CHANNEL_COL + 7] = True
    # The channel below it runs dry.
    after[BLOCK_ROW + 5 : BLOCK_ROW + 25, :] = False
    # And the channel at the blockage is buried.
    after[BLOCK_ROW : BLOCK_ROW + 5, :] = False
    return after


def run(cfg: Config, landslides, water_post=None, **overrides):
    base = scene()
    kwargs = dict(
        landslides=landslides,
        streams=base["streams"],
        flow_accumulation=base["flow_accumulation"],
        water_pre=base["water_pre"],
        water_post=water_post,
        cellsize_m=CELLSIZE,
        pixel_area_m2=PIXEL_AREA,
        transform=TRANSFORM,
        crs=UTM45N,
        pre_date="2023-09-01",
        post_date="2023-10-19",
    )
    kwargs.update(overrides)
    return detect_blockages(cfg, **kwargs)


# --------------------------------------------------------------------------- #
# Required system test 4 -- the negative that matters most
# --------------------------------------------------------------------------- #


class TestProximityAloneIsNotADam:
    def test_4_landslide_touching_a_river_with_no_obstruction_is_not_a_dam(
        self, cfg: Config
    ) -> None:
        """Required system test 4.

        The landslide reaches the channel, but the river runs exactly as
        before: no new water above, none lost below, no narrowing.
        """
        base = scene()
        candidates = run(cfg, landslide(touching=True), water_post=base["water_pre"])
        assert candidates == []

    def test_a_landslide_nowhere_near_the_channel_is_ignored(
        self, cfg: Config
    ) -> None:
        base = scene()
        candidates = run(
            cfg,
            landslide(touching=False, far_cols=10),
            water_post=dammed_water(base["water_pre"]),
        )
        assert candidates == []

    def test_no_landslides_gives_no_candidates(self, cfg: Config) -> None:
        base = scene()
        candidates = run(
            cfg,
            np.zeros((SIZE, SIZE), dtype=bool),
            water_post=dammed_water(base["water_pre"]),
        )
        assert candidates == []

    def test_min_evidence_types_cannot_be_zero(self, cfg: Config) -> None:
        """The conjunction is not negotiable through configuration."""
        with pytest.raises(ValueError):
            replace_blockage_config(cfg, min_evidence_types=0)

    def test_without_water_masks_no_candidate_is_produced(
        self, cfg: Config
    ) -> None:
        """No obstruction evidence can be measured, so there is no candidate."""
        candidates = run(cfg, landslide(touching=True), water_post=None)
        assert candidates == []


# --------------------------------------------------------------------------- #
# Required system test 5 -- obstruction evidence present
# --------------------------------------------------------------------------- #


class TestObstructionEvidence:
    def test_5_landslide_crossing_a_river_with_obstruction_is_a_candidate(
        self, cfg: Config
    ) -> None:
        """Required system test 5."""
        base = scene()
        candidates = run(
            cfg, landslide(touching=True), water_post=dammed_water(base["water_pre"])
        )
        assert len(candidates) == 1
        candidate = candidates[0]
        assert candidate.site_type == "Potential Landslide Dam"
        assert candidate.evidence_count >= 1
        assert candidate.confidence > 0.0

    def test_new_upstream_water_is_detected(self, cfg: Config) -> None:
        base = scene()
        candidate = run(
            cfg, landslide(touching=True), water_post=dammed_water(base["water_pre"])
        )[0]
        upstream = next(
            f for f in candidate.factors if f.name == "new_upstream_water"
        )
        assert upstream.present
        assert upstream.value > 0

    def test_downstream_water_loss_is_detected(self, cfg: Config) -> None:
        base = scene()
        candidate = run(
            cfg, landslide(touching=True), water_post=dammed_water(base["water_pre"])
        )[0]
        downstream = next(
            f for f in candidate.factors if f.name == "downstream_water_loss"
        )
        assert downstream.present
        assert downstream.value > 0

    def test_channel_narrowing_is_detected(self, cfg: Config) -> None:
        base = scene()
        candidate = run(
            cfg, landslide(touching=True), water_post=dammed_water(base["water_pre"])
        )[0]
        narrowing = next(
            f for f in candidate.factors if f.name == "channel_narrowing"
        )
        assert narrowing.present

    def test_more_evidence_gives_higher_confidence(self, cfg: Config) -> None:
        base = scene()
        full = run(
            cfg, landslide(touching=True), water_post=dammed_water(base["water_pre"])
        )[0]

        # Only the channel buried: narrowing, but nothing pooling upstream.
        partial_water = base["water_pre"].copy()
        partial_water[BLOCK_ROW : BLOCK_ROW + 5, :] = False
        partial = run(cfg, landslide(touching=True), water_post=partial_water)
        assert partial, "narrowing alone should still be a candidate"
        assert full.confidence > partial[0].confidence

    def test_upstream_direction_comes_from_flow_accumulation(
        self, cfg: Config
    ) -> None:
        """Reverse the accumulation and the directional signals swap."""
        base = scene()
        water_post = dammed_water(base["water_pre"])
        reversed_accumulation = base["flow_accumulation"][::-1, :].copy()

        normal = run(cfg, landslide(touching=True), water_post=water_post)[0]
        flipped = run(
            cfg,
            landslide(touching=True),
            water_post=water_post,
            flow_accumulation=reversed_accumulation,
        )
        upstream_normal = next(
            f for f in normal.factors if f.name == "new_upstream_water"
        ).present
        assert upstream_normal
        if flipped:
            upstream_flipped = next(
                f for f in flipped[0].factors if f.name == "new_upstream_water"
            ).present
            assert not upstream_flipped

    def test_without_flow_accumulation_direction_is_absent_not_guessed(
        self, cfg: Config
    ) -> None:
        base = scene()
        candidates = run(
            cfg,
            landslide(touching=True),
            water_post=dammed_water(base["water_pre"]),
            flow_accumulation=None,
        )
        # Narrowing alone still qualifies under the default min_evidence_types.
        assert len(candidates) == 1
        for name in ("new_upstream_water", "downstream_water_loss"):
            factor = next(f for f in candidates[0].factors if f.name == name)
            assert not factor.present
            assert "upstream cannot be told" in factor.reason


# --------------------------------------------------------------------------- #
# Reporting
# --------------------------------------------------------------------------- #


class TestReporting:
    def candidate(self, cfg: Config):
        base = scene()
        return run(
            cfg, landslide(touching=True), water_post=dammed_water(base["water_pre"])
        )[0]

    def test_dam_code_follows_the_brief_s_format(self, cfg: Config) -> None:
        assert self.candidate(cfg).dam_code == "ND-001"

    def test_code_prefix_is_configurable(self, cfg: Config) -> None:
        tuned = replace_blockage_config(cfg, code_prefix="DAM")
        base = scene()
        candidate = run(
            tuned, landslide(touching=True), water_post=dammed_water(base["water_pre"])
        )[0]
        assert candidate.dam_code.startswith("DAM-")

    def test_the_type_never_asserts_a_dam_has_formed(self, cfg: Config) -> None:
        """The system reports potential, never fact."""
        assert "Potential" in self.candidate(cfg).site_type

    def test_every_candidate_lists_its_factors(self, cfg: Config) -> None:
        candidate = self.candidate(cfg)
        described = candidate.describe()
        for factor in candidate.factors:
            assert factor.name in described
        assert set(OBSTRUCTION_SIGNALS) <= {f.name for f in candidate.factors}

    def test_proximity_is_labelled_a_precondition_not_evidence(
        self, cfg: Config
    ) -> None:
        proximity = next(
            f for f in self.candidate(cfg).factors if f.name == "intersects_stream"
        )
        assert "not evidence of obstruction" in proximity.reason
        assert proximity.name not in OBSTRUCTION_SIGNALS

    def test_confidence_cannot_reach_one_on_proximity_alone(
        self, cfg: Config
    ) -> None:
        """Normalisation is over the total weight, proximity included."""
        weights = cfg.detection.blockage.weights
        assert weights.intersects_stream / weights.total() < 0.3

    def test_evidence_dates_are_carried(self, cfg: Config) -> None:
        candidate = self.candidate(cfg)
        assert candidate.pre_date == "2023-09-01"
        assert candidate.post_date == "2023-10-19"

    def test_geographic_centroid_is_derived(self, cfg: Config) -> None:
        candidate = self.candidate(cfg)
        assert 80.0 < candidate.centroid_lon < 90.0
        assert 25.0 < candidate.centroid_lat < 32.0

    def test_candidates_convert_to_a_frame(self, cfg: Config) -> None:
        base = scene()
        candidates = run(
            cfg, landslide(touching=True), water_post=dammed_water(base["water_pre"])
        )
        frame = candidates_to_frame(candidates, UTM45N)
        assert len(frame) == 1
        assert frame["dam_code"].iloc[0] == "ND-001"

    def test_an_empty_frame_keeps_its_columns(self, cfg: Config) -> None:
        frame = candidates_to_frame([], UTM45N)
        assert len(frame) == 0
        assert "dam_code" in frame.columns

    def test_a_geographic_crs_is_refused_for_the_frame(self, cfg: Config) -> None:
        with pytest.raises(ValueError, match="requires a projected CRS"):
            candidates_to_frame([], "EPSG:4326")

    def test_mismatched_grids_are_refused(self, cfg: Config) -> None:
        with pytest.raises(ValueError, match="different grids"):
            detect_blockages(
                cfg,
                landslides=np.zeros((10, 10), dtype=bool),
                streams=np.zeros((12, 12), dtype=bool),
                cellsize_m=CELLSIZE,
                pixel_area_m2=PIXEL_AREA,
            )

    def test_confidence_feeds_the_risk_assessment(self, cfg: Config) -> None:
        """Phase 11's blockage_confidence factor is unavailable until now."""
        from analysis.risk import assess_risk

        candidate = self.candidate(cfg)
        assessment = assess_risk(
            cfg, slope_deg=40.0, blockage_confidence=candidate.confidence
        )
        factor = next(
            f for f in assessment.factors if f.name == "blockage_confidence"
        )
        assert factor.available
        assert factor.value == pytest.approx(candidate.confidence)


# --------------------------------------------------------------------------- #
# Minimum landslide area -- the gate that the Baige 2018 run forced
# --------------------------------------------------------------------------- #
class TestMinimumLandslideArea:
    """A fragment too small to dam a river must not become a candidate.

    Phase 5 applies a 1000 m^2 floor to its own polygons, but Phase 7 consumes
    the raw change mask, so without this gate single pixels became candidates.
    On the real Baige 2018 event that produced 153 candidates for one dam, 76
    of them a single 10 m pixel, 18 at confidence 1.000 -- because the
    obstruction evidence is measured over a 500 m reach and a one-pixel
    fragment beside a blocked river inherits all of it.
    """

    def _speck(self, row: int = BLOCK_ROW, col: int = CHANNEL_COL + 1):
        """One pixel sitting directly on the channel."""
        mask = np.zeros((SIZE, SIZE), dtype=bool)
        mask[row, col] = True
        return mask

    def test_a_single_pixel_is_rejected_by_default(self, cfg: Config):
        """The default floor is Phase 5's, so one pixel cannot be a dam."""
        base = scene()
        candidates = run(
            cfg, self._speck(), water_post=dammed_water(base["water_pre"])
        )
        assert candidates == []

    def test_the_same_pixel_would_otherwise_score_full_confidence(
        self, cfg: Config
    ):
        """Proof the rejection is the area gate, not weak evidence.

        With the floor dropped to zero the identical pixel is accepted and
        scores highly -- which is precisely the failure mode observed on real
        data, and why the floor is needed rather than merely tidy.
        """
        tuned = replace_blockage_config(cfg, min_landslide_area_m2=0.0)
        base = scene()
        candidates = run(
            tuned, self._speck(), water_post=dammed_water(base["water_pre"])
        )
        assert len(candidates) == 1
        assert candidates[0].confidence > 0.5
        assert candidates[0].landslide_area_m2 == pytest.approx(PIXEL_AREA)

    def test_a_real_deposit_survives_the_default_floor(self, cfg: Config):
        """The gate must not cost the genuine detection."""
        base = scene()
        candidates = run(
            cfg, landslide(), water_post=dammed_water(base["water_pre"])
        )
        assert candidates, "the floor removed a deposit large enough to dam"
        assert candidates[0].landslide_area_m2 >= (
            cfg.detection.blockage.min_landslide_area_m2
        )

    def test_the_floor_is_read_from_config(self, cfg: Config):
        """Raising it above the deposit's size rejects the deposit."""
        base = scene()
        deposit = landslide()
        area = float(deposit.sum()) * PIXEL_AREA
        tuned = replace_blockage_config(
            cfg, min_landslide_area_m2=area + PIXEL_AREA
        )
        assert run(tuned, deposit, water_post=dammed_water(base["water_pre"])) == []


# --------------------------------------------------------------------------- #
# One dam, one candidate -- merging along the channel
# --------------------------------------------------------------------------- #
class TestMergingAlongTheStream:
    """Fragments of one deposit must not become several dams.

    Phase 5's slope gate carves the channel-crossing part out of a deposit
    lying on a flat valley floor, and cloud and snow fragment it further. Each
    fragment then became its own candidate -- and because the obstruction
    evidence is measured over a REACH, every fragment saw the same impounded
    water and reported it as independent confirmation.

    Measured on Baige 2018: the four top-ranked candidates claimed
    136,500-154,800 m2 of gained water upstream, which was the same water
    counted four times, so choosing "the candidate with the most impounded
    water" chose an arbitrary fragment. Merging took 32 candidates to 2 and
    put the survivor on the main stem.
    """

    def _split_deposit(self):
        """One deposit cut in two by a gap across the channel.

        This is the shape the slope gate produces: material either side of the
        river, with the channel-crossing middle removed.
        """
        mask = np.zeros((SIZE, SIZE), dtype=bool)
        mask[BLOCK_ROW : BLOCK_ROW + 4, CHANNEL_COL - 9 : CHANNEL_COL - 2] = True
        mask[BLOCK_ROW : BLOCK_ROW + 4, CHANNEL_COL + 3 : CHANNEL_COL + 10] = True
        return mask

    def test_two_fragments_of_one_deposit_give_one_candidate(
        self, cfg: Config
    ) -> None:
        base = scene()
        candidates = run(
            cfg, self._split_deposit(),
            water_post=dammed_water(base["water_pre"]),
        )
        assert len(candidates) == 1, (
            f"one split deposit produced {len(candidates)} candidates"
        )

    def test_the_split_deposit_really_is_two_components(self) -> None:
        """Precondition: without grouping these are two separate objects.

        Checked directly, because a test asserting "one candidate" proves
        nothing if the fixture was one component all along.
        """
        from detection.blockage import _components

        assert len(_components(self._split_deposit())) == 2

    def test_zero_distance_still_groups_a_split_deposit(
        self, cfg: Config
    ) -> None:
        """Zero is not "off", and should not be.

        Both halves of a deposit cut by the channel reach the SAME stream
        pixels, so they obstruct the same cross-section. That makes them one
        blockage at any along-channel distance, including none.
        """
        zero = replace_blockage_config(cfg, merge_along_stream_m=0.0)
        base = scene()
        candidates = run(
            zero, self._split_deposit(),
            water_post=dammed_water(base["water_pre"]),
        )
        assert len(candidates) == 1

    def test_the_merged_candidate_carries_the_whole_deposit(
        self, cfg: Config
    ) -> None:
        """Area must be the union, or the risk score under-reads the dam."""
        deposit = self._split_deposit()
        base = scene()
        candidates = run(
            cfg, deposit, water_post=dammed_water(base["water_pre"])
        )
        assert candidates[0].landslide_area_m2 == pytest.approx(
            float(deposit.sum()) * PIXEL_AREA
        )

    def test_deposits_far_apart_along_the_channel_need_the_distance(
        self, cfg: Config
    ) -> None:
        """Along-channel separation is what the setting actually governs.

        Two deposits 20 px apart on the channel reach different cross-sections,
        so grouping them depends on `merge_along_stream_m`.
        """
        far = np.zeros((SIZE, SIZE), dtype=bool)
        far[10:14, CHANNEL_COL - 3 : CHANNEL_COL + 4] = True
        far[30:34, CHANNEL_COL - 3 : CHANNEL_COL + 4] = True
        base = scene()
        water_post = dammed_water(base["water_pre"])

        tight = run(
            replace_blockage_config(cfg, merge_along_stream_m=20.0),
            far, water_post=water_post,
        )
        wide = run(
            replace_blockage_config(cfg, merge_along_stream_m=400.0),
            far, water_post=water_post,
        )
        assert len(tight) == 2, "20 m must not bridge a 200 m separation"
        assert len(wide) == 1, "400 m must bridge a 200 m separation"

    def test_separate_tributaries_do_not_merge(self, cfg: Config) -> None:
        """Distance is along the network, so unconnected channels stay apart.

        Two deposits the same straight-line distance apart as a split deposit,
        but on streams that do not meet inside the search window, are two
        blockages.
        """
        streams = np.zeros((SIZE, SIZE), dtype=bool)
        left, right = 12, 46
        streams[:, left] = True
        streams[:, right] = True
        accumulation = np.tile(
            (np.arange(SIZE, dtype=float) + 1.0) * 100.0, (SIZE, 1)
        ).T
        water = np.zeros((SIZE, SIZE), dtype=bool)
        water[:, left - 1 : left + 2] = True
        water[:, right - 1 : right + 2] = True

        deposits = np.zeros((SIZE, SIZE), dtype=bool)
        deposits[BLOCK_ROW : BLOCK_ROW + 4, left - 3 : left + 4] = True
        deposits[BLOCK_ROW : BLOCK_ROW + 4, right - 3 : right + 4] = True

        after = water.copy()
        for col in (left, right):
            after[BLOCK_ROW - 20 : BLOCK_ROW - 6, col - 5 : col + 6] = True
            after[BLOCK_ROW + 5 : BLOCK_ROW + 25, col - 2 : col + 3] = False
            after[BLOCK_ROW : BLOCK_ROW + 5, col - 2 : col + 3] = False

        candidates = run(
            cfg, deposits, water_post=after,
            streams=streams, flow_accumulation=accumulation, water_pre=water,
        )
        assert len(candidates) == 2, (
            "deposits on two unconnected streams were merged into one dam"
        )

    def test_the_default_merges_the_real_baige_fragments(
        self, cfg: Config
    ) -> None:
        """The shipped default must group fragments at the scale observed.

        On Baige the fragments of one deposit lay within a few hundred metres
        along the channel, and the default is tied to evidence_search_m for
        the reason in the config comment.
        """
        assert (
            cfg.detection.blockage.merge_along_stream_m
            == cfg.detection.blockage.evidence_search_m
        )
