"""Google Earth Engine session handling, AOI conversion and catalog probing.

Responsibilities:
  * initialise an Earth Engine session using the Cloud project ID taken from the
    environment (brief, Section 3: never hard-coded),
  * turn a validated AOI from the config into an ``ee.Geometry``,
  * probe the configured collection IDs and report what the catalog *actually*
    returns, rather than assuming the IDs and band names in the brief are
    current (brief, Section 5).

``ee`` is imported lazily throughout, so this module can be imported, and its
error messages tested, without the Earth Engine package or any credentials.
"""

from __future__ import annotations

from collections.abc import Sequence
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field

from config.schema import BBoxAOI, Config, GeoJSONAOI, PointBufferAOI
from utils.logging import get_logger

log = get_logger(__name__)

#: Shown whenever the project ID is missing, so the fix is always in reach.
SETUP_HINT = (
    "Earth Engine setup:\n"
    "  1. Register a Cloud project for Earth Engine (free for research/"
    "non-commercial use):\n"
    "       https://code.earthengine.google.com/register\n"
    "  2. Copy .env.example to .env and set GEE_PROJECT=<your-project-id>\n"
    "  3. Authenticate once on this machine (opens a browser):\n"
    "       earthengine authenticate\n"
)

#: Collections that carry no useful acquisition date to filter on. The GLO-30
#: DEM is a static mosaic of tiles, so date-filtering it would return nothing.
_UNDATED_COLLECTIONS = frozenset({"dem_glo30"})


class GEEError(RuntimeError):
    """Any Earth Engine problem surfaced by this module."""


class GEENotConfigured(GEEError):
    """The GEE project ID is absent, or no credentials are available."""


def gee_project_id(cfg: Config) -> str:
    """The Earth Engine Cloud project ID, read from the configured env var.

    Raises:
        GEENotConfigured: if the variable is unset or empty, with setup steps.
    """
    import os

    from config.loader import load_dotenv_if_present

    load_dotenv_if_present()

    var = cfg.gee.project_env_var
    value = (os.environ.get(var) or "").strip()
    if not value:
        raise GEENotConfigured(
            f"environment variable {var} is not set, so no Earth Engine project "
            f"is available.\n\n{SETUP_HINT}"
        )
    return value


def initialize(cfg: Config, *, force: bool = False) -> str:
    """Initialise an Earth Engine session. Returns the project ID used.

    Safe to call repeatedly: Earth Engine ignores a second initialisation unless
    ``force`` is set.

    Raises:
        GEENotConfigured: no project ID, or no stored credentials.
        GEEError: any other initialisation failure.
    """
    ee = _import_ee()
    project = gee_project_id(cfg)

    # ``ee.data._credentials`` is private, so read it defensively: if a future
    # version drops it we fall through and re-initialise, which is harmless.
    if not force and getattr(ee.data, "_credentials", None) is not None:
        return project

    try:
        ee.Initialize(project=project)
    except Exception as exc:
        message = str(exc)
        if "credential" in message.lower() or "authenticate" in message.lower():
            raise GEENotConfigured(
                f"Earth Engine credentials are missing or expired.\n\n{SETUP_HINT}\n"
                f"Underlying error: {message}"
            ) from exc
        raise GEEError(
            f"failed to initialise Earth Engine for project {project!r}: {message}"
        ) from exc

    log.info("Earth Engine initialised (project=%s)", project)
    return project


def is_available(cfg: Config) -> bool:
    """Whether a working Earth Engine session can be established.

    Never raises; intended for skipping tests that need live access.
    """
    try:
        initialize(cfg)
    except Exception as exc:  # noqa: BLE001 - deliberately broad: this is a probe
        log.debug("Earth Engine unavailable: %s", exc)
        return False
    return True


def unavailable_reason(cfg: Config) -> str | None:
    """``None`` if Earth Engine works, otherwise a human-readable reason."""
    try:
        initialize(cfg)
    except Exception as exc:  # noqa: BLE001 - deliberately broad: this is a probe
        return str(exc)
    return None


# --------------------------------------------------------------------------- #
# AOI conversion
# --------------------------------------------------------------------------- #


