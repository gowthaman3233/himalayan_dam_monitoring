"""Storage layer (brief, Section 10).

The emphasis is on what the database **refuses**: the Section 10 value-type
vocabulary, and Section 8's rule that an unavailable depth is not a number.
Those are enforced in SQL so a buggy caller cannot get round them.
"""

from __future__ import annotations

import json
import sqlite3
from pathlib import Path

import pytest

from analysis.risk import assess_risk
from config.schema import Config
from database.db import (
    BRANCHES,
    TABLES,
    VALUE_TYPES,
    Database,
    ValueTypeError,
    check_value_type,
    code_version,
    rows_to_dicts,
)

pytestmark = pytest.mark.synthetic


@pytest.fixture
def db() -> Database:
    """An initialised in-memory database."""
    database = Database(":memory:")
    database.initialise()
    yield database
    database.close()


@pytest.fixture
def site_id(db: Database) -> int:
    return db.upsert_site(
        site_code="ND-001",
        site_type="Potential Landslide Dam",
        geometry="POINT (448501.9 3081872.8)",
        lat=27.86062,
        lon=86.47691,
        elevation=4547.2,
        confidence=0.8,
        status="candidate",
    )


def depth_record(site_id: int, **overrides) -> dict:
    record = {
        "site_id": site_id,
        "obs_date": "2023-10-19",
        "branch": "B",
        "wse_m": 4554.69,
        "wse_uncertainty_m": 10.19,
        "mean_depth_m": None,
        "max_depth_m": None,
        "volume_m3": None,
        "volume_low_m3": None,
        "volume_high_m3": None,
        "value_type": "unavailable",
        "method": "brief Section 8 branch logic",
        "notes": "DEM records water surface; no bathymetry",
    }
    record.update(overrides)
    return record


# --------------------------------------------------------------------------- #
# Schema
# --------------------------------------------------------------------------- #


class TestSchema:
    def test_every_required_table_exists(self, db: Database) -> None:
        """The six tables the brief names as a minimum."""
        assert set(TABLES) <= set(db.table_names())

    def test_initialise_is_idempotent(self, db: Database) -> None:
        db.initialise()
        db.initialise()
        assert set(TABLES) <= set(db.table_names())

    def test_counts_start_empty(self, db: Database) -> None:
        assert db.counts() == {table: 0 for table in TABLES}

    def test_a_file_database_is_created_with_its_parent(self, tmp_path: Path) -> None:
        target = tmp_path / "nested" / "monitoring.sqlite"
        with Database(target) as database:
            database.initialise()
        assert target.exists()

    def test_foreign_keys_are_enforced(self, db: Database) -> None:
        """Off by default in SQLite, so a dangling site_id would slip through."""
        with pytest.raises(sqlite3.IntegrityError):
            db.add_observation(
                9999, obs_date="2023-10-19", sensor="S2", value_type="observed"
            )


# --------------------------------------------------------------------------- #
# The Section 10 vocabulary
# --------------------------------------------------------------------------- #


class TestValueTypeVocabulary:
    def test_the_vocabulary_is_exactly_the_brief_s(self) -> None:
        assert set(VALUE_TYPES) == {
            "observed",
            "classified",
            "estimated",
            "empirical",
            "derived",
            "unavailable",
        }

    def test_each_value_type_is_accepted(self, db: Database, site_id: int) -> None:
        for value_type in VALUE_TYPES:
            db.add_observation(
                site_id,
                obs_date="2023-10-19",
                sensor="S2",
                value_type=value_type,
            )
        assert db.counts()["observations"] == len(VALUE_TYPES)

    def test_an_unknown_value_type_is_refused_in_python(self) -> None:
        with pytest.raises(ValueTypeError, match="Section 10 value types"):
            check_value_type("probably_fine")

    def test_an_unknown_value_type_is_refused_by_the_database(
        self, db: Database, site_id: int
    ) -> None:
        """The SQL constraint is the guarantee, not the Python check."""
        connection = db.connect()
        with pytest.raises(sqlite3.IntegrityError):
            connection.execute(
                "INSERT INTO observations (site_id, obs_date, sensor, value_type)"
                " VALUES (?, ?, ?, ?)",
                (site_id, "2023-10-19", "S2", "guessed"),
            )

    def test_landslide_events_carry_a_value_type_too(
        self, db: Database, site_id: int
    ) -> None:
        db.add_landslide_event(
            site_id=site_id, pre_date="2023-09-01", post_date="2023-10-19"
        )
        event = db.landslide_events(site_id)[0]
        assert event["value_type"] == "classified"


