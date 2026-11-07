"""Turn a co-registered stack and a label raster into training patches.

Brief, Section 7.5. This is the step between Phase 2's output and Phase 6's
dataset: it assembles the configured channel stack, cuts it into
``patch.size_px`` tiles at ``patch.stride_px``, and writes each one through
:func:`models.dataset.write_patch` with the coordinates that let
:func:`models.dataset.assign_splits` place it on the ground.

**The labelling contract.** A label raster is a single-band GeoTIFF on exactly
the same grid as the stack, holding this project's own class integers (0-4)
with ``models.ignore_index`` for unlabelled ground. That is what a QGIS
labelling session exports when the labeller rasterises their polygons against
the stack. Nothing here guesses at a layout: the grid must match, and
:func:`build_patches` refuses the pair if it does not, because a label raster
offset by even one pixel mislabels every boundary in the scene while looking
entirely reasonable.

**Unlabelled is not background.** Ground the labeller did not visit must be
``ignore_index``, never 0. A QGIS export defaults empty space to zero, so
:func:`build_patches` reports the share of each class it found and warns when
a patch set is overwhelmingly class 0 — the signature of an export where
"not labelled" silently became "background", which would teach the model that
every unvisited landslide and lake is land.

**Nodata is not a value.** Where the stack has no observation the channels are
left as they are but the label is forced to ``ignore_index``, so no pixel is
trained on an absent measurement. This is the same rule
:mod:`models.predict` applies at inference.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import TYPE_CHECKING, Any, Mapping, Sequence

import numpy as np

from models.dataset import keep_patch, write_patch
from utils.logging import get_logger

if TYPE_CHECKING:  # pragma: no cover
    from config.schema import Config

log = get_logger(__name__)


class PatchBuildError(RuntimeError):
    """A stack and label pair that cannot be turned into patches."""


@dataclass
class BuildReport:
    """What a build produced, and what it discarded."""

    written: int = 0
    skipped_unlabelled: int = 0
    skipped_empty: int = 0
    class_pixels: dict[str, int] = field(default_factory=dict)
    ignored_pixels: int = 0
    out_dir: Path | None = None

    def as_dict(self) -> dict[str, Any]:
        total = sum(self.class_pixels.values()) + self.ignored_pixels
        return {
            "patches_written": self.written,
            "skipped_below_min_labelled_fraction": self.skipped_unlabelled,
            "skipped_no_data": self.skipped_empty,
            "class_pixels": dict(self.class_pixels),
            "ignored_pixels": self.ignored_pixels,
            "class_fractions": {
                name: round(count / total, 5) if total else 0.0
                for name, count in self.class_pixels.items()
            },
            "out_dir": None if self.out_dir is None else str(self.out_dir),
        }


def assemble_stack(
    channels: Mapping[str, np.ndarray], cfg: "Config"
) -> np.ndarray:
    """Stack the configured channels, in the configured order.

    Args:
        channels: ``{channel name: 2-D array}``, covering every name in
            ``models.channels``. Extra entries are ignored, so a caller may
            pass everything it has.

    Raises:
        PatchBuildError: if a configured channel is missing, or the arrays
            disagree in shape. Both are named, because a missing channel
            silently zero-filled would teach the model that "no data" is a
            valid value for real terrain.
    """
    wanted = list(cfg.models.channels)
    missing = [name for name in wanted if name not in channels]
    if missing:
        raise PatchBuildError(
            f"channel(s) {missing} are configured in models.channels but were "
            f"not supplied (got {sorted(channels)}). Supply them or remove "
            "them from the stack -- a zero-filled channel is not a measurement."
        )

    shapes = {name: np.asarray(channels[name]).shape for name in wanted}
    distinct = set(shapes.values())
    if len(distinct) != 1:
        raise PatchBuildError(
            f"channels are on different grids: {shapes}. Co-register them in "
            "Phase 2 before building patches."
        )

    return np.stack(
        [np.asarray(channels[name], dtype=np.float32) for name in wanted], axis=0
    )


def build_patches(
    cfg: "Config",
    channels: Mapping[str, np.ndarray],
    labels: np.ndarray,
    *,
    transform: Any,
    out_dir: str | Path,
    crs: Any = None,
    event: str | None = None,
    unseen: np.ndarray | None = None,
    prefix: str = "patch",
) -> BuildReport:
    """Cut a stack and its labels into patches on disk.

    Args:
        labels: single band, this project's class integers, ``ignore_index``
            where unlabelled. Must match the stack's grid exactly.
        transform: the stack's affine transform, used to record each patch's
            projected position so splits can be geographic.
        unseen: where the stack holds no observation. Those pixels' labels are
            forced to ``ignore_index``.
        event: recorded on every patch, enabling ``split.strategy: event``.

    Returns:
        A :class:`BuildReport`.
    """
    settings = cfg.models
    stack = assemble_stack(channels, cfg)
    labels = np.asarray(labels)

    if labels.shape != stack.shape[1:]:
        raise PatchBuildError(
            f"labels are {labels.shape} but the stack is {stack.shape[1:]}. A "
            "label raster must be on exactly the stack's grid -- an offset of "
            "one pixel mislabels every boundary in the scene while looking "
            "entirely reasonable."
        )

    valid_values = set(range(settings.num_classes)) | {settings.ignore_index}
    present = {int(v) for v in np.unique(labels)}
    unexpected = sorted(present - valid_values)
    if unexpected:
        raise PatchBuildError(
            f"the label raster contains value(s) {unexpected}, which are "
            f"neither a class (0-{settings.num_classes - 1}) nor "
            f"ignore_index ({settings.ignore_index}). If these come from an "
            "external dataset, map them first with "
            "models.dataset.map_labels."
        )

    labels = labels.astype(np.uint8, copy=True)
    if unseen is None:
        unseen = np.all(stack == 0.0, axis=0)
    else:
        unseen = np.asarray(unseen, dtype=bool)
        if unseen.shape != labels.shape:
            raise PatchBuildError(
                f"unseen {unseen.shape} does not match the grid {labels.shape}"
            )
    forced = int(np.count_nonzero(unseen & (labels != settings.ignore_index)))
    labels[unseen] = settings.ignore_index
    if forced:
        log.info(
            "%d labelled pixel(s) had no observation in the stack and were set "
            "to ignore_index: a label without a measurement cannot be trained on",
            forced,
        )

    size = settings.patch.size_px
    stride = settings.patch.stride_px
    height, width = labels.shape
    if height < size or width < size:
        raise PatchBuildError(
            f"the grid is {height}x{width}, smaller than one "
            f"{size}x{size} patch"
        )

    out_dir = Path(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    report = BuildReport(out_dir=out_dir)
    counts = np.zeros(settings.num_classes, dtype=np.int64)

    for row in range(0, height - size + 1, stride):
        for col in range(0, width - size + 1, stride):
            y = labels[row : row + size, col : col + size]
            if not keep_patch(y, cfg):
                report.skipped_unlabelled += 1
                continue
            x = stack[:, row : row + size, col : col + size]
            if np.all(unseen[row : row + size, col : col + size]):
                report.skipped_empty += 1
                continue

            # Projected position of the patch's top-left corner.
            x_m, y_m = transform * (col, row)
            write_patch(
                out_dir / f"{prefix}_{row:05d}_{col:05d}.npz",
                x, y, settings.channels,
                x_m=float(x_m), y_m=float(y_m),
                crs=None if crs is None else str(crs),
                event=event,
            )
            report.written += 1
            for class_id in range(settings.num_classes):
                counts[class_id] += int(np.count_nonzero(y == class_id))
            report.ignored_pixels += int(
                np.count_nonzero(y == settings.ignore_index)
            )

    report.class_pixels = {
        name: int(counts[i]) for i, name in enumerate(settings.classes)
    }

    log.info(
        "built %d patch(es) in %s; skipped %d below "
        "min_labelled_fraction and %d with no observation",
        report.written, out_dir,
        report.skipped_unlabelled, report.skipped_empty,
    )
    _warn_about_the_label_raster(report, cfg)
    return report


def _warn_about_the_label_raster(report: BuildReport, cfg: "Config") -> None:
    """Flag the two label-export mistakes that are quiet and expensive."""
    labelled = sum(report.class_pixels.values())
    if not labelled:
        log.warning("no labelled pixels were written at all")
        return

    background = report.class_pixels.get(cfg.models.classes[0], 0)
    if background / labelled > 0.98:
        log.warning(
            "%.1f%% of the labelled pixels are %r. If the labeller only drew "
            "the features of interest, their QGIS export has turned "
            "UNLABELLED ground into background, which would teach the model "
            "that every unvisited lake and landslide is land. Empty space "
            "must export as ignore_index (%d), not 0",
            100 * background / labelled,
            cfg.models.classes[0],
            cfg.models.ignore_index,
        )

    absent = [
        name for name, count in report.class_pixels.items() if count == 0
    ]
    if absent:
        log.warning(
            "class(es) %s have no pixels in this patch set. A model cannot "
            "learn them, and their IoU will read 0.0 for that reason rather "
            "than through any failure of the architecture",
            ", ".join(absent),
        )


def write_report(report: BuildReport, path: str | Path) -> Path:
    """Record what the build produced, beside the patches."""
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(report.as_dict(), indent=2), encoding="utf-8")
    log.info("wrote %s", path)
    return path
