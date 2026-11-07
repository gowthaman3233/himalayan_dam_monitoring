"""Sentinel-1 GRD acquisition.

Collection: ``COPERNICUS/S1_GRD`` (verified 2026-10-03; over the default AOI it
carries both ASCENDING and DESCENDING passes on relative orbits 12, 85 and 121,
all IW mode -- see docs/methods.md 0.4).

Brief, Section 5: ascending and descending orbits are kept **separate** and the
orbit metadata is recorded. Scenes are therefore exported individually with
their pass direction and relative orbit in both the filename and the sidecar;
nothing here mixes geometries.

The ``angle`` band (per-pixel incidence angle) is always retained: the SAR
layover/shadow mask in Phase 2 cannot be computed without it (brief, Section
7.1).

Note on units: ``COPERNICUS/S1_GRD`` serves VV/VH already converted to
decibels, unlike ``COPERNICUS/S1_GRD_FLOAT`` which is linear power. The
observed value range is recorded in each sidecar so the units in use are never
in doubt downstream.
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

SENSOR = "Sentinel-1 C-SAR"
PROCESSING_LEVEL = "GRD"

#: Sentinel-1A began routine acquisition in October 2014. Coverage over any
#: particular area before ~2015 is sparse and must be checked, not assumed
#: (brief, Section 6, on the August 2014 Jure event).
S1_EPOCH_START = date(2014, 10, 3)

_SCENE_PROPERTIES = (
    "orbitProperties_pass",
    "relativeOrbitNumber_start",
    "instrumentMode",
    "platform_number",
    "transmitterReceiverPolarisation",
    "resolution_meters",
    "orbitNumber_start",
)


class Sentinel1Error(RuntimeError):
    """A Sentinel-1 request that cannot be satisfied."""


def list_scenes(
    cfg: Config,
    *,
    start: date | None = None,
    end: date | None = None,
    limit: int | None = None,
    orbit_pass: str | None = None,
) -> list[SceneRef]:
    """Sentinel-1 scenes intersecting the AOI, sorted oldest first.

    Filters to the configured instrument mode and to scenes carrying every
    configured polarisation band. ``orbit_pass`` overrides the configured
    ``acquisition.sentinel1.orbit_pass``; ``None`` in both keeps all passes.
    """
    import ee

    window = cfg.dates.query_window
    start = start or window.start
    end = end or window.end
    settings = cfg.acquisition.sentinel1

    # Validate the window before touching the network.
    if end < S1_EPOCH_START:
        raise Sentinel1Error(
            f"the requested window ends {end}, before Sentinel-1 acquisitions "
            f"begin ({S1_EPOCH_START})."
        )

    initialize(cfg)
    geometry = aoi_to_ee_geometry(cfg.aoi)
    collection = (
        ee.ImageCollection(cfg.gee.collections.s1_grd)
        .filterBounds(geometry)
        .filterDate(start.isoformat(), _exclusive_end(end))
        .filter(ee.Filter.eq("instrumentMode", settings.instrument_mode))
    )

    # Require every polarisation we intend to export, so a scene is never
    # exported with a silently missing band.
    for polarisation in (b for b in settings.bands if b in {"VV", "VH", "HH", "HV"}):
        collection = collection.filter(
            ee.Filter.listContains("transmitterReceiverPolarisation", polarisation)
        )

    effective_pass = orbit_pass if orbit_pass is not None else settings.orbit_pass
    if effective_pass is not None:
        collection = collection.filter(
            ee.Filter.eq("orbitProperties_pass", effective_pass)
        )

    collection = collection.sort("system:time_start")
    records = collection.toList(collection.size()).getInfo()

    scenes: list[SceneRef] = []
    for record in records:
        props = record.get("properties", {})
        pass_direction = props.get("orbitProperties_pass")
        relative_orbit = props.get("relativeOrbitNumber_start")
        scenes.append(
            SceneRef(
                ee_image_id=record["id"],
                acquisition_start=millis_to_datetime(props.get("system:time_start")),
                acquisition_end=millis_to_datetime(props.get("system:time_end")),
                # Brief, Section 5: orbit identity travels with the product.
                orbit_or_tile=_orbit_label(pass_direction, relative_orbit),
                platform=_platform(props.get("platform_number")),
                orbit_pass=pass_direction,
                relative_orbit=_as_int(relative_orbit),
                cloud_fraction=None,  # SAR is unaffected by cloud
                extra={
                    key: props.get(key)
                    for key in _SCENE_PROPERTIES
                    if props.get(key) is not None
                },
            )
        )

    by_pass: dict[str, int] = {}
    for scene in scenes:
        by_pass[scene.orbit_pass or "unknown"] = (
            by_pass.get(scene.orbit_pass or "unknown", 0) + 1
        )
    log.info(
        "Sentinel-1: %d scene(s) over %s, %s to %s (%s)",
        len(scenes),
        cfg.aoi.name,
        start,
        end,
        ", ".join(f"{k}: {v}" for k, v in sorted(by_pass.items())) or "none",
    )

    if limit is not None:
        scenes = scenes[:limit]
    return scenes


def list_scenes_by_pass(
    cfg: Config,
    *,
    start: date | None = None,
    end: date | None = None,
    limit_per_pass: int | None = None,
) -> dict[str, list[SceneRef]]:
    """Scenes grouped by orbit pass direction.

    Brief, Section 5: ascending and descending must stay separate. This is the
    grouping downstream code should consume rather than a mixed list, because
    backscatter from opposing look directions is not comparable in steep
    terrain.
    """
    grouped: dict[str, list[SceneRef]] = {}
    for scene in list_scenes(cfg, start=start, end=end):
        grouped.setdefault(scene.orbit_pass or "unknown", []).append(scene)
    if limit_per_pass is not None:
        grouped = {k: v[:limit_per_pass] for k, v in grouped.items()}
    return grouped


def export_scene(
    cfg: Config,
    scene: SceneRef,
    *,
    out_dir: Path,
    run_id: str | None = None,
    config_hash: str | None = None,
    overwrite: bool = False,
) -> list[tuple[Path, Path]]:
    """Export one Sentinel-1 scene as a single multi-band GeoTIFF.

    VV, VH and ``angle`` are all floating point, so unlike Sentinel-2 they can
    share one file without a dtype compromise.
    """
    from datetime import datetime, timezone

    import ee

    initialize(cfg)

    image = ee.Image(scene.ee_image_id)
    geometry = aoi_to_ee_geometry(cfg.aoi)
    crs = resolve_export_crs(cfg)
    scale = cfg.gee.default_scale_m
    bands = cfg.acquisition.sentinel1.bands

    name = f"S1_{scene.orbit_or_tile}_{scene.date_str}.tif"
    metadata = ProductMetadata(
        sensor=SENSOR,
        platform=scene.platform,
        processing_level=PROCESSING_LEVEL,
        source_collection=cfg.gee.collections.s1_grd,
        ee_image_id=scene.ee_image_id,
        acquisition_start=scene.acquisition_start,
        acquisition_end=scene.acquisition_end,
        orbit_or_tile=scene.orbit_or_tile,
        orbit_pass=scene.orbit_pass,
        relative_orbit=scene.relative_orbit,
        bands=tuple(bands),
        crs=crs,
        scale_m=scale,
        aoi_name=cfg.aoi.name,
        aoi_kind=cfg.aoi.kind,
        value_type="observed",
        exported_at=datetime.now(tz=timezone.utc),
        run_id=run_id,
        config_hash=config_hash,
        notes=_notes(scene),
    )

    return [
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
    ]


def export_scenes(
    cfg: Config,
    *,
    start: date | None = None,
    end: date | None = None,
    limit_per_pass: int | None = None,
    out_dir: Path | None = None,
    run_id: str | None = None,
    config_hash: str | None = None,
    overwrite: bool = False,
) -> list[tuple[Path, Path]]:
    """Export Sentinel-1 scenes, balanced across orbit passes.

    The per-pass limit defaults to ``acquisition.max_scenes_per_sensor``, applied
    to **each** pass direction, so a run never ends up with only one geometry.
    """
    from config.loader import resolved_paths

    if limit_per_pass is None:
        limit_per_pass = cfg.acquisition.max_scenes_per_sensor
    out_dir = Path(out_dir) if out_dir else resolved_paths(cfg)["raw"] / "sentinel1"

    grouped = list_scenes_by_pass(
        cfg, start=start, end=end, limit_per_pass=limit_per_pass
    )
    if not grouped:
        log.warning(
            "no Sentinel-1 scenes for %s in the requested window; nothing exported",
            cfg.aoi.name,
        )
        return []

    exported: list[tuple[Path, Path]] = []
    for pass_direction, scenes in sorted(grouped.items()):
        log.info("Sentinel-1 %s: exporting %d scene(s)", pass_direction, len(scenes))
        for scene in scenes:
            exported.extend(
                export_scene(
                    cfg,
                    scene,
                    out_dir=out_dir / pass_direction.lower(),
                    run_id=run_id,
                    config_hash=config_hash,
                    overwrite=overwrite,
                )
            )
    return exported


def _orbit_label(pass_direction: Any, relative_orbit: Any) -> str:
    direction = {"ASCENDING": "ASC", "DESCENDING": "DESC"}.get(
        str(pass_direction), "UNK"
    )
    orbit = _as_int(relative_orbit)
    return f"{direction}{orbit:03d}" if orbit is not None else direction


def _platform(number: Any) -> str | None:
    if not number:
        return None
    return f"Sentinel-1{number}"


def _notes(scene: SceneRef) -> str:
    bits = [
        "VV/VH served in decibels by COPERNICUS/S1_GRD "
        "(COPERNICUS/S1_GRD_FLOAT would be linear power)"
    ]
    mode = scene.extra.get("instrumentMode")
    if mode:
        bits.append(f"instrument mode {mode}")
    polarisations = scene.extra.get("transmitterReceiverPolarisation")
    if polarisations:
        bits.append(f"polarisations {'+'.join(polarisations)}")
    resolution = scene.extra.get("resolution_meters")
    if resolution:
        bits.append(f"native resolution {resolution} m")
    if scene.orbit_pass:
        bits.append(f"orbit pass {scene.orbit_pass}")
    if scene.relative_orbit is not None:
        bits.append(f"relative orbit {scene.relative_orbit}")
    return "; ".join(bits)


def _exclusive_end(end: date) -> str:
    from datetime import timedelta

    return (end + timedelta(days=1)).isoformat()


def _as_int(value: Any) -> int | None:
    if value is None:
        return None
    try:
        return int(value)
    except (TypeError, ValueError):
        return None
