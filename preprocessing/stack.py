"""Co-registration and channel stacking.

Brief, Section 7.1: co-register all layers to a common 10 m grid in the AOI's
UTM CRS. Section 7.5: the model input is a configurable channel stack.

Two rules are enforced here rather than left to the caller:

1. **Categorical layers are never interpolated.** SCL class codes, masks and
   the SAR geometry map are resampled with nearest-neighbour whatever
   ``preprocessing.stack.resampling`` says. Bilinear interpolation of class
   codes would invent classes that do not exist -- averaging "cloud" (9) and
   "snow" (11) into "thin cirrus" (10) is a fabricated observation.
2. **The reference grid is explicit.** Every stacked layer is reported with the
   grid it was resampled *from*, so a silent mismatch cannot hide.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import numpy as np

from utils.logging import get_logger

log = get_logger(__name__)

#: Resampling for layers whose values are class codes, not measurements.
CATEGORICAL_RESAMPLING = "nearest"

#: Layer names treated as categorical regardless of configuration.
CATEGORICAL_HINTS = (
    "scl",
    "mask",
    "class",
    "qa",
    "geometry",
    "shadow",
    "cloud",
    "stream",
    "wbm",
)


@dataclass(frozen=True)
class Grid:
    """A raster grid: CRS, affine transform and shape."""

    crs: str
    transform: Any
    width: int
    height: int

    @property
    def cellsize(self) -> float:
        return abs(float(self.transform.a))

    @property
    def shape(self) -> tuple[int, int]:
        return (self.height, self.width)

    def matches(self, other: "Grid", *, tolerance: float = 1e-6) -> bool:
        if (self.width, self.height) != (other.width, other.height):
            return False
        if str(self.crs) != str(other.crs):
            return False
        return all(
            abs(a - b) <= tolerance
            for a, b in zip(tuple(self.transform)[:6], tuple(other.transform)[:6])
        )

    def describe(self) -> str:
        return (
            f"{self.width}x{self.height} @ {self.cellsize:.1f} m, {self.crs}"
        )


@dataclass
class StackedLayers:
    """A co-registered channel stack."""

    grid: Grid
    names: list[str] = field(default_factory=list)
    arrays: list[np.ndarray] = field(default_factory=list)
    provenance: dict[str, str] = field(default_factory=dict)

    def add(
        self, name: str, array: np.ndarray, source: str = "in-memory"
    ) -> "StackedLayers":
        if array.shape != self.grid.shape:
            raise ValueError(
                f"layer {name!r} has shape {array.shape}, but the stack grid is "
                f"{self.grid.shape} ({self.grid.describe()})"
            )
        if name in self.names:
            raise ValueError(f"duplicate layer name: {name!r}")
        self.names.append(name)
        self.arrays.append(array)
        self.provenance[name] = source
        return self

    def as_array(self) -> np.ndarray:
        """``(bands, rows, cols)`` float32 cube."""
        if not self.arrays:
            raise ValueError("the stack is empty")
        return np.stack([a.astype(np.float32) for a in self.arrays], axis=0)

    def __len__(self) -> int:
        return len(self.names)

    def __contains__(self, name: str) -> bool:
        return name in self.names

    def get(self, name: str) -> np.ndarray:
        try:
            return self.arrays[self.names.index(name)]
        except ValueError as exc:
            raise KeyError(
                f"no layer {name!r} in the stack; have {self.names}"
            ) from exc


def is_categorical(name: str) -> bool:
    """Whether a layer name denotes class codes rather than measurements."""
    lowered = name.lower()
    return any(hint in lowered for hint in CATEGORICAL_HINTS)


def read_grid(path: str | Path) -> Grid:
    """The grid of a raster on disk."""
    import rasterio

    with rasterio.open(path) as src:
        return Grid(
            crs=str(src.crs), transform=src.transform, width=src.width, height=src.height
        )


def reference_grid_from(path: str | Path) -> Grid:
    """Use an existing raster's grid as the stack reference.

    The DEM is the natural choice: it is the only layer every other product is
    compared against, and it does not change between scenes.
    """
    grid = read_grid(path)
    from utils.crs import ensure_projected

    ensure_projected(grid.crs, context="the stack reference grid")
    log.info("stack reference grid: %s", grid.describe())
    return grid


def reproject_to_grid(
    path: str | Path,
    grid: Grid,
    *,
    band: int = 1,
    resampling: str = "bilinear",
    categorical: bool | None = None,
) -> np.ndarray:
    """Read one band of a raster onto ``grid``.

    Args:
        categorical: force nearest-neighbour. ``None`` infers it from the
            file name via :func:`is_categorical`.
    """
    import rasterio
    from rasterio.enums import Resampling
    from rasterio.warp import reproject

    path = Path(path)
    if categorical is None:
        categorical = is_categorical(path.name)

    method_name = CATEGORICAL_RESAMPLING if categorical else resampling
    if categorical and resampling != CATEGORICAL_RESAMPLING:
        log.debug(
            "%s is categorical: using %s instead of %s, so no class code is "
            "invented by interpolation",
            path.name,
            CATEGORICAL_RESAMPLING,
            resampling,
        )

    try:
        method = getattr(Resampling, method_name)
    except AttributeError as exc:
        raise ValueError(f"unsupported resampling method: {method_name!r}") from exc

    with rasterio.open(path) as src:
        source_grid = Grid(
            crs=str(src.crs), transform=src.transform, width=src.width, height=src.height
        )
        if source_grid.matches(grid):
            return src.read(band).astype(np.float64)

        destination = np.zeros(grid.shape, dtype=np.float64)
        reproject(
            source=rasterio.band(src, band),
            destination=destination,
            src_transform=src.transform,
            src_crs=src.crs,
            dst_transform=grid.transform,
            dst_crs=grid.crs,
            resampling=method,
        )
        log.debug(
            "resampled %s from %s to %s using %s",
            path.name,
            source_grid.describe(),
            grid.describe(),
            method_name,
        )
        return destination


def write_stack(
    stack: StackedLayers,
    out_path: str | Path,
    *,
    tags: dict[str, str] | None = None,
) -> Path:
    """Write a stack as a multi-band GeoTIFF with band descriptions."""
    import rasterio

    from utils.io import ensure_parent

    out_path = ensure_parent(out_path)
    cube = stack.as_array()

    profile = {
        "driver": "GTiff",
        "height": stack.grid.height,
        "width": stack.grid.width,
        "count": cube.shape[0],
        "dtype": "float32",
        "crs": stack.grid.crs,
        "transform": stack.grid.transform,
        "compress": "deflate",
        "predictor": 2,
        "tiled": True,
    }

    with rasterio.open(out_path, "w", **profile) as dst:
        dst.write(cube)
        for index, name in enumerate(stack.names, start=1):
            dst.set_band_description(index, name)
        dst.update_tags(
            HDM_LAYERS=",".join(stack.names),
            HDM_VALUE_TYPE="derived",
            **{f"HDM_SOURCE_{n.upper()}": s for n, s in stack.provenance.items()},
            **(tags or {}),
        )

    log.info("wrote stack %s with %d layer(s): %s", out_path.name, len(stack), stack.names)
    return out_path


def read_stack(path: str | Path) -> StackedLayers:
    """Read a stack written by :func:`write_stack`."""
    import rasterio

    with rasterio.open(path) as src:
        grid = Grid(
            crs=str(src.crs), transform=src.transform, width=src.width, height=src.height
        )
        stack = StackedLayers(grid=grid)
        for index in range(1, src.count + 1):
            name = src.descriptions[index - 1] or f"band_{index}"
            stack.add(name, src.read(index).astype(np.float64), source=str(path))
    return stack
