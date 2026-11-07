"""The whole chain, on one synthetic landslide-dam event.

Every other test file exercises a module in isolation. This one wires them
together in the order a real run would:

    landslide change -> blockage -> barrier lake -> tracking
                     -> trend -> depth/volume -> risk -> storage

Its purpose is to catch the errors that live in the *interfaces* between
phases rather than inside them -- the kind that pass every unit test and still
produce nonsense end to end.

The scene is SYNTHETIC (brief, Section 2): a V-shaped valley built from an
analytic surface, with a landslide stamped across the channel and water
impounded behind it. Nothing here is satellite imagery, and the geometry is
chosen so the expected answers are known.
"""

from __future__ import annotations

from datetime import date, timedelta

import numpy as np
import pytest
from affine import Affine

from analysis.change import AreaObservation, analyse_trend
from analysis.depth_volume import BRANCH_A, estimate_depth_volume
from analysis.risk import assess_risk
from config.schema import Config
from database.db import Database
from detection.barrier_lake import LakeTracker, find_barrier_lakes
from detection.blockage import detect_blockages
from detection.landslide_change import detect_change, landslide_polygons

pytestmark = pytest.mark.synthetic

SIZE = 90
CELLSIZE = 10.0
PIXEL_AREA = CELLSIZE * CELLSIZE
CHANNEL_COL = 45
BLOCK_ROW = 50
UTM45N = "EPSG:32645"
TRANSFORM = Affine(CELLSIZE, 0.0, 450000.0, 0.0, -CELLSIZE, 3085000.0)

DEM_EPOCH_END = date(2014, 9, 8)
PRE_DATE = date(2023, 9, 1)
POST_DATE = date(2023, 10, 19)


# --------------------------------------------------------------------------- #
# The synthetic valley
# --------------------------------------------------------------------------- #


def valley_dem() -> np.ndarray:
    """A V-shaped valley falling from row 0 to row 89.

    ``elevation = 4600 - 0.8*row + 1.5*|col - channel|``: the floor drops
    0.8 m per 10 m downstream and the walls rise 1.5 m per 10 m outward, so
    the cross-section is a genuine V with a measurable capacity.
    """
    rows = np.arange(SIZE, dtype=float)[:, None]
    cols = np.arange(SIZE, dtype=float)[None, :]
    return 4600.0 - 0.8 * rows + 1.5 * np.abs(cols - CHANNEL_COL)


def terrain():
    dem = valley_dem()
    streams = np.zeros((SIZE, SIZE), dtype=bool)
    streams[:, CHANNEL_COL] = True
    # Accumulation rises downstream, which is what tells upstream from down.
    accumulation = np.tile((np.arange(SIZE, dtype=float) + 1.0) * 50.0, (SIZE, 1)).T
    # Valley walls are steep; the floor is not.
    slope = np.full((SIZE, SIZE), 34.0)
    slope[:, CHANNEL_COL - 1 : CHANNEL_COL + 2] = 2.0
    return dem, streams, accumulation, slope


def river() -> np.ndarray:
    """The pre-event channel: three pixels wide, running the whole valley."""
    water = np.zeros((SIZE, SIZE), dtype=bool)
    water[:, CHANNEL_COL - 1 : CHANNEL_COL + 2] = True
    return water


def landslide_mask() -> np.ndarray:
    """Debris crossing the channel at BLOCK_ROW, from the eastern wall."""
    mask = np.zeros((SIZE, SIZE), dtype=bool)
    mask[BLOCK_ROW : BLOCK_ROW + 5, CHANNEL_COL - 4 : CHANNEL_COL + 14] = True
    return mask


def impounded(dem: np.ndarray, level_m: float) -> np.ndarray:
    """Water filling the valley behind the blockage up to ``level_m``.

    Only upstream of the dam, and only where the terrain is below the level --
    which is what gives the depth/volume branch something real to measure.
    """
    lake = np.zeros((SIZE, SIZE), dtype=bool)
    upstream = np.zeros((SIZE, SIZE), dtype=bool)
    upstream[:BLOCK_ROW, :] = True
    lake[(dem <= level_m) & upstream] = True
    return lake


