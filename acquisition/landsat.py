"""Landsat 8/9 Collection 2 Level 2 acquisition.

Collections: ``LANDSAT/LC08/C02/T1_L2`` and ``LANDSAT/LC09/C02/T1_L2``
(verified 2026-10-03, see docs/methods.md 0.4).

Purpose (brief, Section 5): history before Sentinel-2 and long time series. In
particular the **August 2014 Jure event predates Sentinel-2**, so it can only be
approached through this path.

Landsat 8 and 9 are merged into one time series: they share the OLI/TIRS band
structure and Collection 2 Level 2 processing, so a merged series is the honest
representation of available coverage. The platform of every scene is recorded.

Scaling note: Collection 2 Level 2 surface reflectance is stored as scaled
integers and requires ``value * 2.75e-5 - 0.2`` to reach reflectance. That
conversion is **not** applied here -- raw values are exported so the stored
product stays auditable, and scaling happens in preprocessing. The factors are
recorded in each sidecar.
"""

from __future__ import annotations

from datetime import date
from pathlib import Path
from typing import Any

from acquisition.gee_client import (
    ProductMetadata,
    SceneRef,
    aoi_to_ee_geometry,
    export_image,
    initialize,
    millis_to_datetime,
    resolve_export_crs,
)
from config.schema import Config
from utils.logging import get_logger

log = get_logger(__name__)

SENSOR = "Landsat OLI/TIRS"
PROCESSING_LEVEL = "C2 L2"

#: Landsat 8 launched 2013-02-11; routine data from 2013-03-18.
LANDSAT8_EPOCH_START = date(2013, 3, 18)

#: USGS Collection 2 Level 2 surface-reflectance scaling. Recorded, not applied.
SR_SCALE_FACTOR = 2.75e-5
SR_ADD_OFFSET = -0.2

#: Landsat 8/9 native optical resolution. Exports are resampled to the project
#: 10 m grid, which does not create detail -- noted in each sidecar.
LANDSAT_NATIVE_SCALE_M = 30.0

_SCENE_PROPERTIES = (
    "WRS_PATH",
    "WRS_ROW",
    "SPACECRAFT_ID",
    "CLOUD_COVER",
    "CLOUD_COVER_LAND",
    "LANDSAT_PRODUCT_ID",
    "SUN_ELEVATION",
    "SUN_AZIMUTH",
    "COLLECTION_CATEGORY",
)


class LandsatError(RuntimeError):
    """A Landsat request that cannot be satisfied."""


def list_scenes(
    cfg: Config,
    *,
    start: date | None = None,
    end: date | None = None,
    limit: int | None = None,
) -> list[SceneRef]:
    """Landsat 8 and 9 scenes intersecting the AOI, merged and sorted by time."""
    import ee

    window = cfg.dates.query_window
    start = start or window.start
    end = end or window.end

    # Validate the window before touching the network.
    if end < LANDSAT8_EPOCH_START:
        raise LandsatError(
            f"the requested window ends {end}, before Landsat 8 data begins "
            f"({LANDSAT8_EPOCH_START}). Landsat 5/7 would be needed for earlier "
            f"dates and are not configured."
        )

    initialize(cfg)
    geometry = aoi_to_ee_geometry(cfg.aoi)
    collections = (cfg.gee.collections.landsat8_l2, cfg.gee.collections.landsat9_l2)

    merged: list[SceneRef] = []
    for collection_id in collections:
        collection = (
            ee.ImageCollection(collection_id)
            .filterBounds(geometry)
            .filterDate(start.isoformat(), _exclusive_end(end))
            .sort("system:time_start")
        )
        records = collection.toList(collection.size()).getInfo()
        for record in records:
            props = record.get("properties", {})
            merged.append(
                SceneRef(
                    ee_image_id=record["id"],
                    acquisition_start=millis_to_datetime(
                        props.get("system:time_start")
                    ),
                    acquisition_end=millis_to_datetime(props.get("system:time_end")),
                    orbit_or_tile=_wrs_label(
                        props.get("WRS_PATH"), props.get("WRS_ROW")
                    ),
                    platform=props.get("SPACECRAFT_ID"),
                    cloud_fraction=_as_float(props.get("CLOUD_COVER")),
                    extra={
                        "source_collection": collection_id,
                        **{
                            key: props.get(key)
                            for key in _SCENE_PROPERTIES
                            if props.get(key) is not None
                        },
                    },
                )
            )

    merged.sort(key=lambda s: (s.acquisition_start is None, s.acquisition_start))

    from acquisition.sentinel2 import _screen_cloud

    found = len(merged)
    merged, rejected = _screen_cloud(merged, cfg.acquisition.max_cloud_fraction)

    log.info(
        "Landsat: %d scene(s) over %s, %s to %s; %d kept, %d rejected as too "
        "cloudy (max_cloud_fraction=%s)",
        found,
        cfg.aoi.name,
        start,
        end,
        len(merged),
        rejected,
        cfg.acquisition.max_cloud_fraction,
    )
    if found and not merged:
        log.warning(
            "all %d Landsat scene(s) over %s between %s and %s exceed "
            "max_cloud_fraction=%s: no valid observation in this window",
            found,
            cfg.aoi.name,
            start,
            end,
            cfg.acquisition.max_cloud_fraction,
        )

    if limit is not None:
        merged = merged[:limit]
    return merged


