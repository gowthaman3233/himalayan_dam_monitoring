"""Storage for sites, observations, estimates, events, assessments and runs.

Brief, Section 10. SQLite with geometry held as WKT, and the layer kept
**swappable**: callers use the :class:`MonitoringStore` methods, never SQL, so
a GeoPackage or PostGIS implementation can be dropped in behind the same
interface.

The database is a line of defence, not a passive container
----------------------------------------------------------
Two of this project's integrity rules are enforced here as ``CHECK``
constraints, so that even a buggy caller cannot persist a value the rest of
the system has promised never to produce:

1. **The Section 10 vocabulary.** Every stored value carries a ``value_type``
   drawn from ``observed``, ``classified``, ``estimated``, ``empirical``,
   ``derived`` or ``unavailable``. Anything else is rejected by the database.

2. **Section 8's rule that an unavailable depth is not a number.** A
   ``depth_volume_estimates`` row whose ``value_type`` is ``unavailable``
   must have NULL for every depth and volume column, and only Branch A may
   carry an ``estimated`` value. A Branch B lake physically cannot be stored
   with a volume, however it is passed in.

The second constraint matters because Phase 10 measured what the alternative
looks like: applying the Branch A formula to a Branch B lake yields
14.3, 21.7 or 30.9 million cubic metres purely according to a buffer width
(docs/methods.md 10.3). Those numbers look entirely plausible. The schema
refuses them.
"""

from __future__ import annotations

import sqlite3
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable, Protocol

from utils.logging import get_logger

log = get_logger(__name__)

#: Brief, Section 10. The complete vocabulary; nothing else may be stored.
VALUE_TYPES = (
    "observed",
    "classified",
    "estimated",
    "empirical",
    "derived",
    "unavailable",
)

#: Section 8 branches.
BRANCHES = ("A", "B", "C")

RUN_STATUSES = ("running", "completed", "failed")

_VALUE_TYPE_SQL = ", ".join(f"'{v}'" for v in VALUE_TYPES)
_BRANCH_SQL = ", ".join(f"'{b}'" for b in BRANCHES)
_RUN_STATUS_SQL = ", ".join(f"'{s}'" for s in RUN_STATUSES)