def post_event_water(dem: np.ndarray, level_m: float) -> np.ndarray:
    """After the blockage: a lake above, a dry channel below."""
    water = river().copy()
    water[BLOCK_ROW : BLOCK_ROW + 5, :] = False          # channel buried
    water[BLOCK_ROW + 5 : BLOCK_ROW + 30, :] = False     # downstream runs dry
    return water | impounded(dem, level_m)


@pytest.fixture(scope="module")
def scene():
    dem, streams, accumulation, slope = terrain()
    return {
        "dem": dem,
        "streams": streams,
        "accumulation": accumulation,
        "slope": slope,
        "water_pre": river(),
        "water_post": post_event_water(dem, 4578.0),
        "landslide": landslide_mask(),
    }


# --------------------------------------------------------------------------- #
# The chain
# --------------------------------------------------------------------------- #


@pytest.fixture(scope="module")
def dam_cfg(cfg: Config) -> Config:
    """Config tuned for landslide DAMS, not shallow-landslide source areas.

    Phase 5's slope gate comes from Notti et al. (2023), who map shallow
    landslide *source* areas -- which are steep by definition, hence
    "slope > 15 deg". A landslide **deposit** that blocks a river lies on the
    valley floor, which is flat by definition. Left at 15 deg the gate carves
    the channel-crossing part out of the debris, splitting one landslide into
    two components either side of the river and producing two duplicate dam
    candidates for a single event.

    So the gate is relaxed here. Recorded in docs/methods.md 5.9: the cited
    default is right for the paper's purpose and wrong for this one.
    """
    data = cfg.model_dump(mode="python")
    data["detection"]["landslide_change"]["gating"]["min_slope_deg"] = 1.0
    data["detection"]["landslide_change"]["gating"]["min_median_slope_deg"] = 1.0
    return Config.model_validate(data)