def aoi_to_ee_geometry(aoi: BBoxAOI | PointBufferAOI | GeoJSONAOI) -> Any:
    """Convert a validated AOI from the config into an ``ee.Geometry``.

    * ``bbox``    -> planar rectangle in EPSG:4326 (``geodesic=False``, so the
      edges are the straight lines the user drew, not great circles).
    * ``point``   -> geodesic buffer of ``buffer_m`` metres around the point.
    * ``geojson`` -> the file's geometry, dissolved to one shape if needed.
    """
    ee = _import_ee()

    if isinstance(aoi, BBoxAOI):
        return ee.Geometry.Rectangle(
            [aoi.west, aoi.south, aoi.east, aoi.north],
            proj="EPSG:4326",
            geodesic=False,
        )

    if isinstance(aoi, PointBufferAOI):
        return ee.Geometry.Point([aoi.lon, aoi.lat]).buffer(aoi.buffer_m)

    if isinstance(aoi, GeoJSONAOI):
        from utils.io import read_geojson_geometry

        return ee.Geometry(read_geojson_geometry(aoi.path))

    raise TypeError(f"unsupported AOI type: {type(aoi).__name__}")


def aoi_area_km2(geometry: Any, *, error_m: float = 1.0) -> float:
    """Server-side area of an ``ee.Geometry`` in km^2.

    Earth Engine computes this on the ellipsoid, so the result is in real metric
    units and does not depend on a local projection.
    """
    return float(geometry.area(error_m).divide(1e6).getInfo())


# --------------------------------------------------------------------------- #
# Catalog probe (Phase 0 gate check)
# --------------------------------------------------------------------------- #


def describe_collections(
    cfg: Config,
    *,
    start: date | None = None,
    end: date | None = None,
) -> dict[str, dict[str, Any]]:
    """Report what each configured collection actually returns for the AOI.

    This is the Phase 0 gate check and the standing verification required by the
    brief, Section 5. Nothing is assumed: for each configured ID it reports the
    image count, the real band names, the observed date range and, where
    relevant, the distinct Sentinel-1 orbit directions and Sentinel-2 tiles.

    Per-collection failures are captured in that entry's ``error`` field rather
    than aborting the probe, so one stale ID still leaves the rest verifiable.
    """
    initialize(cfg)
    ee = _import_ee()

    window = cfg.dates.query_window
    start = start or window.start
    end = end or window.end

    geometry = aoi_to_ee_geometry(cfg.aoi)
    results: dict[str, dict[str, Any]] = {
        "_aoi": {
            "name": cfg.aoi.name,
            "kind": cfg.aoi.kind,
            "area_km2": round(aoi_area_km2(geometry), 3),
            "date_filter": [start.isoformat(), end.isoformat()],
        }
    }

    for key in type(cfg.gee.collections).model_fields:
        collection_id = getattr(cfg.gee.collections, key)
        entry: dict[str, Any] = {"id": collection_id, "date_filtered": False}
        try:
            collection = ee.ImageCollection(collection_id).filterBounds(geometry)
            if key not in _UNDATED_COLLECTIONS:
                # ee.filterDate's end is EXCLUSIVE, so add a day to make the
                # configured end date inclusive, as a user would expect.
                collection = collection.filterDate(
                    start.isoformat(), (end + timedelta(days=1)).isoformat()
                )
                entry["date_filtered"] = True

            count = int(collection.size().getInfo())
            entry["image_count"] = count

            if count == 0:
                entry["note"] = (
                    "collection resolved, but no images intersect this AOI and "
                    "date window"
                )
            else:
                entry.update(_summarise(ee, collection, key, count))

        except Exception as exc:  # noqa: BLE001 - reported, not swallowed
            entry["error"] = f"{type(exc).__name__}: {exc}"

        results[key] = entry

    return results


