"""Acquisition logic that can be checked without touching Earth Engine.

Live catalog behaviour is covered by ``tests/test_gee_smoke.py`` and
``tests/test_acquisition_live.py``. Everything here is pure logic: metadata
records, size guards, CRS selection, sensor-epoch guards and the DEM
Branch A/B decision.

Scene records built here are SYNTHETIC: hand-written metadata used to exercise
logic, never real imagery or real acquisition records.
"""

from __future__ import annotations

from datetime import date, datetime, timezone
from pathlib import Path

import pytest

from acquisition import landsat, sentinel1, sentinel2
from acquisition.dem import DEMEpoch
from acquisition.gee_client import (
    ProductMetadata,
    SceneRef,
    estimate_export_bytes,
    millis_to_datetime,
    resolve_export_crs,
)
from config.loader import ConfigError, load_config
from config.schema import Config

# --------------------------------------------------------------------------- #
# Export CRS selection (brief, Section 6)
# --------------------------------------------------------------------------- #


def test_auto_export_crs_derives_utm_from_the_aoi(cfg: Config) -> None:
    assert cfg.acquisition.export_crs == "auto"
    assert resolve_export_crs(cfg) == "EPSG:32645"


def test_explicit_export_crs_overrides_auto(mutable_config, write_config) -> None:
    mutable_config["acquisition"]["export_crs"] = "EPSG:32644"
    loaded = load_config(write_config(mutable_config), load_env=False)
    assert resolve_export_crs(loaded) == "EPSG:32644"


def test_malformed_export_crs_is_rejected(mutable_config, write_config) -> None:
    mutable_config["acquisition"]["export_crs"] = "utm45n"
    with pytest.raises(ConfigError, match="export_crs"):
        load_config(write_config(mutable_config), load_env=False)


# --------------------------------------------------------------------------- #
# Acquisition config validation
# --------------------------------------------------------------------------- #


def test_empty_band_list_is_rejected(mutable_config, write_config) -> None:
    """A band list that silently empties would export a file with no data."""
    mutable_config["acquisition"]["sentinel2"]["reflectance_bands"] = []
    with pytest.raises(ConfigError):
        load_config(write_config(mutable_config), load_env=False)


def test_zero_scene_limit_is_rejected(mutable_config, write_config) -> None:
    mutable_config["acquisition"]["max_scenes_per_sensor"] = 0
    with pytest.raises(ConfigError):
        load_config(write_config(mutable_config), load_env=False)


def test_bad_orbit_pass_is_rejected(mutable_config, write_config) -> None:
    mutable_config["acquisition"]["sentinel1"]["orbit_pass"] = "SIDEWAYS"
    with pytest.raises(ConfigError):
        load_config(write_config(mutable_config), load_env=False)


def test_incidence_angle_band_is_configured(cfg: Config) -> None:
    """Phase 2's SAR layover/shadow mask cannot be built without it."""
    assert "angle" in cfg.acquisition.sentinel1.bands


def test_dem_height_error_band_is_configured(cfg: Config) -> None:
    """HEM feeds depth uncertainty propagation in Phase 10 (brief, Section 8)."""
    assert "HEM" in cfg.acquisition.dem.bands


# --------------------------------------------------------------------------- #
# Export size guard
# --------------------------------------------------------------------------- #


@pytest.mark.synthetic
def test_export_size_estimate() -> None:
    # 1 km^2 at 10 m = 100x100 = 10,000 px; 6 bands x 4 bytes = 240,000 bytes.
    assert estimate_export_bytes(1_000_000, 10.0, 6) == 240_000


@pytest.mark.synthetic
def test_export_size_estimate_scales_with_resolution() -> None:
    fine = estimate_export_bytes(1_000_000, 10.0, 1)
    coarse = estimate_export_bytes(1_000_000, 20.0, 1)
    assert fine == pytest.approx(coarse * 4)


def test_default_aoi_export_fits_the_configured_budget(cfg: Config) -> None:
    """The shipped AOI must be exportable on a laptop (brief, Section 3)."""
    import math

    area = math.pi * cfg.aoi.buffer_m**2
    estimate = estimate_export_bytes(
        area, cfg.gee.default_scale_m, len(cfg.acquisition.sentinel2.reflectance_bands)
    )
    assert estimate < cfg.acquisition.max_export_bytes