@pytest.fixture(scope="module")
def pipeline(scene, dam_cfg: Config):
    """Run every phase in order and return what each produced."""
    cfg = dam_cfg
    dem = scene["dem"]
    slope = scene["slope"]
    landslide = scene["landslide"]

    # --- Phase 5: bi-temporal change ----------------------------------------
    # Noise is deliberate. The default brightness and SAR thresholds are
    # derived from the scene's own spread, so a noiseless scene has no scale
    # and those signals are reported unavailable. Real imagery is never
    # noiseless, and a test scene that is would exercise the wrong path.
    rng = np.random.default_rng(20231019)
    ndvi_pre = 0.62 + rng.normal(0.0, 0.02, (SIZE, SIZE))
    ndvi_post = ndvi_pre + rng.normal(0.0, 0.02, (SIZE, SIZE))
    ndvi_post[landslide] = 0.05            # vegetation stripped
    brightness_pre = 0.16 + rng.normal(0.0, 0.01, (SIZE, SIZE))
    brightness_post = brightness_pre + rng.normal(0.0, 0.01, (SIZE, SIZE))
    brightness_post[landslide] = 0.38      # fresh bare debris
    sar_pre = -9.0 + rng.normal(0.0, 0.4, (SIZE, SIZE))
    sar_post = sar_pre + rng.normal(0.0, 0.4, (SIZE, SIZE))
    sar_post[landslide] = -3.5             # roughened surface

    change = detect_change(
        cfg,
        ndvi_pre=ndvi_pre,
        ndvi_post=ndvi_post,
        brightness_pre=brightness_pre,
        brightness_post=brightness_post,
        sar_db_pre=sar_pre,
        sar_db_post=sar_post,
        slope_deg=slope,
    )
    polygons = landslide_polygons(change, TRANSFORM, UTM45N, cfg, slope_deg=slope)

    # --- Phase 7: blockage ---------------------------------------------------
    blockages = detect_blockages(
        cfg,
        landslides=change.change,
        streams=scene["streams"],
        flow_accumulation=scene["accumulation"],
        water_pre=scene["water_pre"],
        water_post=scene["water_post"],
        cellsize_m=CELLSIZE,
        pixel_area_m2=PIXEL_AREA,
        transform=TRANSFORM,
        crs=UTM45N,
        pre_date=str(PRE_DATE),
        post_date=str(POST_DATE),
    )

    # --- Phase 8: barrier lake ----------------------------------------------
    lakes = []
    if blockages:
        lakes = find_barrier_lakes(
            cfg,
            blockage_site=blockages[0].site_mask,
            streams=scene["streams"],
            water_post=scene["water_post"],
            water_pre=scene["water_pre"],
            flow_accumulation=scene["accumulation"],
            cellsize_m=CELLSIZE,
            pixel_area_m2=PIXEL_AREA,
            dam_code=blockages[0].dam_code,
        )

    # --- Phase 8 tracking + Phase 9 trend: the lake filling over four dates --
    tracker = LakeTracker(cfg, pixel_area_m2=PIXEL_AREA)
    observations: list[AreaObservation] = []
    # Channel elevation upstream of the dam runs 4560.8 m (row 49) to 4600 m
    # (row 0), so these levels impound a lake that visibly grows.
    for step, level in enumerate((4566.0, 4570.0, 4574.0, 4578.0)):
        obs_date = POST_DATE + timedelta(days=step * 10)
        mask = impounded(dem, level)
        tracker.update(
            obs_date,
            lakes=[mask],
            observable=np.ones((SIZE, SIZE), dtype=bool),
            upstream_of=blockages[0].dam_code if blockages else None,
        )
        observations.append(
            AreaObservation(
                obs_date=obs_date,
                area_m2=float(np.count_nonzero(mask) * PIXEL_AREA),
                sensor="Sentinel-2",
            )
        )
    trend = analyse_trend(cfg, observations, reference_date=observations[-1].obs_date)

    # --- Phase 10: depth and volume -----------------------------------------
    final_lake = impounded(dem, 4578.0)
    depth = estimate_depth_volume(
        cfg,
        final_lake,
        dem,
        cellsize_m=CELLSIZE,
        pixel_area_m2=PIXEL_AREA,
        dem_epoch_end=DEM_EPOCH_END,
        lake_first_observed=POST_DATE,
    )

    # --- Phase 11: risk ------------------------------------------------------
    assessment = assess_risk(
        cfg,
        lake_growth_rate_m2_per_day=trend.rate_m2_per_day,
        lake_volume_m3=depth.volume_m3,
        volume_unavailable_reason=None if depth.available else depth.reason,
        new_landslide_area_m2=(
            float(polygons["area_m2"].sum()) if len(polygons) else None
        ),
        blockage_confidence=blockages[0].confidence if blockages else None,
        slope_deg=float(np.median(slope[landslide])),
    )

    return {
        "change": change,
        "polygons": polygons,
        "blockages": blockages,
        "lakes": lakes,
        "tracker": tracker,
        "trend": trend,
        "depth": depth,
        "assessment": assessment,
    }


# --------------------------------------------------------------------------- #
# Each link in the chain
# --------------------------------------------------------------------------- #