def _summarise(
    ee: Any, collection: Any, key: str, count: int
) -> dict[str, Any]:
    """Band names, observed date range and sensor-specific metadata."""
    out: dict[str, Any] = {}

    sorted_by_time = collection.sort("system:time_start")
    out["band_names"] = list(sorted_by_time.first().bandNames().getInfo())

    stats = collection.aggregate_array("system:time_start").getInfo() or []
    epochs = [t for t in stats if t]
    if epochs:
        out["first_acquisition"] = _iso(ee, min(epochs))
        out["last_acquisition"] = _iso(ee, max(epochs))

    if key == "s1_grd":
        # Brief, Section 5: ascending and descending orbits must stay separate,
        # so record what the AOI actually has.
        out["orbit_directions"] = sorted(
            set(collection.aggregate_array("orbitProperties_pass").getInfo() or [])
        )
        out["relative_orbits"] = sorted(
            set(collection.aggregate_array("relativeOrbitNumber_start").getInfo() or [])
        )
        out["instrument_modes"] = sorted(
            set(collection.aggregate_array("instrumentMode").getInfo() or [])
        )
    elif key == "s2_sr":
        out["mgrs_tiles"] = sorted(
            set(collection.aggregate_array("MGRS_TILE").getInfo() or [])
        )
        # Solar angles are read from image properties (brief, Section 7.1); check
        # they are present, because the terrain-shadow mask depends on them.
        first = collection.sort("system:time_start").first()
        out["solar_angles_first_image"] = {
            "MEAN_SOLAR_ZENITH_ANGLE": first.get("MEAN_SOLAR_ZENITH_ANGLE").getInfo(),
            "MEAN_SOLAR_AZIMUTH_ANGLE": first.get("MEAN_SOLAR_AZIMUTH_ANGLE").getInfo(),
        }

    out["sampled_images"] = count
    return out


def _iso(ee: Any, millis: int) -> str:
    return str(ee.Date(millis).format("YYYY-MM-dd'T'HH:mm:ss").getInfo())


# --------------------------------------------------------------------------- #
# Product metadata (brief, Section 5)
# --------------------------------------------------------------------------- #


class SceneRef(BaseModel):
    """One scene found in the catalog, before anything is downloaded.

    Listing is kept separate from exporting so a run can report what coverage
    exists -- and how cloudy it is -- without pulling any pixels.
    """

    model_config = ConfigDict(extra="forbid")

    ee_image_id: str
    acquisition_start: datetime | None = None
    acquisition_end: datetime | None = None
    orbit_or_tile: str
    platform: str | None = None
    orbit_pass: str | None = None
    relative_orbit: int | None = None
    cloud_fraction: float | None = Field(
        default=None,
        description="Scene-level cloud percentage as reported by the provider, 0-100.",
    )
    extra: dict[str, Any] = Field(default_factory=dict)

    @property
    def date_str(self) -> str:
        """``YYYYmmddTHHMMSS`` for filenames, or 'undated'."""
        if self.acquisition_start is None:
            return "undated"
        return self.acquisition_start.strftime("%Y%m%dT%H%M%S")


class ProductMetadata(BaseModel):
    """Provenance carried by every exported product.

    Brief, Section 5: "Every product the system stores must carry: sensor,
    acquisition date(s), orbit/tile, processing level, and source collection."
    Written alongside each GeoTIFF as a ``.json`` sidecar, and embedded in the
    GeoTIFF's own tags where the driver allows it.
    """

    model_config = ConfigDict(extra="forbid")

    # --- what the data is -------------------------------------------------- #
    sensor: str = Field(description="e.g. 'Sentinel-2 MSI', 'Sentinel-1 C-SAR'.")
    platform: str | None = Field(
        default=None, description="e.g. 'Sentinel-2A', 'LANDSAT_8'."
    )
    processing_level: str = Field(description="e.g. 'L2A', 'GRD', 'C2 L2', 'DSM'.")
    source_collection: str = Field(description="Earth Engine collection ID.")
    ee_image_id: str | None = Field(
        default=None, description="Earth Engine asset ID of the source image."
    )

    # --- when ------------------------------------------------------------- #
    acquisition_start: datetime | None = None
    acquisition_end: datetime | None = None

    # --- where / which pass ------------------------------------------------ #
    orbit_or_tile: str = Field(
        description=(
            "MGRS tile for S2, orbit direction + relative orbit for S1, "
            "WRS path/row for Landsat, tile_version for the DEM."
        )
    )
    orbit_pass: str | None = None
    relative_orbit: int | None = None

    # --- illumination geometry -------------------------------------------- #
    # Required per scene by the terrain-shadow mask (brief, Section 7.1).
    # Structured fields rather than free text so Phase 2 can consume them
    # without parsing prose.
    sun_zenith_deg: float | None = Field(default=None, ge=0.0, le=180.0)
    sun_azimuth_deg: float | None = Field(default=None, ge=0.0, le=360.0)
    #: SAR incidence angle against the ellipsoid, where it is a scene constant.
    incidence_angle_deg: float | None = Field(default=None, ge=0.0, le=90.0)

    # --- the exported raster ---------------------------------------------- #
    bands: tuple[str, ...]
    crs: str
    scale_m: float
    width: int | None = None
    height: int | None = None
    bounds: tuple[float, float, float, float] | None = None
    dtype: str | None = None
    nodata: float | None = None

    # --- provenance of this run ------------------------------------------- #
    aoi_name: str
    aoi_kind: str
    value_type: Literal[
        "observed", "classified", "estimated", "empirical", "derived", "unavailable"
    ] = Field(
        default="observed",
        description=(
            "Brief, Section 10. Raw satellite imagery is 'observed'; anything "
            "the pipeline computes from it is not."
        ),
    )
    exported_at: datetime
    run_id: str | None = None
    config_hash: str | None = None
    notes: str | None = None

    def sidecar_path(self, raster_path: Path) -> Path:
        return raster_path.with_suffix(raster_path.suffix + ".json")

    def write_sidecar(self, raster_path: Path) -> Path:
        from utils.io import write_json

        target = self.sidecar_path(raster_path)
        write_json(self.model_dump(mode="json"), target)
        return target