# --------------------------------------------------------------------------- #
# Scene records
# --------------------------------------------------------------------------- #


@pytest.mark.synthetic
def test_scene_date_string_for_filenames() -> None:
    scene = SceneRef(
        ee_image_id="SYNTHETIC/IMAGE/1",
        acquisition_start=datetime(2023, 10, 4, 5, 1, 6, tzinfo=timezone.utc),
        orbit_or_tile="45RVL",
    )
    assert scene.date_str == "20231004T050106"


@pytest.mark.synthetic
def test_undated_scene_does_not_crash_filename_building() -> None:
    scene = SceneRef(ee_image_id="SYNTHETIC/IMAGE/2", orbit_or_tile="45RVL")
    assert scene.date_str == "undated"


@pytest.mark.synthetic
def test_millis_conversion_is_utc() -> None:
    converted = millis_to_datetime(1696395666000)
    assert converted is not None
    assert converted.tzinfo is not None
    assert converted.utcoffset().total_seconds() == 0
    assert millis_to_datetime(None) is None


# --------------------------------------------------------------------------- #
# Product metadata (brief, Section 5 and Section 10)
# --------------------------------------------------------------------------- #


def _metadata(**overrides) -> ProductMetadata:
    base = dict(
        sensor="Sentinel-2 MSI",
        processing_level="L2A",
        source_collection="COPERNICUS/S2_SR_HARMONIZED",
        orbit_or_tile="45RVL",
        bands=("B2", "B3"),
        crs="EPSG:32645",
        scale_m=10.0,
        aoi_name="synthetic AOI",
        aoi_kind="point",
        exported_at=datetime(2026, 10, 3, 12, 0, tzinfo=timezone.utc),
    )
    base.update(overrides)
    return ProductMetadata(**base)


@pytest.mark.synthetic
def test_metadata_carries_everything_section_5_requires() -> None:
    meta = _metadata(
        acquisition_start=datetime(2023, 10, 4, tzinfo=timezone.utc),
        platform="Sentinel-2A",
    )
    # sensor, acquisition date(s), orbit/tile, processing level, source collection
    assert meta.sensor and meta.processing_level and meta.source_collection
    assert meta.orbit_or_tile and meta.acquisition_start


@pytest.mark.synthetic
def test_raw_imagery_defaults_to_observed() -> None:
    """Brief, Section 10: raw satellite imagery is 'observed', nothing else."""
    assert _metadata().value_type == "observed"


@pytest.mark.synthetic
def test_invalid_value_type_is_rejected() -> None:
    with pytest.raises(ValueError):
        _metadata(value_type="probably_water")


@pytest.mark.synthetic
def test_metadata_rejects_unknown_fields() -> None:
    with pytest.raises(ValueError):
        _metadata(sensro="typo")


@pytest.mark.synthetic
def test_sidecar_round_trip(tmp_path: Path) -> None:
    raster = tmp_path / "S2_45RVL_20231004T050106_refl.tif"
    meta = _metadata(acquisition_start=datetime(2023, 10, 4, tzinfo=timezone.utc))

    sidecar = meta.write_sidecar(raster)
    assert sidecar.name == raster.name + ".json"

    from utils.io import read_json

    restored = ProductMetadata.model_validate(read_json(sidecar))
    assert restored.source_collection == meta.source_collection
    assert restored.bands == meta.bands
    assert restored.acquisition_start == meta.acquisition_start


# --------------------------------------------------------------------------- #
# Sensor epoch guards -- must fail before any network call
# --------------------------------------------------------------------------- #


def test_sentinel2_refuses_a_pre_2015_window(cfg: Config) -> None:
    """Brief, Section 6: the August 2014 Jure event is a Landsat case, not S2."""
    with pytest.raises(sentinel2.Sentinel2Error, match="before Sentinel-2"):
        sentinel2.list_scenes(cfg, start=date(2014, 8, 1), end=date(2014, 8, 31))