class TestChain:
    def test_the_landslide_is_detected_as_change(self, pipeline) -> None:
        change = pipeline["change"]
        assert change.changed_pixels > 0
        assert len(pipeline["polygons"]) == 1
        assert pipeline["polygons"]["area_m2"].iloc[0] > 0

    def test_the_blockage_is_found_with_obstruction_evidence(self, pipeline) -> None:
        blockages = pipeline["blockages"]
        assert len(blockages) == 1
        candidate = blockages[0]
        assert candidate.dam_code == "ND-001"
        assert candidate.site_type == "Potential Landslide Dam"
        assert candidate.evidence_count >= 1, "proximity alone must not suffice"

    def test_the_candidate_carries_what_phase_8_needs(self, pipeline) -> None:
        """The interface that was missing until this test was written."""
        candidate = pipeline["blockages"][0]
        assert candidate.site_mask is not None
        assert candidate.site_mask.any()
        assert candidate.landslide_mask is not None

    def test_the_barrier_lake_is_found_upstream(self, pipeline) -> None:
        lakes = pipeline["lakes"]
        assert len(lakes) >= 1
        lake = lakes[0]
        assert lake.upstream_of == "ND-001"
        assert lake.qualifies_as in {"new", "expanding"}
        assert lake.new_area_m2 > 0

    def test_the_lake_is_tracked_with_one_stable_id(self, pipeline) -> None:
        tracker = pipeline["tracker"]
        assert len(tracker.lakes) == 1, "a filling lake must not fragment its identity"
        lake = next(iter(tracker.lakes.values()))
        assert lake.lake_id == "BL-001"
        assert len(lake.observations) == 4
        assert lake.upstream_of == "ND-001"

    def test_the_filling_lake_trends_increasing(self, pipeline) -> None:
        trend = pipeline["trend"]
        assert trend.trend == "Increasing"
        assert trend.rate_m2_per_day > 0
        assert trend.n_gaps == 0

    def test_depth_and_volume_take_branch_a(self, pipeline) -> None:
        """The first exercise of Branch A anywhere in the project.

        The lake postdates the DEM epoch and the DEM holds a real valley
        floor, so a volume is both permitted and meaningful.
        """
        depth = pipeline["depth"]
        assert depth.branch == BRANCH_A
        assert depth.value_type == "estimated"
        assert depth.volume_m3 > 0
        assert depth.mean_depth_m > 0
        assert depth.volume_low_m3 <= depth.volume_m3 <= depth.volume_high_m3

    def test_the_volume_is_physically_plausible_for_this_valley(
        self, pipeline, scene
    ) -> None:
        """Checked against the analytic capacity of the V, not against itself."""
        depth = pipeline["depth"]
        dem = scene["dem"]
        lake = impounded(dem, 4578.0)
        expected = float(np.clip(4578.0 - dem[lake], 0.0, None).sum() * PIXEL_AREA)
        # The WSE is read from the shoreline, which sits slightly above the
        # fill level, so the estimate should exceed the exact figure a little.
        assert depth.volume_m3 == pytest.approx(expected, rel=0.5)
        assert depth.volume_m3 > expected

    def test_the_risk_assessment_uses_every_upstream_phase(self, pipeline) -> None:
        """The point of the whole chain: five factors, all now measurable."""
        assessment = pipeline["assessment"]
        available = {f.name for f in assessment.factors if f.available}
        assert available >= {
            "lake_growth_rate",
            "lake_volume",
            "new_landslide_activity",
            "blockage_confidence",
            "slope",
        }
        assert not assessment.insufficient_data
        assert assessment.data_coverage == pytest.approx(1.0)

    def test_the_warning_is_complete_and_disclaimed(self, pipeline, cfg: Config) -> None:
        text = pipeline["assessment"].warning_text()
        assert "Not an official warning" in text
        assert "Contributing factors:" in text
        for name in ("lake_growth_rate", "blockage_confidence"):
            assert name in text


# --------------------------------------------------------------------------- #
# Storage
# --------------------------------------------------------------------------- #