# --------------------------------------------------------------------------- #
# Section 8 enforced in storage
# --------------------------------------------------------------------------- #


class TestDepthVolumeIntegrity:
    def test_a_branch_b_estimate_stores_without_numbers(
        self, db: Database, site_id: int
    ) -> None:
        db.add_depth_volume(depth_record(site_id))
        stored = db.depth_volume_estimates(site_id)[0]
        assert stored["branch"] == "B"
        assert stored["value_type"] == "unavailable"
        assert stored["volume_m3"] is None
        assert stored["mean_depth_m"] is None
        assert "no bathymetry" in stored["notes"]

    def test_an_unavailable_estimate_cannot_carry_a_volume(
        self, db: Database, site_id: int
    ) -> None:
        """The core Section 8 rule, enforced in SQL.

        This is the failure Phase 10 measured: the Branch A formula applied to
        a Branch B lake gives a plausible 14.3 million m3. The schema refuses
        to store it.
        """
        with pytest.raises(sqlite3.IntegrityError):
            db.add_depth_volume(
                depth_record(site_id, volume_m3=14_251_000.0)
            )

    def test_an_unavailable_estimate_cannot_carry_a_depth(
        self, db: Database, site_id: int
    ) -> None:
        with pytest.raises(sqlite3.IntegrityError):
            db.add_depth_volume(depth_record(site_id, mean_depth_m=9.19))

    def test_branch_b_cannot_be_marked_estimated(
        self, db: Database, site_id: int
    ) -> None:
        """Only Branch A may carry an estimated value."""
        with pytest.raises(sqlite3.IntegrityError):
            db.add_depth_volume(
                depth_record(site_id, branch="B", value_type="estimated")
            )

    def test_branch_c_cannot_be_marked_estimated(
        self, db: Database, site_id: int
    ) -> None:
        with pytest.raises(sqlite3.IntegrityError):
            db.add_depth_volume(
                depth_record(site_id, branch="C", value_type="estimated")
            )

    def test_branch_a_may_carry_an_estimate(self, db: Database, site_id: int) -> None:
        db.add_depth_volume(
            depth_record(
                site_id,
                branch="A",
                value_type="estimated",
                mean_depth_m=12.4,
                max_depth_m=31.0,
                volume_m3=9_900_000.0,
                volume_low_m3=7_100_000.0,
                volume_high_m3=13_400_000.0,
            )
        )
        stored = db.depth_volume_estimates(site_id)[0]
        assert stored["branch"] == "A"
        assert stored["volume_m3"] == pytest.approx(9_900_000.0)

    def test_an_unknown_branch_is_refused(self, db: Database, site_id: int) -> None:
        with pytest.raises(ValueError, match="branch must be one of"):
            db.add_depth_volume(depth_record(site_id, branch="D"))

    def test_branches_are_exactly_a_b_c(self) -> None:
        assert BRANCHES == ("A", "B", "C")


# --------------------------------------------------------------------------- #
# Round-trips from the analysis layer
# --------------------------------------------------------------------------- #


class TestAnalysisRoundTrip:
    def test_a_phase_10_estimate_stores_as_emitted(
        self, db: Database, site_id: int, cfg: Config
    ) -> None:
        """analysis.depth_volume and the schema share one record shape."""
        import numpy as np

        from analysis.depth_volume import estimate_depth_volume

        dem = np.full((20, 20), 100.0)
        dem[5:15, 5:15] = 95.0
        water = dem <= 95.0
        flat = dem.copy()
        flat[water] = 95.0  # the DEM recorded the water surface

        estimate = estimate_depth_volume(
            cfg, water, flat, cellsize_m=10.0, pixel_area_m2=100.0
        )
        row_id = db.add_depth_volume(estimate.as_record(site_id, "2023-10-19"))
        assert row_id > 0
        stored = db.depth_volume_estimates(site_id)[0]
        assert stored["branch"] == estimate.branch
        assert stored["volume_m3"] is None

    def test_a_phase_11_assessment_stores_as_emitted(
        self, db: Database, site_id: int, cfg: Config
    ) -> None:
        assessment = assess_risk(
            cfg,
            lake_growth_rate_m2_per_day=1400.0,
            blockage_confidence=0.82,
            slope_deg=41.0,
        )
        db.add_risk_assessment(assessment.as_record(site_id))
        stored = db.latest_risk_assessment(site_id)
        assert stored["level"] == assessment.level
        assert stored["score"] == pytest.approx(assessment.score)
        factors = json.loads(stored["factors_json"])
        assert len(factors) == 6
        assert any(not f["available"] for f in factors), "gaps are stored as gaps"

    def test_an_out_of_range_score_is_refused(
        self, db: Database, site_id: int
    ) -> None:
        with pytest.raises(sqlite3.IntegrityError):
            db.add_risk_assessment(
                {
                    "site_id": site_id,
                    "assessed_at": "2026-10-26T00:00:00Z",
                    "factors_json": "[]",
                    "score": 1.4,
                    "level": "NORMAL",
                    "config_version": "0.1.0",
                }
            )

    def test_latest_assessment_is_the_most_recent(
        self, db: Database, site_id: int
    ) -> None:
        base = {
            "site_id": site_id,
            "factors_json": "[]",
            "config_version": "0.1.0",
        }
        db.add_risk_assessment(
            {**base, "assessed_at": "2026-10-01T00:00:00Z", "score": 0.1,
             "level": "NORMAL"}
        )
        db.add_risk_assessment(
            {**base, "assessed_at": "2026-10-20T00:00:00Z", "score": 0.8,
             "level": "CRITICAL INDICATORS - verification recommended"}
        )
        assert db.latest_risk_assessment(site_id)["score"] == pytest.approx(0.8)