def test_sentinel1_refuses_a_window_before_the_mission(cfg: Config) -> None:
    with pytest.raises(sentinel1.Sentinel1Error, match="before Sentinel-1"):
        sentinel1.list_scenes(cfg, start=date(2013, 1, 1), end=date(2013, 6, 30))


def test_landsat_refuses_a_window_before_landsat8(cfg: Config) -> None:
    with pytest.raises(landsat.LandsatError, match="before Landsat 8"):
        landsat.list_scenes(cfg, start=date(2010, 1, 1), end=date(2010, 12, 31))


def test_sentinel2_epoch_matches_the_brief() -> None:
    """Sentinel-2 data begins mid-2015 (brief, Section 5)."""
    assert sentinel2.S2_EPOCH_START.year == 2015


# --------------------------------------------------------------------------- #
# Scene-level cloud screening
# --------------------------------------------------------------------------- #
# Distinct from the per-pixel cloud mask in Phase 2: this only decides which
# scenes are worth downloading.


def _scene(cloud: float | None, day: int = 1) -> SceneRef:
    """A SYNTHETIC scene record carrying only a cloud fraction."""
    return SceneRef(
        ee_image_id=f"SYNTHETIC/S2/{day}",
        acquisition_start=datetime(2023, 10, day, tzinfo=timezone.utc),
        orbit_or_tile="45RVL",
        cloud_fraction=cloud,
    )


@pytest.mark.synthetic
def test_cloud_screen_keeps_scenes_at_or_below_the_threshold() -> None:
    scenes = [_scene(0.84, 1), _scene(40.0, 2), _scene(40.01, 3), _scene(99.88, 4)]
    kept, rejected = sentinel2._screen_cloud(scenes, 40.0)
    assert [s.cloud_fraction for s in kept] == [0.84, 40.0]
    assert rejected == 2


@pytest.mark.synthetic
def test_cloud_screen_disabled_keeps_everything() -> None:
    scenes = [_scene(0.84, 1), _scene(99.88, 2)]
    kept, rejected = sentinel2._screen_cloud(scenes, None)
    assert len(kept) == 2
    assert rejected == 0


@pytest.mark.synthetic
def test_scene_with_unknown_cloud_fraction_is_kept() -> None:
    """An absent value is not evidence of clear sky, and must not hide coverage."""
    kept, rejected = sentinel2._screen_cloud([_scene(None)], 40.0)
    assert len(kept) == 1
    assert rejected == 0


@pytest.mark.synthetic
def test_fully_cloudy_window_yields_no_scenes_without_crashing() -> None:
    """Brief, Section 13 test 9: a cloudy-only window degrades gracefully.

    The screen must return an empty list rather than raising, so the caller can
    report "no valid observation" instead of appearing to find no coverage.
    """
    scenes = [_scene(99.88, 1), _scene(95.0, 2), _scene(100.0, 3)]
    kept, rejected = sentinel2._screen_cloud(scenes, 40.0)
    assert kept == []
    assert rejected == 3


def test_cloud_threshold_is_configured_and_in_range(cfg: Config) -> None:
    threshold = cfg.acquisition.max_cloud_fraction
    assert threshold is not None
    assert 0.0 <= threshold <= 100.0


def test_out_of_range_cloud_threshold_is_rejected(
    mutable_config, write_config
) -> None:
    mutable_config["acquisition"]["max_cloud_fraction"] = 150.0
    with pytest.raises(ConfigError):
        load_config(write_config(mutable_config), load_env=False)


# --------------------------------------------------------------------------- #
# Label helpers
# --------------------------------------------------------------------------- #


@pytest.mark.synthetic
@pytest.mark.parametrize(
    ("pass_direction", "relative_orbit", "expected"),
    [
        ("ASCENDING", 85, "ASC085"),
        ("DESCENDING", 12, "DESC012"),
        ("ASCENDING", 121, "ASC121"),
        ("ASCENDING", None, "ASC"),
        (None, 12, "UNK012"),
    ],
)
def test_sentinel1_orbit_label(pass_direction, relative_orbit, expected) -> None:
    """The orbit must be legible in the filename (brief, Section 5)."""
    assert sentinel1._orbit_label(pass_direction, relative_orbit) == expected