class TestPersistence:
    def test_the_whole_result_stores_and_reads_back(self, pipeline, cfg: Config) -> None:
        candidate = pipeline["blockages"][0]
        depth = pipeline["depth"]
        assessment = pipeline["assessment"]
        lake = next(iter(pipeline["tracker"].lakes.values()))

        with Database(":memory:") as db:
            db.initialise()
            run = db.start_run(config_hash="e2e", aoi="synthetic valley")

            site_id = db.upsert_site(
                site_code=candidate.dam_code,
                site_type=candidate.site_type,
                lat=candidate.centroid_lat,
                lon=candidate.centroid_lon,
                first_detected=str(POST_DATE),
                confidence=candidate.confidence,
                status="candidate",
            )
            db.add_landslide_event(
                site_id=site_id,
                pre_date=str(PRE_DATE),
                post_date=str(POST_DATE),
                area_m2=float(pipeline["polygons"]["area_m2"].iloc[0]),
                confidence=candidate.confidence,
                method="bi-temporal change, 2 of 3 signals",
                run_id=run.id,
            )
            for obs_date, area in lake.area_series():
                if area is None:
                    continue
                db.add_observation(
                    site_id,
                    obs_date=str(obs_date),
                    sensor="Sentinel-2",
                    value_type="derived",
                    water_area_m2=area,
                    run_id=run.id,
                )
            db.add_depth_volume(
                depth.as_record(site_id, str(POST_DATE)), run_id=run.id
            )
            db.add_risk_assessment(assessment.as_record(site_id), run_id=run.id)
            db.finish_run(run.id)

            counts = db.counts()
            assert counts["sites"] == 1
            assert counts["landslide_events"] == 1
            assert counts["observations"] == 4
            assert counts["depth_volume_estimates"] == 1
            assert counts["risk_assessments"] == 1

            stored_depth = db.depth_volume_estimates(site_id)[0]
            assert stored_depth["branch"] == BRANCH_A
            assert stored_depth["volume_m3"] > 0

            stored_risk = db.latest_risk_assessment(site_id)
            assert stored_risk["level"] == assessment.level
            assert stored_risk["insufficient_data"] == 0

            areas = [row["water_area_m2"] for row in db.observations(site_id)]
            assert areas == sorted(areas), "the lake series must read back in order"

    def test_a_branch_b_lake_still_cannot_store_a_volume(
        self, pipeline, scene, cfg: Config
    ) -> None:
        """The chain must not find a way around Section 8.

        The same lake, but with the DEM flattened over it as GLO-30 would do:
        Branch B, and the database refuses a volume however it is passed.
        """
        import sqlite3

        dem = scene["dem"].copy()
        lake = impounded(scene["dem"], 4578.0)
        dem[lake] = 4578.0  # the DEM recorded the water surface

        estimate = estimate_depth_volume(
            cfg,
            lake,
            dem,
            cellsize_m=CELLSIZE,
            pixel_area_m2=PIXEL_AREA,
            dem_epoch_end=DEM_EPOCH_END,
            lake_first_observed=POST_DATE,
        )
        assert estimate.branch == "B"
        assert estimate.volume_m3 is None

        with Database(":memory:") as db:
            db.initialise()
            site_id = db.upsert_site(site_code="ND-002", site_type="Potential Landslide Dam")
            record = estimate.as_record(site_id, str(POST_DATE))
            record["volume_m3"] = 9_000_000.0  # a caller inventing a number
            with pytest.raises(sqlite3.IntegrityError):
                db.add_depth_volume(record)


# --------------------------------------------------------------------------- #
# The chain must stay honest when the data thins out
# --------------------------------------------------------------------------- #


class TestDegradation:
    def test_an_unobserved_lake_does_not_become_a_breach(
        self, scene, cfg: Config
    ) -> None:
        """Cloud across the whole chain must not manufacture an alarm."""
        dem = scene["dem"]
        tracker = LakeTracker(cfg, pixel_area_m2=PIXEL_AREA)
        lake = impounded(dem, 4578.0)
        tracker.update(POST_DATE, lakes=[lake], observable=np.ones((SIZE, SIZE), bool))

        clouded = np.ones((SIZE, SIZE), dtype=bool)
        clouded[lake] = False
        events = tracker.update(
            POST_DATE + timedelta(days=10), lakes=[], observable=clouded
        )
        assert [e.kind for e in events] == ["not_observed"]

        tracked = next(iter(tracker.lakes.values()))
        series = [
            AreaObservation(obs_date=d, area_m2=a)
            if a is not None
            else AreaObservation.gap(d, "lake footprint not observable")
            for d, a in tracked.area_series()
        ]
        trend = analyse_trend(cfg, series, reference_date=series[-1].obs_date)
        assert trend.trend == "Unknown"
        assert trend.n_gaps == 1

    def test_no_blockage_means_no_barrier_lake_hunt(self, scene, dam_cfg: Config) -> None:
        """With the river unchanged there is no dam, and so nothing upstream."""
        blockages = detect_blockages(
            dam_cfg,
            landslides=scene["landslide"],
            streams=scene["streams"],
            flow_accumulation=scene["accumulation"],
            water_pre=scene["water_pre"],
            water_post=scene["water_pre"],  # the river flows as before
            cellsize_m=CELLSIZE,
            pixel_area_m2=PIXEL_AREA,
        )
        assert blockages == []

    def test_risk_degrades_gracefully_when_phases_produce_nothing(
        self, cfg: Config
    ) -> None:
        """Every upstream phase silent: a flagged, not a quiet, assessment."""
        assessment = assess_risk(cfg)
        assert assessment.insufficient_data
        assert assessment.data_coverage == 0.0
        assert "INSUFFICIENT DATA" in assessment.warning_text()
        assert "Not an official warning" in assessment.warning_text()
