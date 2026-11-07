"""Sentinel-2 L2A acquisition.

Collection: ``COPERNICUS/S2_SR_HARMONIZED`` (verified 2026-10-03, see
docs/methods.md 0.4).

Scenes are listed and exported **individually**, never composited here.
Compositing belongs to preprocessing (Phase 2) and would be wrong before cloud
masking; per-scene export also preserves the per-scene sun geometry that the
terrain-shadow mask requires (brief, Section 7.1).

Reflectance and QA bands go to **separate** GeoTIFFs: SCL is 8-bit class codes
and the reflectance bands are 16-bit integers, so writing them into one file
would force a lossy common dtype.
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

SENSOR = "Sentinel-2 MSI"
PROCESSING_LEVEL = "L2A"

#: Sentinel-2 data begins mid-2015 (brief, Section 5). Earlier requests cannot
#: be satisfied and are refused rather than silently returning nothing.
#: First Sentinel-2A acquisitions became available 2015-06-23.
S2_EPOCH_START = date(2015, 6, 23)

#: Scene properties pulled for provenance. MEAN_SOLAR_* are required by the
#: Phase 2 terrain-shadow mask.
_SCENE_PROPERTIES = (
    "MGRS_TILE",
    "SPACECRAFT_NAME",
    "CLOUDY_PIXEL_PERCENTAGE",
    "MEAN_SOLAR_ZENITH_ANGLE",
    "MEAN_SOLAR_AZIMUTH_ANGLE",
    "PROCESSING_BASELINE",
    "SENSING_ORBIT_NUMBER",
)


class Sentinel2Error(RuntimeError):
    """A Sentinel-2 request that cannot be satisfied."""


def list_scenes(
    cfg: Config,
    *,
    start: date | None = None,
    end: date | None = None,
    limit: int | None = None,
) -> list[SceneRef]:
    """Sentinel-2 scenes intersecting the AOI in the date window.

    Returns them sorted by acquisition time, oldest first. No pixels are
    downloaded.

    Raises:
        Sentinel2Error: if the window ends before Sentinel-2 existed.
    """
    import ee

    window = cfg.dates.query_window
    start = start or window.start
    end = end or window.end

    # Validate the window before touching the network, so an impossible request
    # fails fast and without credentials.
    if end < S2_EPOCH_START:
        raise Sentinel2Error(
            f"the requested window ends {end}, before Sentinel-2 data begins "
            f"({S2_EPOCH_START}). Use the Landsat path for earlier dates "
            f"(brief, Section 6: the 2014 Jure event is a Landsat test case)."
        )
    if start < S2_EPOCH_START:
        log.warning(
            "window starts %s, before Sentinel-2 data begins %s; "
            "the effective start is %s",
            start,
            S2_EPOCH_START,
            S2_EPOCH_START,
        )
        start = S2_EPOCH_START

    initialize(cfg)
    geometry = aoi_to_ee_geometry(cfg.aoi)
    collection = (
        ee.ImageCollection(cfg.gee.collections.s2_sr)
        .filterBounds(geometry)
        .filterDate(start.isoformat(), _exclusive_end(end))
        .sort("system:time_start")
    )

    records = collection.toList(collection.size()).getInfo()
    scenes: list[SceneRef] = []
    for record in records:
        props = record.get("properties", {})
        scenes.append(
            SceneRef(
                ee_image_id=record["id"],
                acquisition_start=millis_to_datetime(props.get("system:time_start")),
                acquisition_end=millis_to_datetime(props.get("system:time_end")),
                orbit_or_tile=str(props.get("MGRS_TILE", "unknown")),
                platform=props.get("SPACECRAFT_NAME"),
                cloud_fraction=_as_float(props.get("CLOUDY_PIXEL_PERCENTAGE")),
                extra={
                    key: props.get(key)
                    for key in _SCENE_PROPERTIES
                    if props.get(key) is not None
                },
            )
        )

    found = len(scenes)
    scenes, rejected = _screen_cloud(scenes, cfg.acquisition.max_cloud_fraction)

    log.info(
        "Sentinel-2: %d scene(s) over %s, %s to %s; %d kept, %d rejected as "
        "too cloudy (max_cloud_fraction=%s)",
        found,
        cfg.aoi.name,
        start,
        end,
        len(scenes),
        rejected,
        cfg.acquisition.max_cloud_fraction,
    )
    if found and not scenes:
        # Brief, Section 13 test 9: a cloudy-only window must degrade
        # gracefully into "no valid observation", not look like no coverage.
        log.warning(
            "all %d Sentinel-2 scene(s) over %s between %s and %s exceed "
            "max_cloud_fraction=%s: no valid observation in this window",
            found,
            cfg.aoi.name,
            start,
            end,
            cfg.acquisition.max_cloud_fraction,
        )

    if limit is not None:
        scenes = scenes[:limit]
    return scenes


def _screen_cloud(
    scenes: list[SceneRef], max_cloud_fraction: float | None
) -> tuple[list[SceneRef], int]:
    """Drop scenes above the cloud threshold, returning the rejected count.

    A scene with no reported cloud fraction is **kept**: an absent value is not
    evidence of clear sky, and discarding it would hide real coverage.
    """
    if max_cloud_fraction is None:
        return scenes, 0
    kept = [
        s
        for s in scenes
        if s.cloud_fraction is None or s.cloud_fraction <= max_cloud_fraction
    ]
    return kept, len(scenes) - len(kept)


def export_scene(
    cfg: Config,
    scene: SceneRef,
    *,
    out_dir: Path,
    run_id: str | None = None,
    config_hash: str | None = None,
    overwrite: bool = False,
) -> list[tuple[Path, Path]]:
    """Export one scene as up to two GeoTIFFs: reflectance, and QA.

    Returns a list of ``(raster_path, sidecar_path)`` pairs.
    """
    import ee
    from datetime import datetime, timezone

    initialize(cfg)

    image = ee.Image(scene.ee_image_id)
    geometry = aoi_to_ee_geometry(cfg.aoi)
    crs = resolve_export_crs(cfg)
    scale = cfg.gee.default_scale_m
    settings = cfg.acquisition.sentinel2

    groups: list[tuple[str, tuple[str, ...], Any]] = [
        ("refl", settings.reflectance_bands, image)
    ]
    if settings.qa_bands:
        groups.append(("qa", settings.qa_bands, image))

    if settings.cloud_score_bands:
        # Cloud Score+ lives in its own collection, matched to this scene by
        # system:index (Pasquarella et al. 2023). Exported as its own file
        # because it is float, unlike the integer reflectance and SCL bands.
        cs_image = _cloud_score_image(cfg, scene)
        if cs_image is not None:
            groups.append(("cs", settings.cloud_score_bands, cs_image))
        else:
            log.warning(
                "no Cloud Score+ image matches %s; cloud masking will fall back "
                "to SCL for this scene",
                scene.ee_image_id,
            )

    results: list[tuple[Path, Path]] = []
    for suffix, bands, source_image in groups:
        name = f"S2_{scene.orbit_or_tile}_{scene.date_str}_{suffix}.tif"
        metadata = ProductMetadata(
            sensor=SENSOR,
            platform=scene.platform,
            processing_level=PROCESSING_LEVEL,
            source_collection=(
                cfg.gee.collections.s2_cloud_score_plus
                if suffix == "cs"
                else cfg.gee.collections.s2_sr
            ),
            ee_image_id=scene.ee_image_id,
            acquisition_start=scene.acquisition_start,
            acquisition_end=scene.acquisition_end,
            orbit_or_tile=scene.orbit_or_tile,
            sun_zenith_deg=_as_float(scene.extra.get("MEAN_SOLAR_ZENITH_ANGLE")),
            sun_azimuth_deg=_as_float(scene.extra.get("MEAN_SOLAR_AZIMUTH_ANGLE")),
            bands=tuple(bands),
            crs=crs,
            scale_m=scale,
            aoi_name=cfg.aoi.name,
            aoi_kind=cfg.aoi.kind,
            value_type="observed",
            exported_at=datetime.now(tz=timezone.utc),
            run_id=run_id,
            config_hash=config_hash,
            notes=_notes(scene, suffix),
        )
        results.append(
            export_image(
                source_image,
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
    """List and export Sentinel-2 scenes for the configured AOI.

    ``limit`` defaults to ``acquisition.max_scenes_per_sensor``.
    """
    from config.loader import resolved_paths

    limit = cfg.acquisition.max_scenes_per_sensor if limit is None else limit
    out_dir = Path(out_dir) if out_dir else resolved_paths(cfg)["raw"] / "sentinel2"

    scenes = list_scenes(cfg, start=start, end=end, limit=limit)
    if not scenes:
        log.warning(
            "no Sentinel-2 scenes for %s in the requested window; nothing exported",
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


def _cloud_score_image(cfg: Config, scene: SceneRef) -> Any | None:
    """The Cloud Score+ image matching this Sentinel-2 scene, or ``None``.

    Cloud Score+ shares ``system:index`` with the Sentinel-2 scene it scores, so
    the two are joined on that rather than on time, which would be ambiguous
    where tiles overlap.
    """
    import ee

    index = scene.ee_image_id.rsplit("/", 1)[-1]
    matched = (
        ee.ImageCollection(cfg.gee.collections.s2_cloud_score_plus)
        .filter(ee.Filter.eq("system:index", index))
        .first()
    )
    try:
        if matched.getInfo() is None:
            return None
    except Exception as exc:  # noqa: BLE001 - absence is reported, not fatal
        log.debug("Cloud Score+ lookup failed for %s: %s", index, exc)
        return None
    return ee.Image(matched)


def _notes(scene: SceneRef, group: str) -> str:
    bits = [f"band group: {group}"]
    if scene.cloud_fraction is not None:
        bits.append(f"scene CLOUDY_PIXEL_PERCENTAGE: {scene.cloud_fraction:.1f}%")
    zenith = scene.extra.get("MEAN_SOLAR_ZENITH_ANGLE")
    azimuth = scene.extra.get("MEAN_SOLAR_AZIMUTH_ANGLE")
    if zenith is not None and azimuth is not None:
        bits.append(
            f"sun zenith {float(zenith):.3f} deg, azimuth {float(azimuth):.3f} deg"
        )
    baseline = scene.extra.get("PROCESSING_BASELINE")
    if baseline:
        bits.append(f"processing baseline {baseline}")
    return "; ".join(bits)


def _exclusive_end(end: date) -> str:
    """ee.filterDate's end is exclusive; shift by a day to include ``end``."""
    from datetime import timedelta

    return (end + timedelta(days=1)).isoformat()


def _as_float(value: Any) -> float | None:
    if value is None:
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None