# --------------------------------------------------------------------------- #
# Sites, observations, runs
# --------------------------------------------------------------------------- #


class TestSites:
    def test_geometry_is_stored_as_wkt(self, db: Database, site_id: int) -> None:
        assert db.site("ND-001")["geometry"].startswith("POINT")

    def test_upsert_updates_rather_than_duplicating(self, db: Database) -> None:
        first = db.upsert_site(site_code="ND-002", site_type="Barrier Lake")
        second = db.upsert_site(
            site_code="ND-002", site_type="Barrier Lake", elevation=4600.0
        )
        assert first == second
        assert db.counts()["sites"] == 1
        assert db.site("ND-002")["elevation"] == pytest.approx(4600.0)

    def test_first_detected_survives_an_update(self, db: Database) -> None:
        """When a site was first seen is a fact about the site."""
        db.upsert_site(
            site_code="ND-003", site_type="Barrier Lake", first_detected="2023-10-19"
        )
        db.upsert_site(site_code="ND-003", site_type="Barrier Lake")
        assert db.site("ND-003")["first_detected"] == "2023-10-19"

    def test_an_impossible_confidence_is_refused(self, db: Database) -> None:
        with pytest.raises(sqlite3.IntegrityError):
            db.upsert_site(
                site_code="ND-004", site_type="Barrier Lake", confidence=1.5
            )


class TestObservations:
    def test_observations_come_back_in_date_order(
        self, db: Database, site_id: int
    ) -> None:
        for obs_date in ("2023-10-24", "2023-10-19", "2023-11-03"):
            db.add_observation(
                site_id,
                obs_date=obs_date,
                sensor="S2",
                value_type="derived",
                water_area_m2=1_600_000.0,
            )
        dates = [row["obs_date"] for row in db.observations(site_id)]
        assert dates == sorted(dates)

    def test_a_gap_is_simply_absent(self, db: Database, site_id: int) -> None:
        """Nothing interpolates: a missing date has no row."""
        db.add_observation(
            site_id, obs_date="2023-10-19", sensor="S2", value_type="derived"
        )
        db.add_observation(
            site_id, obs_date="2023-11-30", sensor="S2", value_type="derived"
        )
        rows = db.observations(site_id)
        assert len(rows) == 2
        assert [r["obs_date"] for r in rows] == ["2023-10-19", "2023-11-30"]

    def test_provenance_columns_are_stored(self, db: Database, site_id: int) -> None:
        """Section 5: sensor, date, orbit/tile and source collection."""
        db.add_observation(
            site_id,
            obs_date="2023-10-19",
            sensor="Sentinel-2",
            orbit_or_tile="45RVL",
            cloud_fraction=10.14,
            value_type="derived",
            method="both_and + snow screen",
            source_collection="COPERNICUS/S2_SR_HARMONIZED",
        )
        row = db.observations(site_id)[0]
        assert row["orbit_or_tile"] == "45RVL"
        assert row["source_collection"] == "COPERNICUS/S2_SR_HARMONIZED"


