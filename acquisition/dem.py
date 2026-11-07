"""Copernicus GLO-30 DEM acquisition.

Collection: ``COPERNICUS/DEM/GLO30_2024_1``. The brief names
``COPERNICUS/DEM/GLO30``, but Earth Engine has deprecated it, and the switch is
material rather than cosmetic -- see docs/methods.md 0.6. The deprecated
collection exposes only a placeholder acquisition date (2006-01-01), whereas the
replacement carries real per-tile acquisition windows.

That matters because **the DEM acquisition date is the hinge of the Branch A /
Branch B depth decision** (brief, Section 8):

* **Branch A** -- the lake formed *after* the DEM was acquired, so the DEM shows
  the pre-lake valley floor and a depth can be estimated.
* **Branch B** -- the lake already existed, so the DEM recorded its water
  surface and the bed is unknown; depth must be reported ``unavailable``.

:func:`acquisition_epoch` makes that hinge a **measured, per-AOI value** read
from the catalog, rather than the assumed "about 2015" constant. Phase 10 must
consume it from here and never hard-code a date.

Bands: ``DEM`` (orthometric height above EGM2008), ``EDM`` (edit mask), ``FLM``
(fill mask), ``HEM`` (height error mask -- feeds depth uncertainty), ``WBM``
(water body mask).
"""

from __future__ import annotations

from datetime import date, datetime
from pathlib import Path
from typing import Any

from pydantic import BaseModel, ConfigDict, Field

from acquisition.gee_client import (
    ProductMetadata,
    aoi_to_ee_geometry,
    export_image,
    initialize,
    millis_to_datetime,
    resolve_export_crs,
)
from config.schema import Config
from utils.logging import get_logger

log = get_logger(__name__)

SENSOR = "Copernicus DEM GLO-30 (TanDEM-X derived)"
PROCESSING_LEVEL = "DSM"

#: Vertical datum of the DEM band, per the Earth Engine catalog entry.
VERTICAL_DATUM = "EGM2008 orthometric height"

#: Catalog-stated global acquisition span of GLO30_2024_1. The per-AOI span is
#: narrower and is what :func:`acquisition_epoch` measures.
GLOBAL_EPOCH_START = date(2010, 12, 1)
GLOBAL_EPOCH_END = date(2020, 11, 13)


class DEMError(RuntimeError):
    """A DEM request that cannot be satisfied."""


class DEMEpoch(BaseModel):
    """When the DEM covering an AOI was actually acquired.

    This is the authoritative input to the Branch A / Branch B decision in
    Phase 10. It is measured from the catalog, never assumed.
    """

    model_config = ConfigDict(extra="forbid")

    source_collection: str
    aoi_name: str
    earliest_acquisition: datetime
    latest_acquisition: datetime
    distinct_start_dates: tuple[str, ...]
    distinct_end_dates: tuple[str, ...]
    tile_versions_present: tuple[str, ...]
    tile_version_selected: str | None
    entries_intersecting_aoi: int
    entries_selected: int
    value_type: str = Field(
        default="observed",
        description="Read from catalog metadata, so observed rather than derived.",
    )

    @property
    def branch_hinge_date(self) -> date:
        """The date a lake must post-date to qualify for Branch A.

        Deliberately the **latest** acquisition over the AOI, which is the
        conservative choice: if any part of the DEM footprint could have seen
        the lake, the DEM may already record its water surface, and claiming
        Branch A would risk fabricating a depth. Ambiguity resolves towards
        ``unavailable``, per the brief, Section 8.
        """
        return self.latest_acquisition.date()

    def branch_for_lake(self, first_observed: date) -> str:
        """``"A"`` or ``"B"`` for a lake first observed on ``first_observed``.

        Returns the branch letter only; Phase 10 owns the actual depth logic
        and the Branch C (insufficient data) case.
        """
        return "A" if first_observed > self.branch_hinge_date else "B"

    def summary(self) -> str:
        return (
            f"DEM epoch over {self.aoi_name}: "
            f"{self.earliest_acquisition.date()} to {self.latest_acquisition.date()} "
            f"(Branch A requires a lake first observed after "
            f"{self.branch_hinge_date}); "
            f"{self.entries_selected}/{self.entries_intersecting_aoi} entries, "
            f"tile_version {self.tile_version_selected} "
            f"of {list(self.tile_versions_present)}"
        )


def _filtered_collection(cfg: Config) -> tuple[Any, dict[str, Any]]:
    """The DEM entries intersecting the AOI, plus the tile-version facts.

    GLO30_2024_1 returns many heavily **overlapping** 1-degree tiles for a small
    AOI (361 entries of ~10,980 km2 each over the default 49.7 km2 AOI), in more
    than one ``tile_version``. Mosaicking that directly would blend versions
    non-deterministically, so a single version is selected first.
    """
    import ee

    initialize(cfg)

    geometry = aoi_to_ee_geometry(cfg.aoi)
    collection = ee.ImageCollection(cfg.gee.collections.dem_glo30).filterBounds(
        geometry
    )

    versions = collection.aggregate_array("tile_version").getInfo() or []
    present = sorted({str(v) for v in versions})
    total = int(collection.size().getInfo())

    if total == 0:
        raise DEMError(
            f"no DEM tiles intersect the AOI {cfg.aoi.name!r} in "
            f"{cfg.gee.collections.dem_glo30}"
        )

    selected_version: str | None = None
    if present:
        policy = cfg.acquisition.dem.tile_version_policy
        selected_version = max(present) if policy == "highest" else min(present)
        collection = collection.filter(
            ee.Filter.eq("tile_version", selected_version)
        )

    facts = {
        "tile_versions_present": tuple(present),
        "tile_version_selected": selected_version,
        "entries_intersecting_aoi": total,
        "entries_selected": int(collection.size().getInfo()),
        "geometry": geometry,
    }
    return collection, facts