def export_scene(
    cfg: Config,
    scene: SceneRef,
    *,
    out_dir: Path,
    run_id: str | None = None,
    config_hash: str | None = None,
    overwrite: bool = False,
) -> list[tuple[Path, Path]]:
    """Export one Landsat scene: reflectance and QA to separate GeoTIFFs.

    ``QA_PIXEL`` is a bit-packed 16-bit mask and the reflectance bands are
    scaled integers, so they are kept in separate files.
    """
    from datetime import datetime, timezone

    import ee

    initialize(cfg)

    image = ee.Image(scene.ee_image_id)
    geometry = aoi_to_ee_geometry(cfg.aoi)
    crs = resolve_export_crs(cfg)
    scale = cfg.gee.default_scale_m
    settings = cfg.acquisition.landsat
    collection_id = str(scene.extra.get("source_collection", "unknown"))
    platform_tag = (scene.platform or "LANDSAT").replace("_", "")

    groups: list[tuple[str, tuple[str, ...]]] = [("refl", settings.reflectance_bands)]
    if settings.qa_bands:
        groups.append(("qa", settings.qa_bands))

    results: list[tuple[Path, Path]] = []
    for suffix, bands in groups:
        name = f"LS_{platform_tag}_{scene.orbit_or_tile}_{scene.date_str}_{suffix}.tif"
        metadata = ProductMetadata(
            sensor=SENSOR,
            platform=scene.platform,
            processing_level=PROCESSING_LEVEL,
            source_collection=collection_id,
            ee_image_id=scene.ee_image_id,
            acquisition_start=scene.acquisition_start,
            acquisition_end=scene.acquisition_end,
            orbit_or_tile=scene.orbit_or_tile,
            # Landsat reports sun ELEVATION; the shadow code wants zenith.
            sun_zenith_deg=_elevation_to_zenith(scene.extra.get("SUN_ELEVATION")),
            sun_azimuth_deg=_as_azimuth(scene.extra.get("SUN_AZIMUTH")),
            bands=tuple(bands),
            crs=crs,
            scale_m=scale,
            aoi_name=cfg.aoi.name,
            aoi_kind=cfg.aoi.kind,
            value_type="observed",
            exported_at=datetime.now(tz=timezone.utc),
            run_id=run_id,
            config_hash=config_hash,
            notes=_notes(scene, suffix, scale),
        )
        results.append(
            export_image(
                image,
                region=geometry,
                out_path=Path(out_dir) / name,
                bands=bands,
                crs=crs,
                scale_m=scale,
                metadata=metadata,
                cfg=cfg,
                overwrite=overwrite,
            )
        )
    return results


def export_scenes(
    cfg: Config,
    *,
    start: date | None = None,
    end: date | None = None,
    limit: int | None = None,
    out_dir: Path | None = None,
    run_id: str | None = None,
    config_hash: str | None = None,
    overwrite: bool = False,
) -> list[tuple[Path, Path]]:
    """List and export Landsat scenes for the configured AOI."""
    from config.loader import resolved_paths

    limit = cfg.acquisition.max_scenes_per_sensor if limit is None else limit
    out_dir = Path(out_dir) if out_dir else resolved_paths(cfg)["raw"] / "landsat"

    scenes = list_scenes(cfg, start=start, end=end, limit=limit)
    if not scenes:
        log.warning(
            "no Landsat scenes for %s in the requested window; nothing exported",
            cfg.aoi.name,
        )
        return []

    exported: list[tuple[Path, Path]] = []
    for scene in scenes:
        exported.extend(
            export_scene(
                cfg,
                scene,
                out_dir=out_dir,
                run_id=run_id,
                config_hash=config_hash,
                overwrite=overwrite,
            )
        )
    return exported


def _elevation_to_zenith(elevation: Any) -> float | None:
    """Landsat reports sun elevation above the horizon; zenith = 90 - elevation."""
    value = _as_float(elevation)
    return None if value is None else 90.0 - value


def _as_azimuth(value: Any) -> float | None:
    """Landsat SUN_AZIMUTH can be negative; wrap into 0-360."""
    parsed = _as_float(value)
    return None if parsed is None else parsed % 360.0


def _wrs_label(path: Any, row: Any) -> str:
    path_int, row_int = _as_int(path), _as_int(row)
    if path_int is None or row_int is None:
        return "unknown"
    return f"p{path_int:03d}r{row_int:03d}"


def _notes(scene: SceneRef, group: str, export_scale_m: float) -> str:
    bits = [f"band group: {group}"]
    if group == "refl":
        bits.append(
            f"surface reflectance is scaled: reflectance = DN * {SR_SCALE_FACTOR} "
            f"{SR_ADD_OFFSET:+}; NOT applied on export"
        )
    if group == "qa":
        bits.append("QA_PIXEL is a bit-packed quality mask, not a class index")
    if export_scale_m < LANDSAT_NATIVE_SCALE_M:
        bits.append(
            f"resampled from {LANDSAT_NATIVE_SCALE_M:.0f} m native to the "
            f"{export_scale_m:.0f} m project grid; this adds no real detail"
        )
    if scene.cloud_fraction is not None:
        bits.append(f"scene CLOUD_COVER: {scene.cloud_fraction:.1f}%")
    elevation = scene.extra.get("SUN_ELEVATION")
    azimuth = scene.extra.get("SUN_AZIMUTH")
    if elevation is not None and azimuth is not None:
        bits.append(
            f"sun elevation {float(elevation):.3f} deg "
            f"(zenith {90.0 - float(elevation):.3f} deg), "
            f"azimuth {float(azimuth):.3f} deg"
        )
    product_id = scene.extra.get("LANDSAT_PRODUCT_ID")
    if product_id:
        bits.append(f"product {product_id}")
    return "; ".join(bits)


def _exclusive_end(end: date) -> str:
    from datetime import timedelta

    return (end + timedelta(days=1)).isoformat()


def _as_float(value: Any) -> float | None:
    if value is None:
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _as_int(value: Any) -> int | None:
    if value is None:
        return None
    try:
        return int(value)
    except (TypeError, ValueError):
        return None
