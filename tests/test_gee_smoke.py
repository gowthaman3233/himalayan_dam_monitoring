"""Phase 0 gate check: a live Earth Engine query returns real metadata.

This is also the standing verification the brief requires in Section 5 -- that
every collection ID and band name is checked against the live catalog rather
than trusted. The test reports what the catalog actually returns and writes it
to ``outputs/gee_catalog_probe.json`` for the record.

The whole module skips, with the reason printed, when no authenticated Earth
Engine session is available. Run it explicitly with:

    pytest -m gee -s
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from config.loader import load_config, resolved_paths
from config.schema import Config

pytestmark = [pytest.mark.gee, pytest.mark.network, pytest.mark.realdata]


@pytest.fixture(scope="module")
def live_cfg() -> Config:
    """Config loaded *with* ``.env``, since live access needs the project ID."""
    return load_config(load_env=True)


@pytest.fixture(scope="module")
def probe(live_cfg: Config) -> dict:
    """Run the catalog probe once, or skip the module with the reason."""
    gee_client = pytest.importorskip(
        "acquisition.gee_client", reason="acquisition.gee_client is not importable"
    )
    pytest.importorskip("ee", reason="earthengine-api is not installed")

    reason = gee_client.unavailable_reason(live_cfg)
    if reason is not None:
        pytest.skip(f"no Earth Engine session available.\n{reason}")

    result = gee_client.describe_collections(live_cfg)

    out_dir: Path = resolved_paths(live_cfg)["outputs"]
    out_dir.mkdir(parents=True, exist_ok=True)
    out_path = out_dir / "gee_catalog_probe.json"
    out_path.write_text(
        json.dumps(result, indent=2, sort_keys=True, default=str), encoding="utf-8"
    )
    print(f"\nGEE catalog probe written to {out_path}\n")
    print(json.dumps(result, indent=2, sort_keys=True, default=str))

    return result


# --------------------------------------------------------------------------- #
# Gate assertions
# --------------------------------------------------------------------------- #


def test_aoi_area_matches_the_configured_buffer(probe: dict, live_cfg: Config) -> None:
    """A point+buffer AOI should come back as a circle of pi * r^2."""
    import math

    from config.schema import PointBufferAOI

    if not isinstance(live_cfg.aoi, PointBufferAOI):
        pytest.skip("the configured AOI is not a point+buffer")

    expected_km2 = math.pi * (live_cfg.aoi.buffer_m / 1000.0) ** 2
    assert probe["_aoi"]["area_km2"] == pytest.approx(expected_km2, rel=0.02)


def test_every_configured_collection_resolves(probe: dict) -> None:
    """No configured collection ID may fail to resolve."""
    failures = {
        key: entry["error"]
        for key, entry in probe.items()
        if not key.startswith("_") and "error" in entry
    }
    assert not failures, f"collection IDs that did not resolve: {failures}"


def test_collections_return_images_for_the_aoi(probe: dict) -> None:
    """Report, rather than assume, which collections cover this AOI and window."""
    empty = [
        key
        for key, entry in probe.items()
        if not key.startswith("_") and entry.get("image_count") == 0
    ]
    assert not empty, (
        f"no images for {empty} over this AOI and date window -- widen "
        "dates.query_window in config.yaml, or check coverage"
    )


@pytest.mark.parametrize(
    ("collection_key", "required_bands"),
    [
        # Brief, Section 5. Band names are asserted because downstream modules
        # index them directly; if Copernicus renames one, this fails loudly.
        ("s2_sr", ["B2", "B3", "B4", "B8", "B11", "B12", "SCL"]),
        ("s1_grd", ["VV", "VH", "angle"]),
    ],
)
def test_required_bands_are_present(
    probe: dict, collection_key: str, required_bands: list[str]
) -> None:
    entry = probe[collection_key]
    bands = entry.get("band_names")
    assert bands, f"{collection_key} returned no band names"
    missing = [b for b in required_bands if b not in bands]
    assert not missing, (
        f"{collection_key} ({entry['id']}) is missing {missing}; it has {bands}"
    )


def test_sentinel2_exposes_solar_angles(probe: dict) -> None:
    """The terrain-shadow mask (brief, Section 7.1) needs per-scene sun geometry."""
    angles = probe["s2_sr"].get("solar_angles_first_image", {})
    zenith = angles.get("MEAN_SOLAR_ZENITH_ANGLE")
    azimuth = angles.get("MEAN_SOLAR_AZIMUTH_ANGLE")

    assert zenith is not None and azimuth is not None, (
        "MEAN_SOLAR_ZENITH_ANGLE / MEAN_SOLAR_AZIMUTH_ANGLE are absent; the "
        "terrain-shadow mask cannot be computed without them"
    )
    assert 0.0 <= float(zenith) <= 90.0
    assert 0.0 <= float(azimuth) <= 360.0


def test_sentinel1_orbit_metadata_is_recorded(probe: dict) -> None:
    """Brief, Section 5: ascending and descending orbits must stay separable."""
    directions = probe["s1_grd"].get("orbit_directions") or []
    assert directions, "no orbitProperties_pass values returned"
    assert set(directions) <= {"ASCENDING", "DESCENDING"}, directions
    assert probe["s1_grd"].get("relative_orbits"), "no relative orbit numbers returned"


def test_dem_is_available_and_undated(probe: dict) -> None:
    """GLO-30 is a static mosaic, so it is probed without a date filter."""
    entry = probe["dem_glo30"]
    assert entry["date_filtered"] is False
    assert entry.get("image_count", 0) > 0
    assert entry.get("band_names"), "DEM returned no band names"
