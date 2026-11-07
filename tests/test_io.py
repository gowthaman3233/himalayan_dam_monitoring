"""Filesystem and GeoJSON helpers.

Every geometry below is a SYNTHETIC hand-written polygon, not real data.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from utils.io import (
    ensure_dir,
    ensure_parent,
    geojson_centroid,
    read_geojson_geometry,
    read_json,
    resolve_path,
    write_json,
)

pytestmark = pytest.mark.synthetic

# A synthetic 0.01-degree square near the default AOI. Used only to exercise
# parsing; it is not a real lake outline.
SQUARE = {
    "type": "Polygon",
    "coordinates": [
        [
            [86.46, 27.86],
            [86.47, 27.86],
            [86.47, 27.87],
            [86.46, 27.87],
            [86.46, 27.86],
        ]
    ],
}


# --------------------------------------------------------------------------- #
# Paths
# --------------------------------------------------------------------------- #


def test_ensure_dir_is_idempotent(tmp_path: Path) -> None:
    target = tmp_path / "a" / "b" / "c"
    assert ensure_dir(target).is_dir()
    assert ensure_dir(target).is_dir()


def test_ensure_parent_creates_only_the_parent(tmp_path: Path) -> None:
    target = tmp_path / "nested" / "file.json"
    returned = ensure_parent(target)
    assert returned.parent.is_dir()
    assert not returned.exists()


def test_resolve_path_treats_relative_as_repo_relative(root: Path) -> None:
    assert resolve_path("data/raw") == (root / "data" / "raw").resolve()


def test_resolve_path_honours_an_explicit_root(tmp_path: Path) -> None:
    assert resolve_path("x/y", root=tmp_path) == (tmp_path / "x" / "y").resolve()


def test_resolve_path_leaves_absolute_paths_alone(tmp_path: Path) -> None:
    absolute = (tmp_path / "already").resolve()
    assert resolve_path(absolute) == absolute


# --------------------------------------------------------------------------- #
# JSON
# --------------------------------------------------------------------------- #


def test_json_roundtrip_creates_missing_directories(tmp_path: Path) -> None:
    target = tmp_path / "deep" / "out.json"
    write_json({"branch": "C", "reason": "cloudy observation"}, target)
    assert read_json(target) == {"branch": "C", "reason": "cloudy observation"}


def test_json_writer_serialises_dates(tmp_path: Path) -> None:
    from datetime import date

    target = tmp_path / "dates.json"
    write_json({"obs_date": date(2023, 10, 15)}, target)
    assert read_json(target)["obs_date"] == "2023-10-15"


# --------------------------------------------------------------------------- #
# GeoJSON
# --------------------------------------------------------------------------- #


def _write(tmp_path: Path, obj: dict, name: str = "aoi.geojson") -> Path:
    path = tmp_path / name
    path.write_text(json.dumps(obj), encoding="utf-8")
    return path


def test_reads_a_bare_geometry(tmp_path: Path) -> None:
    assert read_geojson_geometry(_write(tmp_path, SQUARE)) == SQUARE


def test_reads_a_feature(tmp_path: Path) -> None:
    feature = {"type": "Feature", "properties": {}, "geometry": SQUARE}
    assert read_geojson_geometry(_write(tmp_path, feature)) == SQUARE


def test_reads_a_single_feature_collection(tmp_path: Path) -> None:
    fc = {
        "type": "FeatureCollection",
        "features": [{"type": "Feature", "properties": {}, "geometry": SQUARE}],
    }
    assert read_geojson_geometry(_write(tmp_path, fc)) == SQUARE


def test_dissolves_a_multi_feature_collection(tmp_path: Path) -> None:
    """Several features become one AOI geometry rather than silently using the first."""
    second = {
        "type": "Polygon",
        "coordinates": [
            [
                [86.48, 27.86],
                [86.49, 27.86],
                [86.49, 27.87],
                [86.48, 27.87],
                [86.48, 27.86],
            ]
        ],
    }
    fc = {
        "type": "FeatureCollection",
        "features": [
            {"type": "Feature", "properties": {}, "geometry": SQUARE},
            {"type": "Feature", "properties": {}, "geometry": second},
        ],
    }
    geom = read_geojson_geometry(_write(tmp_path, fc))
    assert geom["type"] in {"MultiPolygon", "Polygon"}

    from shapely.geometry import shape

    assert shape(geom).area == pytest.approx(2 * 0.01 * 0.01)


def test_missing_file_raises(tmp_path: Path) -> None:
    with pytest.raises(FileNotFoundError, match="not found"):
        read_geojson_geometry(tmp_path / "absent.geojson")


def test_feature_without_geometry_raises(tmp_path: Path) -> None:
    with pytest.raises(ValueError, match="no geometry"):
        read_geojson_geometry(
            _write(tmp_path, {"type": "Feature", "properties": {}, "geometry": None})
        )


def test_empty_feature_collection_raises(tmp_path: Path) -> None:
    with pytest.raises(ValueError, match="no geometries"):
        read_geojson_geometry(
            _write(tmp_path, {"type": "FeatureCollection", "features": []})
        )


def test_unsupported_type_raises(tmp_path: Path) -> None:
    with pytest.raises(ValueError, match="unsupported"):
        read_geojson_geometry(_write(tmp_path, {"type": "Topology"}))


def test_centroid_of_the_synthetic_square() -> None:
    lon, lat = geojson_centroid(SQUARE)
    assert lon == pytest.approx(86.465)
    assert lat == pytest.approx(27.865)


def test_centroid_picks_the_expected_utm_zone() -> None:
    """The centroid is only ever used to choose a projection, never to measure."""
    from utils.crs import utm_epsg_for_centroid

    assert utm_epsg_for_centroid(geojson_centroid(SQUARE)) == 32645
