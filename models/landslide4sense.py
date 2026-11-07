"""Adapter for the Landslide4Sense 2022 benchmark (Phase 6).

Licence: **Creative Commons Attribution 4.0 International**, read from the
Zenodo record 10.5281/zenodo.10463239 on 2026-11-07 rather than from a mirror.
Use requires attribution:

    Ghorbanzadeh, O., Xu, Y., Ghamisi, P., Kopp, M. and Kreil, D. (2022),
    "Landslide4Sense: Reference Benchmark Data and Deep Learning Models for
    Landslide Detection", IEEE Transactions on Geoscience and Remote Sensing
    60, 1-17.

**What this dataset can and cannot answer.**

It supplies real, independently produced labels for **landslide** and
**background** only — its masks are binary. So it can answer the brief's
required *architecture* comparison, plain U-Net against Attention U-Net on a
real labelled task with this project's channel conventions. It **cannot**
answer the brief's primary result, the water-versus-shadow confusion, because
it labels neither water nor terrain shadow. That needs hand-labelled
Himalayan patches and there is no substitute for them.

Three mismatches with this project, each handled explicitly rather than
papered over.

**Patch size.** Theirs is 128x128; this project's is 256x256. Patches are
**not** upsampled, because interpolating a label raster invents boundaries
that were never drawn. Instead the configured patch size is expected to be
128 for a Landslide4Sense run (see ``config/landslide4sense.yaml``), and
:func:`convert` refuses a mismatch rather than resizing.

**Channels.** They ship Sentinel-2 B1-B12 plus a DEM and an ALOS PALSAR
slope layer. That covers eleven of this project's fifteen channels. It has no
Sentinel-1, and no illumination or terrain-shadow layer — those need per-scene
sun angles, which the dataset does not carry. A run therefore uses a reduced
stack, declared in config, and :func:`convert` refuses any channel it cannot
actually supply. Zero-filling the missing ones would teach the model that "no
data" is a valid value for real terrain.

**No georeference.** The patches carry no coordinates, so a *geographic*
split is impossible. Each patch is given a synthetic position derived from its
index, spread far enough apart that the block split degenerates into a
per-patch split — which would leak. A Landslide4Sense run must therefore use
``split.strategy: event`` with the patch index as the event, which is what
:func:`convert` records. This is a real weakness of using the dataset at all
and is recorded in ``docs/labelling.md``.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import TYPE_CHECKING, Any, Iterable

import numpy as np

from models.dataset import DatasetError, keep_patch, map_labels, write_patch
from utils.logging import get_logger

if TYPE_CHECKING:  # pragma: no cover
    from config.schema import Config

log = get_logger(__name__)

SOURCE_NAME = "landslide4sense"
CITATION = (
    "Ghorbanzadeh, O., Xu, Y., Ghamisi, P., Kopp, M. and Kreil, D. (2022), "
    "'Landslide4Sense: Reference Benchmark Data and Deep Learning Models for "
    "Landslide Detection', IEEE Transactions on Geoscience and Remote Sensing "
    "60, 1-17. Data: 10.5281/zenodo.10463239, CC BY 4.0."
)
ZENODO_RECORD = "https://zenodo.org/records/10463239"

#: Band order inside each Landslide4Sense ``image_N.h5`` array, as documented
#: with the dataset: Sentinel-2 B1-B12, then a DEM, then ALOS PALSAR slope.
#: Zero-based index into the last axis.
BAND_INDEX = {
    "S2_B1": 0, "S2_B2": 1, "S2_B3": 2, "S2_B4": 3, "S2_B5": 4,
    "S2_B6": 5, "S2_B7": 6, "S2_B8": 7, "S2_B9": 8, "S2_B10": 9,
    "S2_B11": 10, "S2_B12": 11,
    "DEM": 12, "SLOPE": 13,
}

#: Channels this project names that the dataset can supply, directly or by
#: arithmetic on bands it holds. Anything outside this set is refused.
SUPPORTED = set(BAND_INDEX) | {"NDWI", "MNDWI", "NDVI"}


@dataclass
class ConversionReport:
    """What a conversion produced and what it refused."""

    written: int = 0
    skipped_unlabelled: int = 0
    class_pixels: dict[str, int] = field(default_factory=dict)
    channels: list[str] = field(default_factory=list)
    out_dir: Path | None = None
    citation: str = CITATION

    def as_dict(self) -> dict[str, Any]:
        return {
            "source": SOURCE_NAME,
            "licence": "CC BY 4.0 (Zenodo 10.5281/zenodo.10463239)",
            "citation": self.citation,
            "patches_written": self.written,
            "skipped_below_min_labelled_fraction": self.skipped_unlabelled,
            "channels": list(self.channels),
            "class_pixels": dict(self.class_pixels),
            "out_dir": None if self.out_dir is None else str(self.out_dir),
            "cannot_supply": [
                "S1_VV", "S1_VH", "ILLUMINATION", "TERRAIN_SHADOW",
            ],
            "classes_present": ["background", "landslide"],
            "classes_absent": ["water", "terrain_shadow", "snow_ice"],
            "note": (
                "Binary source. The water-vs-shadow confusion the brief asks "
                "for cannot be produced from this dataset at any sample size."
            ),
        }


def _index(name: str) -> np.ndarray | None:
    return None


def _derive(name: str, bands: dict[str, np.ndarray]) -> np.ndarray:
    """A normalised index from bands the dataset holds."""
    def nd(a: np.ndarray, b: np.ndarray) -> np.ndarray:
        total = a + b
        with np.errstate(divide="ignore", invalid="ignore"):
            out = np.where(total != 0, (a - b) / total, np.nan)
        return out.astype(np.float32)

    if name == "NDWI":
        return nd(bands["S2_B3"], bands["S2_B8"])
    if name == "MNDWI":
        return nd(bands["S2_B3"], bands["S2_B11"])
    if name == "NDVI":
        return nd(bands["S2_B8"], bands["S2_B4"])
    raise DatasetError(f"cannot derive {name!r} from this dataset")


def check_channels(cfg: "Config") -> list[str]:
    """The configured stack, verified against what the dataset can supply.

    Raises:
        DatasetError: naming every channel the dataset cannot provide, with
            the reason, rather than letting a zero-filled channel through.
    """
    wanted = list(cfg.models.channels)
    unsupported = [name for name in wanted if name not in SUPPORTED]
    if unsupported:
        raise DatasetError(
            f"Landslide4Sense cannot supply {unsupported}. It ships "
            f"Sentinel-2 B1-B12, a DEM and an ALOS PALSAR slope layer, and no "
            f"Sentinel-1, illumination or terrain-shadow layer -- the last two "
            f"need per-scene sun angles the dataset does not carry. Use a "
            f"reduced stack (config/landslide4sense.yaml) rather than "
            f"zero-filling: a zero channel is not a measurement."
        )
    return wanted


def _read_pair(image_path: Path, mask_path: Path) -> tuple[np.ndarray, np.ndarray]:
    """One Landslide4Sense image and its mask, from HDF5."""
    try:
        import h5py
    except ImportError as exc:  # pragma: no cover - environment problem
        raise DatasetError(
            "h5py is required to read Landslide4Sense (.h5); install it with "
            "`pip install h5py`"
        ) from exc

    with h5py.File(image_path, "r") as handle:
        key = next(iter(handle.keys()))
        image = np.asarray(handle[key], dtype=np.float32)
    with h5py.File(mask_path, "r") as handle:
        key = next(iter(handle.keys()))
        mask = np.asarray(handle[key])
    return image, mask


def convert(
    cfg: "Config",
    root: str | Path,
    out_dir: str | Path,
    *,
    limit: int | None = None,
) -> ConversionReport:
    """Convert the labelled training split into this project's patches.

    Args:
        root: the unpacked ``TrainData`` directory, holding ``img/`` and
            ``mask/``. Only the training split is labelled; the validation
            and test splits are withheld for competition ranking.
        limit: stop after this many patches, for a quick check.

    Returns:
        A :class:`ConversionReport`.
    """
    channels = check_channels(cfg)
    root = Path(root)
    img_dir, mask_dir = root / "img", root / "mask"
    if not img_dir.is_dir() or not mask_dir.is_dir():
        raise DatasetError(
            f"expected {img_dir} and {mask_dir}. Unpack TrainData.zip from "
            f"{ZENODO_RECORD} and point root at the TrainData directory."
        )

    label_map = cfg.models.sources[SOURCE_NAME].label_map
    if not label_map:
        raise DatasetError(
            f"models.sources.{SOURCE_NAME}.label_map is empty; the mapping "
            "from this dataset's labels onto our classes must be stated in "
            "config, not assumed"
        )

    size = cfg.models.patch.size_px
    out_dir = Path(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    report = ConversionReport(channels=channels, out_dir=out_dir)
    counts = np.zeros(cfg.models.num_classes, dtype=np.int64)

    images = sorted(img_dir.glob("*.h5"))
    if not images:
        raise DatasetError(f"no .h5 files under {img_dir}")
    log.info("converting %d Landslide4Sense patch(es)", len(images))

    for n, image_path in enumerate(images):
        if limit is not None and report.written >= limit:
            break
        mask_path = mask_dir / image_path.name.replace("image", "mask")
        if not mask_path.is_file():
            log.warning("no mask for %s; skipped", image_path.name)
            continue

        image, mask = _read_pair(image_path, mask_path)
        if image.ndim != 3:
            raise DatasetError(
                f"{image_path.name} is {image.shape}; expected (h, w, bands)"
            )
        if image.shape[0] != size or image.shape[1] != size:
            raise DatasetError(
                f"{image_path.name} is {image.shape[0]}x{image.shape[1]} but "
                f"models.patch.size_px is {size}. Landslide4Sense patches are "
                f"128x128; set the patch size to 128 for this dataset rather "
                f"than resampling, because interpolating a label raster "
                f"invents boundaries that were never drawn."
            )

        bands = {
            name: image[:, :, index]
            for name, index in BAND_INDEX.items()
            if index < image.shape[2]
        }
        stack = np.stack(
            [
                bands[name] if name in bands else _derive(name, bands)
                for name in channels
            ],
            axis=0,
        ).astype(np.float32)

        labels = map_labels(
            np.squeeze(mask),
            label_map,
            ignore_index=cfg.models.ignore_index,
            source_name=SOURCE_NAME,
        )
        if not keep_patch(labels, cfg):
            report.skipped_unlabelled += 1
            continue

        # No georeference exists, so the position is synthetic and the split
        # MUST be by event (the patch's own identity). See the module
        # docstring.
        write_patch(
            out_dir / f"l4s_{image_path.stem}.npz",
            stack, labels, channels,
            x_m=float(n * size * cfg.models.patch.scale_m),
            y_m=0.0,
            crs=None,
            event=f"l4s-{image_path.stem}",
        )
        report.written += 1
        for class_id in range(cfg.models.num_classes):
            counts[class_id] += int(np.count_nonzero(labels == class_id))

    report.class_pixels = {
        name: int(counts[i]) for i, name in enumerate(cfg.models.classes)
    }
    log.info(
        "wrote %d patch(es); %d skipped below min_labelled_fraction; "
        "class pixels %s",
        report.written, report.skipped_unlabelled, report.class_pixels,
    )
    absent = [
        name for name, count in report.class_pixels.items() if count == 0
    ]
    if absent:
        log.warning(
            "class(es) %s have no pixels: this source is BINARY, so their IoU "
            "will read 0.00 for want of data. The water-vs-shadow confusion "
            "the brief requires cannot come from this dataset",
            ", ".join(absent),
        )
    if cfg.models.split.strategy != "event":
        log.warning(
            "split.strategy is %r but Landslide4Sense patches carry no "
            "coordinates, so a geographic split would be a per-patch split "
            "and would leak. Use config/landslide4sense.yaml, which sets "
            "'event'",
            cfg.models.split.strategy,
        )
    return report


def write_report(report: ConversionReport, path: str | Path) -> Path:
    """Record the conversion, its licence and its limits beside the patches."""
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(report.as_dict(), indent=2), encoding="utf-8")
    log.info("wrote %s", path)
    return path
