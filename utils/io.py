"""Filesystem and GeoJSON helpers.

Heavier geospatial libraries are imported lazily so that the plain path helpers
stay importable (and unit-testable) without GDAL/PROJ present.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

#: GeoJSON object types that carry coordinates directly.
_GEOMETRY_TYPES = {
    "Point",
    "MultiPoint",
    "LineString",
    "MultiLineString",
    "Polygon",
    "MultiPolygon",
    "GeometryCollection",
}


def ensure_dir(path: str | Path) -> Path:
    """Create ``path`` (and parents) if needed; return it resolved."""
    p = Path(path).expanduser()
    p.mkdir(parents=True, exist_ok=True)
    return p.resolve()


def ensure_parent(path: str | Path) -> Path:
    """Create the *parent* directory of ``path``; return ``path`` resolved.

    For use before writing a file to a directory that may not exist yet.
    """
    p = Path(path).expanduser()
    p.parent.mkdir(parents=True, exist_ok=True)
    return p.resolve()


def resolve_path(path: str | Path, root: str | Path | None = None) -> Path:
    """Resolve ``path``, treating relative paths as relative to ``root``.

    ``root`` defaults to the repository root, so a relative path means the same
    thing regardless of the current working directory.
    """
    p = Path(path).expanduser()
    if p.is_absolute():
        return p.resolve()
    if root is None:
        from config.loader import repo_root

        root = repo_root()
    return (Path(root) / p).resolve()


def read_json(path: str | Path) -> Any:
    with Path(path).open("r", encoding="utf-8") as fh:
        return json.load(fh)


def write_json(obj: Any, path: str | Path, *, indent: int = 2) -> Path:
    """Write ``obj`` as UTF-8 JSON, creating the parent directory if needed."""
    target = ensure_parent(path)
    with target.open("w", encoding="utf-8") as fh:
        json.dump(obj, fh, indent=indent, ensure_ascii=False, default=str)
        fh.write("\n")
    return target


def read_geojson_geometry(path: str | Path, root: str | Path | None = None) -> dict:
    """Read a GeoJSON file and return a single geometry mapping.

    Accepts a bare geometry, a ``Feature``, or a ``FeatureCollection``. A
    collection with several features is dissolved into one geometry so that an
    AOI is always a single area; this is reported by the caller rather than done
    silently in a pipeline step.

    Raises:
        FileNotFoundError: if the file is missing (checked here rather than in
            the config schema, which must stay valid on machines without data).
        ValueError: on an unrecognised or empty GeoJSON structure.
    """
    target = resolve_path(path, root)
    if not target.is_file():
        raise FileNotFoundError(f"GeoJSON AOI file not found: {target}")

    obj = read_json(target)
    if not isinstance(obj, dict):
        raise ValueError(f"not a GeoJSON object: {target}")

    obj_type = obj.get("type")

    if obj_type in _GEOMETRY_TYPES:
        return obj

    if obj_type == "Feature":
        geom = obj.get("geometry")
        if not isinstance(geom, dict):
            raise ValueError(f"Feature has no geometry: {target}")
        return geom

    if obj_type == "FeatureCollection":
        features = obj.get("features") or []
        geoms = [
            f["geometry"]
            for f in features
            if isinstance(f, dict) and isinstance(f.get("geometry"), dict)
        ]
        if not geoms:
            raise ValueError(f"FeatureCollection contains no geometries: {target}")
        if len(geoms) == 1:
            return geoms[0]
        return _union_geometries(geoms)

    raise ValueError(f"unsupported GeoJSON type {obj_type!r} in {target}")


def geojson_centroid(geometry: dict) -> tuple[float, float]:
    """``(lon, lat)`` centroid of a GeoJSON geometry, in input degrees.

    Used only to pick the UTM zone (``utils.crs``). It is a planar centroid of
    geographic coordinates, which is accurate enough to choose a 6-degree-wide
    zone but must never be used as a measurement.
    """
    from shapely.geometry import shape

    centroid = shape(geometry).centroid
    if centroid.is_empty:
        raise ValueError("geometry is empty; cannot compute a centroid")
    return (float(centroid.x), float(centroid.y))


def _union_geometries(geoms: list[dict]) -> dict:
    from shapely.geometry import mapping, shape
    from shapely.ops import unary_union

    return dict(mapping(unary_union([shape(g) for g in geoms])))