# --------------------------------------------------------------------------- #
# Export
# --------------------------------------------------------------------------- #


def resolve_export_crs(cfg: Config) -> str:
    """The CRS to export in.

    ``acquisition.export_crs: auto`` derives the UTM zone from the AOI centroid
    (brief, Section 6: the projection is never assumed). For a GeoJSON AOI the
    centroid is read from the file.
    """
    configured = cfg.acquisition.export_crs
    if configured != "auto":
        return configured

    from utils.crs import utm_epsg_for_centroid

    centroid = cfg.aoi_centroid
    if centroid is None:
        from utils.io import geojson_centroid, read_geojson_geometry

        centroid = geojson_centroid(read_geojson_geometry(cfg.aoi.path))

    return f"EPSG:{utm_epsg_for_centroid(centroid)}"


def estimate_export_bytes(
    area_m2: float, scale_m: float, n_bands: int, bytes_per_pixel: int = 4
) -> int:
    """Rough size of an export, for the pre-flight guard.

    Deliberately an over-estimate: it assumes 4 bytes per band per pixel and a
    square region, so it errs towards refusing early rather than failing
    mid-download.
    """
    pixels = area_m2 / (scale_m**2)
    return int(pixels * n_bands * bytes_per_pixel)


def export_image(
    image: Any,
    *,
    region: Any,
    out_path: Path,
    bands: Sequence[str],
    crs: str,
    scale_m: float,
    metadata: ProductMetadata,
    cfg: Config,
    overwrite: bool = False,
) -> tuple[Path, Path]:
    """Download one Earth Engine image as a GeoTIFF, plus its metadata sidecar.

    Returns ``(raster_path, sidecar_path)``. The raster is opened with rasterio
    after download, and the real width/height/bounds/dtype are written into the
    sidecar -- so the recorded metadata describes the file on disk rather than
    what was requested.

    Raises:
        GEEError: if the request exceeds ``gee.max_request_pixels`` or the
            estimated size exceeds ``acquisition.max_export_bytes``, or the
            download or the readback fails.
    """
    from utils.io import ensure_parent

    out_path = Path(out_path)
    if out_path.exists() and not overwrite:
        log.info("export exists, skipping: %s", out_path.name)
        return out_path, metadata.sidecar_path(out_path)

    area_m2 = float(region.area(1).getInfo())

    # Pixel-count guard. `gee.max_request_pixels` is documented as refusing a
    # request above this size "so a mistyped AOI cannot try to pull a full
    # Sentinel scene onto a laptop" -- but nothing read it, so that protection
    # did not exist. It is a different limit from max_export_bytes: pixel
    # count is what getDownloadURL itself caps, and a single-band request can
    # sit under the byte limit while still being refused by the server.
    requested_pixels = int(area_m2 / (scale_m**2))
    if requested_pixels > cfg.gee.max_request_pixels:
        raise GEEError(
            f"export refused: {requested_pixels:,} pixel(s) at {scale_m} m over "
            f"{area_m2 / 1e6:.1f} km^2 exceeds gee.max_request_pixels "
            f"({cfg.gee.max_request_pixels:,}). Reduce the AOI or raise the "
            f"scale."
        )

    estimated = estimate_export_bytes(area_m2, scale_m, len(bands))
    if estimated > cfg.acquisition.max_export_bytes:
        raise GEEError(
            f"export refused: estimated {estimated / 1e6:.1f} MB for "
            f"{len(bands)} band(s) at {scale_m} m over {area_m2 / 1e6:.1f} km^2 "
            f"exceeds acquisition.max_export_bytes "
            f"({cfg.acquisition.max_export_bytes / 1e6:.1f} MB). Reduce the AOI, "
            f"raise the scale, or export fewer bands per file."
        )

    params = {
        "bands": list(bands),
        "region": region,
        "scale": scale_m,
        "crs": crs,
        "format": "GEO_TIFF",
        "filePerBand": False,
    }

    try:
        url = image.select(list(bands)).getDownloadURL(params)
    except Exception as exc:
        raise GEEError(f"could not build a download URL for {out_path.name}: {exc}") from exc

    ensure_parent(out_path)
    _download(url, out_path)

    raster_facts = _describe_raster(out_path)
    enriched = metadata.model_copy(update=raster_facts)
    sidecar = enriched.write_sidecar(out_path)
    _embed_tags(out_path, enriched)

    log.info(
        "exported %s (%dx%d, %s, %s)",
        out_path.name,
        raster_facts["width"],
        raster_facts["height"],
        raster_facts["dtype"],
        raster_facts["crs"],
    )
    return out_path, sidecar


