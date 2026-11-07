"""Flow routing and stream-network extraction with WhiteboxTools.

Brief, Section 7.1: DEM derivatives include flow direction, flow accumulation
and a stream network. Section 5: the stream network is derived from the DEM with
WhiteboxTools, optionally cross-checked against HydroSHEDS/HydroRIVERS.

The stream network is what Phase 7 tests a landslide against to decide whether a
river may be blocked, so its density is a consequential choice rather than a
cosmetic one. It is driven entirely by
``preprocessing.hydrology.stream_threshold_cells``, and the resulting channel
length is reported so the effect of that choice is visible.

Depression handling defaults to **breaching** rather than filling. Filling
raises every pit to its spill level, which in steep terrain can flood real
valley floors and shift channels; breaching cuts a narrow outlet instead and
preserves the drainage pattern. Both are available via config.

WhiteboxTools downloads its own binary on first use and runs as an external
executable on files, so this module works through GeoTIFFs on disk rather than
in-memory arrays.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

import numpy as np

from config.schema import Config
from utils.logging import get_logger

log = get_logger(__name__)


class HydrologyError(RuntimeError):
    """A WhiteboxTools step that did not produce its expected output."""


@dataclass(frozen=True)
class HydrologyProducts:
    """Paths to the rasters produced by :func:`derive_stream_network`."""

    conditioned_dem: Path
    flow_direction: Path
    flow_accumulation: Path
    streams: Path
    stream_threshold_cells: int
    depression_handling: str

    def as_dict(self) -> dict[str, str]:
        return {
            "conditioned_dem": str(self.conditioned_dem),
            "flow_direction": str(self.flow_direction),
            "flow_accumulation": str(self.flow_accumulation),
            "streams": str(self.streams),
            "stream_threshold_cells": str(self.stream_threshold_cells),
            "depression_handling": self.depression_handling,
        }


def _tools(working_dir: Path):
    """A configured WhiteboxTools instance.

    Verbose output is suppressed: the tools print progress to stdout, which
    would drown the project's own logging.
    """
    try:
        import whitebox
    except ImportError as exc:  # pragma: no cover - environment problem
        raise HydrologyError(
            "the whitebox package is not installed; add it with "
            "`conda install -c conda-forge whitebox`"
        ) from exc

    wbt = whitebox.WhiteboxTools()
    wbt.set_working_dir(str(working_dir))
    wbt.set_verbose_mode(False)
    return wbt


#: Band holding orthometric height in a Copernicus GLO-30 product. The
#: collection ships DEM, EDM, FLM, HEM and WBM bands (see
#: :mod:`acquisition.dem`), and only the first is an elevation surface.
#: One-based, matching rasterio's band indexing.
ELEVATION_BAND = 1

#: GeoTIFF compression schemes the WhiteboxTools decoder accepts. Taken from
#: its own failure message: "The WhiteboxTools GeoTIFF decoder currently only
#: supports PACKBITS, LZW, and DEFLATE compression." Earth Engine exports use
#: DEFLATE, which is nominally on that list, yet the decoder still rejects the
#: multi-band exports this project produces -- so a copy is written whenever
#: the input is not already a plain single-band raster, rather than trusting
#: the list.
WHITEBOX_COMPRESSION = ("lzw", "packbits", "deflate", None)


def _whitebox_readable_dem(dem_path: Path, out_dir: Path, prefix: str) -> Path:
    """A single-band elevation GeoTIFF WhiteboxTools can actually read.

    WhiteboxTools runs as an external executable over files and expects a
    plain single-band elevation raster. The project's own DEM acquisition
    emits a **multi-band** GLO-30 product (DEM, HEM, WBM), which the tool's
    GeoTIFF decoder rejects outright -- it fails while reading, produces no
    output, and says only that the compression is unsupported.

    So when the input is not already single-band, band
    :data:`ELEVATION_BAND` is written out as an LZW-compressed single-band
    copy and that copy is used. A single-band input is passed through
    untouched, so nothing is rewritten needlessly.

    Returns:
        The path to pass to WhiteboxTools -- either the input or the copy.
    """
    import rasterio

    with rasterio.open(dem_path) as src:
        if src.count == 1:
            return dem_path
        descriptions = src.descriptions
        profile = src.profile.copy()
        elevation = src.read(ELEVATION_BAND)
        nodata = src.nodatavals[ELEVATION_BAND - 1]

    band_name = (
        descriptions[ELEVATION_BAND - 1]
        if descriptions and descriptions[ELEVATION_BAND - 1]
        else f"band {ELEVATION_BAND}"
    )
    profile.update(count=1, compress="lzw", predictor=1, tiled=False)
    if nodata is not None:
        profile.update(nodata=nodata)

    single = out_dir / f"{prefix}_elevation.tif"
    with rasterio.open(single, "w", **profile) as dst:
        dst.write(elevation, 1)
        dst.set_band_description(1, band_name)

    log.info(
        "DEM %s has %d bands; wrote single-band elevation (%s) to %s for "
        "WhiteboxTools",
        dem_path.name,
        len(descriptions) if descriptions else 0,
        band_name,
        single.name,
    )
    return single


def derive_stream_network(
    dem_path: str | Path,
    cfg: Config,
    *,
    out_dir: str | Path | None = None,
    prefix: str = "hydro",
) -> HydrologyProducts:
    """Condition a DEM and extract flow direction, accumulation and streams.

    Steps, in order:

    1. **condition** the DEM (breach or fill depressions) so flow can route;
    2. **D8 flow pointer** -- steepest-descent direction per cell;
    3. **D8 flow accumulation** -- contributing cells per cell;
    4. **threshold** the accumulation to extract channels.

    Args:
        dem_path: a single-band DEM GeoTIFF in a projected CRS.
        out_dir: defaults to the DEM's own directory.

    Returns:
        :class:`HydrologyProducts` with the path to each raster.
    """
    dem_path = Path(dem_path).resolve()
    if not dem_path.is_file():
        raise HydrologyError(f"DEM not found: {dem_path}")

    out_dir = Path(out_dir).resolve() if out_dir else dem_path.parent
    out_dir.mkdir(parents=True, exist_ok=True)

    settings = cfg.preprocessing.hydrology
    wbt = _tools(out_dir)

    conditioned = out_dir / f"{prefix}_conditioned.tif"
    pointer = out_dir / f"{prefix}_d8_pointer.tif"
    accumulation = out_dir / f"{prefix}_d8_accumulation.tif"
    streams = out_dir / f"{prefix}_streams.tif"

    source = str(_whitebox_readable_dem(dem_path, out_dir, prefix))

    # --- 1. condition ------------------------------------------------------ #
    if settings.depression_handling == "breach":
        log.info("conditioning DEM by breaching depressions")
        wbt.breach_depressions_least_cost(
            dem=source, output=str(conditioned), dist=100, fill=True
        )
    elif settings.depression_handling == "fill":
        log.info("conditioning DEM by filling depressions")
        wbt.fill_depressions(dem=source, output=str(conditioned))
    else:
        log.warning(
            "depression_handling is 'none'; flow routing may terminate in pits "
            "and the stream network will be incomplete"
        )
        import shutil

        shutil.copyfile(source, conditioned)

    _require(conditioned, "conditioned DEM")

    # --- 2. flow direction ------------------------------------------------- #
    wbt.d8_pointer(dem=str(conditioned), output=str(pointer))
    _require(pointer, "D8 flow pointer")

    # --- 3. flow accumulation ---------------------------------------------- #
    # out_type "cells" so the threshold below is in contributing cells, which is
    # what the config states and what makes the units auditable.
    wbt.d8_flow_accumulation(
        i=str(conditioned), output=str(accumulation), out_type="cells"
    )
    _require(accumulation, "D8 flow accumulation")

    # --- 4. streams --------------------------------------------------------- #
    wbt.extract_streams(
        flow_accum=str(accumulation),
        output=str(streams),
        threshold=settings.stream_threshold_cells,
    )
    _require(streams, "stream network")

    products = HydrologyProducts(
        conditioned_dem=conditioned,
        flow_direction=pointer,
        flow_accumulation=accumulation,
        streams=streams,
        stream_threshold_cells=settings.stream_threshold_cells,
        depression_handling=settings.depression_handling,
    )
    log.info(
        "stream network extracted at threshold %d cells: %s",
        settings.stream_threshold_cells,
        streams.name,
    )
    return products


def stream_statistics(
    streams_path: str | Path, cellsize: float
) -> dict[str, float]:
    """Channel density for the extracted network.

    Reported so the consequences of ``stream_threshold_cells`` are visible
    rather than implicit: too low a threshold invents channels on hillslopes,
    too high a one misses the tributaries a landslide might dam.
    """
    import rasterio

    with rasterio.open(streams_path) as src:
        data = src.read(1, masked=True)
        rows, cols = src.height, src.width

    stream_cells = int((data > 0).filled(False).sum())
    total_cells = rows * cols
    area_km2 = total_cells * cellsize**2 / 1e6

    # One cell of channel contributes roughly one cellsize of length. This is an
    # approximation: diagonal runs are longer by sqrt(2), so it slightly
    # under-reports. Stated rather than silently assumed.
    length_km = stream_cells * cellsize / 1000.0

    return {
        "stream_cells": float(stream_cells),
        "stream_fraction": float(stream_cells / total_cells) if total_cells else 0.0,
        "approx_channel_length_km": length_km,
        "raster_area_km2": area_km2,
        "drainage_density_km_per_km2": length_km / area_km2 if area_km2 else 0.0,
    }


def read_stream_mask(streams_path: str | Path) -> np.ndarray:
    """The stream network as a boolean mask."""
    import rasterio

    with rasterio.open(streams_path) as src:
        data = src.read(1, masked=True)
    return (data > 0).filled(False)


def _require(path: Path, what: str) -> None:
    """Fail loudly when a WhiteboxTools step wrote nothing.

    The tool reports failure on stdout and still exits 0, so a missing output
    file is the only reliable signal. The message lists the causes actually
    seen in this project rather than guessing, because the original wording
    blamed the CRS for what turned out to be a multi-band input.
    """
    if not path.is_file() or path.stat().st_size == 0:
        raise HydrologyError(
            f"WhiteboxTools did not produce the {what} at {path}. It reports "
            f"read failures on stdout and still exits 0, so check its output "
            f"above. Causes seen here: a multi-band input (GLO-30 ships DEM, "
            f"HEM and WBM bands -- see ELEVATION_BAND), a GeoTIFF compression "
            f"its decoder rejects (see WHITEBOX_COMPRESSION), a geographic "
            f"rather than projected CRS, or a blocked whitebox_tools.exe."
        )