@pytest.mark.synthetic
@pytest.mark.parametrize(
    ("path", "row", "expected"),
    [(141, 41, "p141r041"), (1, 1, "p001r001"), (None, 41, "unknown")],
)
def test_landsat_wrs_label(path, row, expected) -> None:
    assert landsat._wrs_label(path, row) == expected


@pytest.mark.synthetic
def test_landsat_notes_record_the_reflectance_scaling() -> None:
    """The scaling is recorded rather than applied, so it must be in the notes."""
    scene = SceneRef(ee_image_id="SYNTHETIC/LS/1", orbit_or_tile="p141r041")
    notes = landsat._notes(scene, "refl", 10.0)
    assert "2.75e-05" in notes or "2.75e-5" in notes
    assert "NOT applied" in notes
    assert "adds no real detail" in notes


# --------------------------------------------------------------------------- #
# DEM epoch and the Branch A/B decision (brief, Section 8)
# --------------------------------------------------------------------------- #


def _epoch(latest: datetime, earliest: datetime | None = None) -> DEMEpoch:
    """A SYNTHETIC epoch record for exercising branch logic."""
    earliest = earliest or datetime(2011, 1, 5, tzinfo=timezone.utc)
    return DEMEpoch(
        source_collection="COPERNICUS/DEM/GLO30_2024_1",
        aoi_name="synthetic AOI",
        earliest_acquisition=earliest,
        latest_acquisition=latest,
        distinct_start_dates=(earliest.date().isoformat(),),
        distinct_end_dates=(latest.date().isoformat(),),
        tile_versions_present=("01", "02"),
        tile_version_selected="02",
        entries_intersecting_aoi=361,
        entries_selected=9,
    )


@pytest.mark.synthetic
def test_hinge_date_is_the_latest_acquisition() -> None:
    """Conservative by design: ambiguity must resolve towards 'unavailable'."""
    epoch = _epoch(datetime(2014, 9, 8, 12, 19, 52, tzinfo=timezone.utc))
    assert epoch.branch_hinge_date == date(2014, 9, 8)


@pytest.mark.synthetic
def test_lake_predating_the_dem_is_branch_b() -> None:
    """Brief, Section 8: the DEM recorded the water surface; depth unavailable."""
    epoch = _epoch(datetime(2014, 9, 8, tzinfo=timezone.utc))
    assert epoch.branch_for_lake(date(2012, 6, 1)) == "B"


@pytest.mark.synthetic
def test_lake_on_the_hinge_date_is_branch_b() -> None:
    """The boundary resolves to B, never A -- it must not fabricate a depth."""
    epoch = _epoch(datetime(2014, 9, 8, tzinfo=timezone.utc))
    assert epoch.branch_for_lake(date(2014, 9, 8)) == "B"


@pytest.mark.synthetic
def test_lake_postdating_the_dem_is_branch_a() -> None:
    epoch = _epoch(datetime(2014, 9, 8, tzinfo=timezone.utc))
    assert epoch.branch_for_lake(date(2015, 6, 1)) == "A"
    assert epoch.branch_for_lake(date(2023, 10, 4)) == "A"


@pytest.mark.synthetic
def test_epoch_round_trips_through_disk(tmp_path: Path) -> None:
    from acquisition.dem import load_epoch
    from utils.io import write_json

    epoch = _epoch(datetime(2014, 9, 8, tzinfo=timezone.utc))
    path = tmp_path / "dem_epoch.json"
    write_json(epoch.model_dump(mode="json"), path)

    restored = load_epoch(path)
    assert restored.branch_hinge_date == epoch.branch_hinge_date
    assert restored.tile_version_selected == "02"


@pytest.mark.synthetic
def test_epoch_summary_states_the_hinge_date() -> None:
    """The summary is logged and read by humans; it must name the hinge."""
    summary = _epoch(datetime(2014, 9, 8, tzinfo=timezone.utc)).summary()
    assert "2014-09-08" in summary
    assert "Branch A" in summary