class TestRuns:
    def test_a_run_records_config_and_status(self, db: Database) -> None:
        run = db.start_run(config_hash="deadbeef" * 8, aoi="Tsho Rolpa")
        assert run.status == "running"
        db.finish_run(run.id)
        row = db.connect().execute(
            "SELECT * FROM runs WHERE id = ?", (run.id,)
        ).fetchone()
        assert row["status"] == "completed"
        assert row["finished_at"]

    def test_a_failed_run_is_recorded_as_failed(self, db: Database) -> None:
        run = db.start_run(config_hash="abc", aoi="Tsho Rolpa")
        db.finish_run(run.id, "failed")
        row = db.connect().execute(
            "SELECT status FROM runs WHERE id = ?", (run.id,)
        ).fetchone()
        assert row["status"] == "failed"

    def test_an_unknown_status_is_refused(self, db: Database) -> None:
        run = db.start_run(config_hash="abc", aoi="Tsho Rolpa")
        with pytest.raises(ValueError, match="status must be one of"):
            db.finish_run(run.id, "probably ok")

    def test_values_are_traceable_to_their_run(
        self, db: Database, site_id: int
    ) -> None:
        run = db.start_run(config_hash="abc", aoi="Tsho Rolpa")
        db.add_observation(
            site_id,
            obs_date="2023-10-19",
            sensor="S2",
            value_type="derived",
            run_id=run.id,
        )
        assert db.observations(site_id)[0]["run_id"] == run.id

    def test_code_version_is_none_outside_a_git_tree(self, tmp_path: Path) -> None:
        """Recorded as unknown rather than faked."""
        assert code_version(tmp_path) is None

    def test_code_version_reads_a_detached_head(self, tmp_path: Path) -> None:
        sha = "a" * 40
        (tmp_path / ".git").mkdir()
        (tmp_path / ".git" / "HEAD").write_text(sha, encoding="utf-8")
        assert code_version(tmp_path) == sha

    def test_code_version_follows_a_branch_ref(self, tmp_path: Path) -> None:
        sha = "b" * 40
        git = tmp_path / ".git"
        (git / "refs" / "heads").mkdir(parents=True)
        (git / "HEAD").write_text("ref: refs/heads/main\n", encoding="utf-8")
        (git / "refs" / "heads" / "main").write_text(sha, encoding="utf-8")
        assert code_version(tmp_path) == sha

    def test_code_version_reads_packed_refs(self, tmp_path: Path) -> None:
        sha = "c" * 40
        git = tmp_path / ".git"
        git.mkdir()
        (git / "HEAD").write_text("ref: refs/heads/main\n", encoding="utf-8")
        (git / "packed-refs").write_text(
            f"# pack-refs with: peeled\n{sha} refs/heads/main\n", encoding="utf-8"
        )
        assert code_version(tmp_path) == sha


class TestHelpers:
    def test_rows_to_dicts_drops_the_sqlite_type(
        self, db: Database, site_id: int
    ) -> None:
        db.add_observation(
            site_id, obs_date="2023-10-19", sensor="S2", value_type="derived"
        )
        rows = rows_to_dicts(db.observations(site_id))
        assert isinstance(rows[0], dict)
        assert rows[0]["sensor"] == "S2"


class TestStoredLevelCarriesItsCaveat:
    """A level stored without its coverage reads as a verdict (methods 11.3)."""

    def test_a_thin_evidence_assessment_is_flagged_in_storage(
        self, db: Database, site_id: int, cfg: Config
    ) -> None:
        assessment = assess_risk(cfg, slope_deg=18.0)
        assert assessment.insufficient_data
        db.add_risk_assessment(assessment.as_record(site_id))

        stored = db.latest_risk_assessment(site_id)
        assert stored["level"] == "NORMAL"
        assert stored["insufficient_data"] == 1
        assert stored["data_coverage"] < 0.5

    def test_a_well_evidenced_assessment_is_not_flagged(
        self, db: Database, site_id: int, cfg: Config
    ) -> None:
        assessment = assess_risk(
            cfg,
            lake_growth_rate_m2_per_day=0.0,
            lake_volume_m3=0.0,
            new_landslide_area_m2=0.0,
            blockage_confidence=0.0,
            slope_deg=15.0,
            rainfall_mm_24h=0.0,
        )
        db.add_risk_assessment(assessment.as_record(site_id))
        stored = db.latest_risk_assessment(site_id)
        assert stored["insufficient_data"] == 0
        assert stored["data_coverage"] == pytest.approx(1.0)

    def test_an_impossible_coverage_is_refused(
        self, db: Database, site_id: int
    ) -> None:
        with pytest.raises(sqlite3.IntegrityError):
            db.add_risk_assessment(
                {
                    "site_id": site_id,
                    "assessed_at": "2026-10-26T00:00:00Z",
                    "factors_json": "[]",
                    "score": 0.2,
                    "level": "NORMAL",
                    "config_version": "0.1.0",
                    "data_coverage": 1.7,
                    "insufficient_data": 0,
                }
            )