def _download(url: str, out_path: Path) -> None:
    import requests

    try:
        with requests.get(url, stream=True, timeout=600) as response:
            response.raise_for_status()
            with out_path.open("wb") as fh:
                for chunk in response.iter_content(chunk_size=1 << 20):
                    if chunk:
                        fh.write(chunk)
    except Exception as exc:
        out_path.unlink(missing_ok=True)
        raise GEEError(f"download failed for {out_path.name}: {exc}") from exc

    if out_path.stat().st_size == 0:
        out_path.unlink(missing_ok=True)
        raise GEEError(f"download produced an empty file: {out_path.name}")


def _describe_raster(path: Path) -> dict[str, Any]:
    """Read back the downloaded file so the metadata matches reality."""
    import rasterio

    try:
        with rasterio.open(path) as src:
            return {
                "width": src.width,
                "height": src.height,
                "bounds": tuple(float(v) for v in src.bounds),
                "dtype": str(src.dtypes[0]),
                "crs": str(src.crs),
                "nodata": None if src.nodata is None else float(src.nodata),
            }
    except Exception as exc:
        raise GEEError(
            f"downloaded file is not a readable raster: {path.name}: {exc}"
        ) from exc


def _embed_tags(path: Path, metadata: ProductMetadata) -> None:
    """Write key provenance into the GeoTIFF's own tags.

    The sidecar is authoritative; these tags mean the essentials survive if the
    raster is moved without its sidecar (for example dragged into QGIS).
    """
    import rasterio

    tags = {
        "HDM_SENSOR": metadata.sensor,
        "HDM_PROCESSING_LEVEL": metadata.processing_level,
        "HDM_SOURCE_COLLECTION": metadata.source_collection,
        "HDM_ORBIT_OR_TILE": metadata.orbit_or_tile,
        "HDM_VALUE_TYPE": metadata.value_type,
        "HDM_BANDS": ",".join(metadata.bands),
    }
    if metadata.acquisition_start:
        tags["HDM_ACQUISITION_START"] = metadata.acquisition_start.isoformat()
    if metadata.ee_image_id:
        tags["HDM_EE_IMAGE_ID"] = metadata.ee_image_id

    try:
        with rasterio.open(path, "r+") as dst:
            dst.update_tags(**tags)
            for index, name in enumerate(metadata.bands, start=1):
                dst.set_band_description(index, name)
    except Exception as exc:  # noqa: BLE001 - the sidecar is authoritative
        log.warning("could not embed tags in %s: %s", path.name, exc)


def millis_to_datetime(millis: int | float | None) -> datetime | None:
    """Earth Engine epoch milliseconds (UTC) to a timezone-aware datetime."""
    if millis is None:
        return None
    return datetime.fromtimestamp(float(millis) / 1000.0, tz=timezone.utc)


def _import_ee() -> Any:
    try:
        import ee
    except ImportError as exc:  # pragma: no cover - environment problem
        raise GEEError(
            "the earthengine-api package is not installed; create the conda "
            "environment with `conda env create -f environment.yml`"
        ) from exc
    return ee