def acquisition_epoch(cfg: Config) -> DEMEpoch:
    """Measure when the DEM covering the AOI was acquired.

    This is the Branch A / Branch B hinge for Phase 10. Nothing downstream may
    substitute an assumed date for this value.

    Raises:
        DEMError: if no tiles cover the AOI, or none carry usable dates.
    """
    collection, facts = _filtered_collection(cfg)

    starts = [
        t for t in (collection.aggregate_array("system:time_start").getInfo() or []) if t
    ]
    ends = [
        t for t in (collection.aggregate_array("system:time_end").getInfo() or []) if t
    ]
    if not starts or not ends:
        raise DEMError(
            f"{cfg.gee.collections.dem_glo30} returned no acquisition dates for "
            f"{cfg.aoi.name!r}. The deprecated COPERNICUS/DEM/GLO30 has this "
            f"problem by design (placeholder dates only); a Branch A/B decision "
            f"cannot be made from it. See docs/methods.md 0.6."
        )

    earliest = millis_to_datetime(min(starts))
    latest = millis_to_datetime(max(ends))
    assert earliest is not None and latest is not None  # guarded above

    epoch = DEMEpoch(
        source_collection=cfg.gee.collections.dem_glo30,
        aoi_name=cfg.aoi.name,
        earliest_acquisition=earliest,
        latest_acquisition=latest,
        distinct_start_dates=tuple(
            sorted({millis_to_datetime(t).date().isoformat() for t in starts})  # type: ignore[union-attr]
        ),
        distinct_end_dates=tuple(
            sorted({millis_to_datetime(t).date().isoformat() for t in ends})  # type: ignore[union-attr]
        ),
        tile_versions_present=facts["tile_versions_present"],
        tile_version_selected=facts["tile_version_selected"],
        entries_intersecting_aoi=facts["entries_intersecting_aoi"],
        entries_selected=facts["entries_selected"],
    )
    log.info("%s", epoch.summary())
    return epoch


def export_dem(
    cfg: Config,
    *,
    out_dir: Path | None = None,
    run_id: str | None = None,
    config_hash: str | None = None,
    overwrite: bool = False,
) -> tuple[list[tuple[Path, Path]], DEMEpoch]:
    """Export the DEM mosaic over the AOI, plus the measured acquisition epoch.

    Returns ``([(raster, sidecar)], epoch)``. The epoch is also written to
    ``<out_dir>/dem_epoch.json`` so Phase 10 can read it without a network call.
    """
    from datetime import timezone

    from config.loader import resolved_paths
    from utils.io import write_json

    out_dir = Path(out_dir) if out_dir else resolved_paths(cfg)["raw"] / "dem"

    collection, facts = _filtered_collection(cfg)
    epoch = acquisition_epoch(cfg)

    # Deterministic mosaic: one tile version only, ordered by acquisition time
    # so that later data wins where the selected tiles still overlap.
    mosaic = collection.sort("system:time_start").mosaic()

    crs = resolve_export_crs(cfg)
    scale = cfg.gee.default_scale_m
    bands = cfg.acquisition.dem.bands

    version_tag = facts["tile_version_selected"] or "v0"
    name = f"DEM_GLO30_v{version_tag}_{crs.replace(':', '')}.tif"

    metadata = ProductMetadata(
        sensor=SENSOR,
        platform=None,
        processing_level=PROCESSING_LEVEL,
        source_collection=cfg.gee.collections.dem_glo30,
        ee_image_id=None,  # a mosaic has no single source image
        acquisition_start=epoch.earliest_acquisition,
        acquisition_end=epoch.latest_acquisition,
        orbit_or_tile=f"tile_version={version_tag}",
        bands=tuple(bands),
        crs=crs,
        scale_m=scale,
        aoi_name=cfg.aoi.name,
        aoi_kind=cfg.aoi.kind,
        value_type="observed",
        exported_at=datetime.now(tz=timezone.utc),
        run_id=run_id,
        config_hash=config_hash,
        notes=(
            f"mosaic of {epoch.entries_selected} entries at tile_version "
            f"{version_tag} (of {list(epoch.tile_versions_present)}), "
            f"sorted by acquisition time so later data wins on overlap; "
            f"{VERTICAL_DATUM}; native 30 m resampled to the "
            f"{scale:.0f} m project grid, which adds no real detail; "
            f"Branch A/B hinge date {epoch.branch_hinge_date} "
            f"(brief, Section 8)"
        ),
    )

    exported = export_image(
        mosaic,
        region=facts["geometry"],
        out_path=Path(out_dir) / name,
        bands=bands,
        crs=crs,
        scale_m=scale,
        metadata=metadata,
        cfg=cfg,
        overwrite=overwrite,
    )

    epoch_path = Path(out_dir) / "dem_epoch.json"
    write_json(epoch.model_dump(mode="json"), epoch_path)
    log.info("DEM epoch written to %s", epoch_path)

    return [exported], epoch


def load_epoch(path: str | Path) -> DEMEpoch:
    """Read a previously exported :class:`DEMEpoch` from disk."""
    from utils.io import read_json

    return DEMEpoch.model_validate(read_json(path))