SCHEMA = f"""
CREATE TABLE IF NOT EXISTS runs (
    id            INTEGER PRIMARY KEY AUTOINCREMENT,
    started_at    TEXT NOT NULL,
    finished_at   TEXT,
    config_hash   TEXT NOT NULL,
    code_version  TEXT,
    aoi           TEXT NOT NULL,
    status        TEXT NOT NULL CHECK (status IN ({_RUN_STATUS_SQL})),
    log_path      TEXT
);

CREATE TABLE IF NOT EXISTS sites (
    id             INTEGER PRIMARY KEY AUTOINCREMENT,
    site_code      TEXT NOT NULL UNIQUE,
    site_type      TEXT NOT NULL,
    geometry       TEXT,
    lat            REAL,
    lon            REAL,
    elevation      REAL,
    first_detected TEXT,
    last_updated   TEXT,
    confidence     REAL CHECK (confidence IS NULL OR confidence BETWEEN 0.0 AND 1.0),
    status         TEXT
);

CREATE TABLE IF NOT EXISTS observations (
    id                INTEGER PRIMARY KEY AUTOINCREMENT,
    site_id           INTEGER NOT NULL REFERENCES sites(id) ON DELETE CASCADE,
    obs_date          TEXT NOT NULL,
    sensor            TEXT NOT NULL,
    orbit_or_tile     TEXT,
    cloud_fraction    REAL,
    water_area_m2     REAL,
    water_perimeter_m REAL,
    geometry          TEXT,
    search_distance_m REAL,
    value_type        TEXT NOT NULL CHECK (value_type IN ({_VALUE_TYPE_SQL})),
    method            TEXT,
    source_collection TEXT,
    run_id            INTEGER REFERENCES runs(id)
);

CREATE TABLE IF NOT EXISTS depth_volume_estimates (
    id                INTEGER PRIMARY KEY AUTOINCREMENT,
    site_id           INTEGER NOT NULL REFERENCES sites(id) ON DELETE CASCADE,
    obs_date          TEXT NOT NULL,
    branch            TEXT NOT NULL CHECK (branch IN ({_BRANCH_SQL})),
    wse_m             REAL,
    wse_uncertainty_m REAL,
    mean_depth_m      REAL,
    max_depth_m       REAL,
    volume_m3         REAL,
    volume_low_m3     REAL,
    volume_high_m3    REAL,
    value_type        TEXT NOT NULL CHECK (value_type IN ({_VALUE_TYPE_SQL})),
    method            TEXT,
    notes             TEXT,
    run_id            INTEGER REFERENCES runs(id),

    -- Brief, Section 8: an unavailable estimate is not a number.
    CHECK (
        value_type <> 'unavailable'
        OR (mean_depth_m IS NULL AND max_depth_m IS NULL
            AND volume_m3 IS NULL AND volume_low_m3 IS NULL
            AND volume_high_m3 IS NULL)
    ),
    -- Only Branch A may carry an estimated value. Branch B's bed is unknown
    -- and Branch C has insufficient data, so both are unavailable unless an
    -- approved empirical relationship is in use.
    CHECK (branch = 'A' OR value_type IN ('unavailable', 'empirical'))
);

CREATE TABLE IF NOT EXISTS landslide_events (
    id         INTEGER PRIMARY KEY AUTOINCREMENT,
    site_id    INTEGER REFERENCES sites(id) ON DELETE CASCADE,
    pre_date   TEXT NOT NULL,
    post_date  TEXT NOT NULL,
    area_m2    REAL,
    geometry   TEXT,
    confidence REAL CHECK (confidence IS NULL OR confidence BETWEEN 0.0 AND 1.0),
    method     TEXT,
    value_type TEXT NOT NULL DEFAULT 'classified'
               CHECK (value_type IN ({_VALUE_TYPE_SQL})),
    run_id     INTEGER REFERENCES runs(id),
    CHECK (post_date >= pre_date)
);

CREATE TABLE IF NOT EXISTS risk_assessments (
    id             INTEGER PRIMARY KEY AUTOINCREMENT,
    site_id        INTEGER NOT NULL REFERENCES sites(id) ON DELETE CASCADE,
    assessed_at    TEXT NOT NULL,
    factors_json   TEXT NOT NULL,
    score          REAL NOT NULL CHECK (score BETWEEN 0.0 AND 1.0),
    level          TEXT NOT NULL,
    config_version TEXT,
    -- Beyond the brief's minimum columns, and deliberately so: without these
    -- a stored row reads "NORMAL" with no sign that it rested on a tenth of
    -- the evidence. The level alone is false reassurance (docs/methods.md
    -- 11.3), so the caveat travels with it into storage.
    data_coverage     REAL CHECK (data_coverage IS NULL
                                  OR data_coverage BETWEEN 0.0 AND 1.0),
    insufficient_data INTEGER NOT NULL DEFAULT 0 CHECK (insufficient_data IN (0, 1)),
    run_id         INTEGER REFERENCES runs(id)
);

CREATE INDEX IF NOT EXISTS idx_observations_site_date
    ON observations (site_id, obs_date);
CREATE INDEX IF NOT EXISTS idx_depth_site_date
    ON depth_volume_estimates (site_id, obs_date);
CREATE INDEX IF NOT EXISTS idx_risk_site_time
    ON risk_assessments (site_id, assessed_at);
"""

TABLES = (
    "runs",
    "sites",
    "observations",
    "depth_volume_estimates",
    "landslide_events",
    "risk_assessments",
)


class ValueTypeError(ValueError):
    """A value_type outside the Section 10 vocabulary."""


def check_value_type(value_type: str) -> str:
    """Validate a ``value_type`` in Python as well as in SQL.

    Checked twice on purpose: the SQL constraint is the guarantee, and this
    gives the caller a clear error naming the vocabulary instead of an opaque
    ``IntegrityError``.
    """
    if value_type not in VALUE_TYPES:
        raise ValueTypeError(
            f"{value_type!r} is not one of the Section 10 value types: "
            f"{', '.join(VALUE_TYPES)}"
        )
    return value_type


def code_version(root: Path | None = None) -> str | None:
    """The current git commit, read from ``.git`` without invoking git.

    Returns ``None`` outside a git working tree, which is a normal state for
    this project rather than an error -- a run is still recorded, with the
    code version left unknown rather than faked.
    """
    base = Path(root) if root is not None else Path(__file__).resolve().parent.parent
    head = base / ".git" / "HEAD"
    try:
        content = head.read_text(encoding="utf-8").strip()
    except OSError:
        return None

    if content.startswith("ref:"):
        ref = content.partition(" ")[2].strip()
        try:
            return (base / ".git" / ref).read_text(encoding="utf-8").strip()
        except OSError:
            # A packed ref; resolving it properly needs packed-refs parsing.
            packed = base / ".git" / "packed-refs"
            try:
                for line in packed.read_text(encoding="utf-8").splitlines():
                    if line.startswith("#") or not line.strip():
                        continue
                    sha, _, name = line.partition(" ")
                    if name.strip() == ref:
                        return sha.strip()
            except OSError:
                return None
            return None
    return content or None


def _now() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


@dataclass(frozen=True)
class Run:
    """A recorded pipeline run, for tracing any stored value back to it."""

    id: int
    started_at: str
    config_hash: str
    aoi: str
    status: str
    code_version: str | None = None
    log_path: str | None = None


class MonitoringStore(Protocol):
    """The interface the rest of the project depends on.

    Brief, Section 4: "keep the DB layer swappable". Nothing outside this
    module should issue SQL; an alternative backend implements these methods.
    """

    def initialise(self) -> None: ...
    def start_run(self, *, config_hash: str, aoi: str, log_path: str | None = None) -> Run: ...
    def finish_run(self, run_id: int, status: str = "completed") -> None: ...
    def upsert_site(self, **fields: Any) -> int: ...
    def add_observation(self, site_id: int, **fields: Any) -> int: ...
    def add_depth_volume(self, record: dict[str, Any], *, run_id: int | None = None) -> int: ...
    def add_landslide_event(self, **fields: Any) -> int: ...
    def add_risk_assessment(self, record: dict[str, Any], *, run_id: int | None = None) -> int: ...


class Database:
    """SQLite implementation of :class:`MonitoringStore`.

    Usable as a context manager::

        with Database(path) as db:
            db.initialise()
            run = db.start_run(config_hash=..., aoi=...)
    """

    def __init__(self, path: str | Path = ":memory:") -> None:
        self.path = str(path)
        self._connection: sqlite3.Connection | None = None

    # -- lifecycle -------------------------------------------------------- #

    def connect(self) -> sqlite3.Connection:
        if self._connection is None:
            if self.path != ":memory:":
                Path(self.path).parent.mkdir(parents=True, exist_ok=True)
            self._connection = sqlite3.connect(self.path)
            self._connection.row_factory = sqlite3.Row
            # Not on by default in SQLite, so a dangling site_id would be
            # silently accepted without this.
            self._connection.execute("PRAGMA foreign_keys = ON")
        return self._connection

    def close(self) -> None:
        if self._connection is not None:
            self._connection.commit()
            self._connection.close()
            self._connection = None

    def __enter__(self) -> "Database":
        self.connect()
        return self

    def __exit__(self, *exc_info: object) -> None:
        self.close()

    #: Columns added after the first release, as
    #: ``{table: {column: SQL type}}``. ``CREATE TABLE IF NOT EXISTS`` leaves
    #: an existing table untouched, so a database written by an earlier
    #: version would silently lack these and every insert naming them would
    #: fail -- which is worse than a schema change, because it only shows up
    #: on the next write.
    ADDED_COLUMNS = {
        "observations": {
            "geometry": "TEXT",
            "search_distance_m": "REAL",
        },
    }

    def initialise(self) -> None:
        """Create the schema, and add any columns an older file predates.

        Safe to call repeatedly.
        """
        connection = self.connect()
        connection.executescript(SCHEMA)
        self._add_missing_columns(connection)
        connection.commit()
        log.info("database ready at %s (%d tables)", self.path, len(TABLES))

    def _add_missing_columns(self, connection: sqlite3.Connection) -> None:
        """Bring an older file up to the current schema.

        SQLite's ``ALTER TABLE ... ADD COLUMN`` is cheap and non-destructive,
        and a nullable column needs no backfill: a row written before the
        column existed genuinely has no value for it, and NULL says so.
        """
        for table, columns in self.ADDED_COLUMNS.items():
            existing = {
                row[1]
                for row in connection.execute(f"PRAGMA table_info({table})")
            }
            if not existing:
                continue  # the table itself is new, so SCHEMA just made it
            for column, sql_type in columns.items():
                if column in existing:
                    continue
                connection.execute(
                    f"ALTER TABLE {table} ADD COLUMN {column} {sql_type}"
                )
                log.info(
                    "added %s.%s to an existing database; rows written before "
                    "it hold NULL, which is correct -- they had no value",
                    table, column,
                )

    # -- runs ------------------------------------------------------------- #

    def start_run(
        self, *, config_hash: str, aoi: str, log_path: str | None = None
    ) -> Run:
        """Open a run, so every value stored under it is traceable."""
        connection = self.connect()
        version = code_version()
        cursor = connection.execute(
            "INSERT INTO runs (started_at, config_hash, code_version, aoi, status,"
            " log_path) VALUES (?, ?, ?, ?, 'running', ?)",
            (_now(), config_hash, version, aoi, log_path),
        )
        connection.commit()
        run = Run(
            id=int(cursor.lastrowid),
            started_at=_now(),
            config_hash=config_hash,
            aoi=aoi,
            status="running",
            code_version=version,
            log_path=log_path,
        )
        log.info(
            "run %d started (config %s, code %s)",
            run.id,
            config_hash[:12],
            version[:12] if version else "unknown",
        )
        return run

    def finish_run(self, run_id: int, status: str = "completed") -> None:
        if status not in RUN_STATUSES:
            raise ValueError(f"status must be one of {RUN_STATUSES}, got {status!r}")
        connection = self.connect()
        connection.execute(
            "UPDATE runs SET status = ?, finished_at = ? WHERE id = ?",
            (status, _now(), run_id),
        )
        connection.commit()

    # -- sites ------------------------------------------------------------ #

    def upsert_site(
        self,
        *,
        site_code: str,
        site_type: str,
        geometry: str | None = None,
        lat: float | None = None,
        lon: float | None = None,
        elevation: float | None = None,
        first_detected: str | None = None,
        confidence: float | None = None,
        status: str | None = None,
    ) -> int:
        """Insert a site, or update it if ``site_code`` already exists.

        ``first_detected`` is preserved on update: when a site was first seen
        is a fact about the site, not about the latest run.
        """
        connection = self.connect()
        connection.execute(
            """
            INSERT INTO sites (site_code, site_type, geometry, lat, lon, elevation,
                               first_detected, last_updated, confidence, status)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(site_code) DO UPDATE SET
                site_type   = excluded.site_type,
                geometry    = COALESCE(excluded.geometry, sites.geometry),
                lat         = COALESCE(excluded.lat, sites.lat),
                lon         = COALESCE(excluded.lon, sites.lon),
                elevation   = COALESCE(excluded.elevation, sites.elevation),
                last_updated = excluded.last_updated,
                confidence  = COALESCE(excluded.confidence, sites.confidence),
                status      = COALESCE(excluded.status, sites.status)
            """,
            (
                site_code,
                site_type,
                geometry,
                lat,
                lon,
                elevation,
                first_detected or _now(),
                _now(),
                confidence,
                status,
            ),
        )
        connection.commit()
        row = connection.execute(
            "SELECT id FROM sites WHERE site_code = ?", (site_code,)
        ).fetchone()
        return int(row["id"])

    def site(self, site_code: str) -> sqlite3.Row | None:
        return self.connect().execute(
            "SELECT * FROM sites WHERE site_code = ?", (site_code,)
        ).fetchone()

    def sites(self) -> list[sqlite3.Row]:
        return list(self.connect().execute("SELECT * FROM sites ORDER BY site_code"))

    # -- observations ----------------------------------------------------- #

    def add_observation(
        self,
        site_id: int,
        *,
        obs_date: str,
        sensor: str,
        value_type: str,
        orbit_or_tile: str | None = None,
        cloud_fraction: float | None = None,
        water_area_m2: float | None = None,
        water_perimeter_m: float | None = None,
        geometry: str | None = None,
        search_distance_m: float | None = None,
        method: str | None = None,
        source_collection: str | None = None,
        run_id: int | None = None,
    ) -> int:
        check_value_type(value_type)
        connection = self.connect()
        cursor = connection.execute(
            """
            INSERT INTO observations (site_id, obs_date, sensor, orbit_or_tile,
                cloud_fraction, water_area_m2, water_perimeter_m, geometry,
                search_distance_m, value_type, method, source_collection,
                run_id)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                site_id,
                obs_date,
                sensor,
                orbit_or_tile,
                cloud_fraction,
                water_area_m2,
                water_perimeter_m,
                geometry,
                search_distance_m,
                value_type,
                method,
                source_collection,
                run_id,
            ),
        )
        connection.commit()
        return int(cursor.lastrowid)

    def observations(self, site_id: int) -> list[sqlite3.Row]:
        """Observations for a site, oldest first.

        Gaps are gaps: a date with no usable observation is simply absent, and
        nothing here interpolates between the rows that exist.
        """
        return list(
            self.connect().execute(
                "SELECT * FROM observations WHERE site_id = ? ORDER BY obs_date",
                (site_id,),
            )
        )

    # -- depth and volume -------------------------------------------------- #

    def add_depth_volume(
        self, record: dict[str, Any], *, run_id: int | None = None
    ) -> int:
        """Store a Phase 10 estimate.

        ``record`` is what ``DepthVolumeEstimate.as_record()`` returns, so the
        analysis and storage layers share one shape.
        """
        check_value_type(record["value_type"])
        if record["branch"] not in BRANCHES:
            raise ValueError(
                f"branch must be one of {BRANCHES}, got {record['branch']!r}"
            )
        connection = self.connect()
        cursor = connection.execute(
            """
            INSERT INTO depth_volume_estimates (site_id, obs_date, branch, wse_m,
                wse_uncertainty_m, mean_depth_m, max_depth_m, volume_m3,
                volume_low_m3, volume_high_m3, value_type, method, notes, run_id)
            VALUES (:site_id, :obs_date, :branch, :wse_m, :wse_uncertainty_m,
                    :mean_depth_m, :max_depth_m, :volume_m3, :volume_low_m3,
                    :volume_high_m3, :value_type, :method, :notes, :run_id)
            """,
            {**record, "run_id": run_id},
        )
        connection.commit()
        return int(cursor.lastrowid)

    def depth_volume_estimates(self, site_id: int) -> list[sqlite3.Row]:
        return list(
            self.connect().execute(
                "SELECT * FROM depth_volume_estimates WHERE site_id = ?"
                " ORDER BY obs_date",
                (site_id,),
            )
        )

    # -- landslide events --------------------------------------------------- #

    def add_landslide_event(
        self,
        *,
        pre_date: str,
        post_date: str,
        site_id: int | None = None,
        area_m2: float | None = None,
        geometry: str | None = None,
        confidence: float | None = None,
        method: str | None = None,
        value_type: str = "classified",
        run_id: int | None = None,
    ) -> int:
        check_value_type(value_type)
        connection = self.connect()
        cursor = connection.execute(
            """
            INSERT INTO landslide_events (site_id, pre_date, post_date, area_m2,
                geometry, confidence, method, value_type, run_id)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                site_id,
                pre_date,
                post_date,
                area_m2,
                geometry,
                confidence,
                method,
                value_type,
                run_id,
            ),
        )
        connection.commit()
        return int(cursor.lastrowid)

    def landslide_events(self, site_id: int | None = None) -> list[sqlite3.Row]:
        connection = self.connect()
        if site_id is None:
            return list(connection.execute("SELECT * FROM landslide_events"))
        return list(
            connection.execute(
                "SELECT * FROM landslide_events WHERE site_id = ?", (site_id,)
            )
        )

    # -- risk --------------------------------------------------------------- #

    def add_risk_assessment(
        self, record: dict[str, Any], *, run_id: int | None = None
    ) -> int:
        """Store a Phase 11 assessment, as ``RiskAssessment.as_record()`` gives it."""
        record = {
            "data_coverage": None,
            "insufficient_data": 0,
            **record,
        }
        connection = self.connect()
        cursor = connection.execute(
            """
            INSERT INTO risk_assessments (site_id, assessed_at, factors_json,
                score, level, config_version, data_coverage, insufficient_data,
                run_id)
            VALUES (:site_id, :assessed_at, :factors_json, :score, :level,
                    :config_version, :data_coverage, :insufficient_data, :run_id)
            """,
            {**record, "run_id": run_id},
        )
        connection.commit()
        return int(cursor.lastrowid)

    def latest_risk_assessment(self, site_id: int) -> sqlite3.Row | None:
        return self.connect().execute(
            "SELECT * FROM risk_assessments WHERE site_id = ?"
            " ORDER BY assessed_at DESC, id DESC LIMIT 1",
            (site_id,),
        ).fetchone()

    # -- introspection ------------------------------------------------------ #

    def table_names(self) -> list[str]:
        return [
            row["name"]
            for row in self.connect().execute(
                "SELECT name FROM sqlite_master WHERE type = 'table'"
                " AND name NOT LIKE 'sqlite_%' ORDER BY name"
            )
        ]

    def counts(self) -> dict[str, int]:
        connection = self.connect()
        return {
            table: int(
                connection.execute(f"SELECT COUNT(*) AS n FROM {table}").fetchone()["n"]
            )
            for table in TABLES
        }


def rows_to_dicts(rows: Iterable[sqlite3.Row]) -> list[dict[str, Any]]:
    """Plain dicts, for callers that should not depend on sqlite3 types."""
    return [dict(row) for row in rows]
