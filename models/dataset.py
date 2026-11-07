"""Training patches, label mapping and leak-free splits (Phase 6).

Brief, Section 7.5. Three things this module is responsible for, in order of
how much damage getting them wrong would do.

**1. The split must not leak.** The brief forbids random pixel or random patch
splits that leak spatially adjacent data, because two 256-pixel patches whose
origins are 128 pixels apart share half their ground: scored across a random
split, a model is partly being tested on its training data and every metric is
optimistic. :func:`assign_splits` partitions **blocks of ground**, never
patches, and then discards patches that come within ``split.buffer_px`` of a
block boundary so that no retained patch straddles one.

**2. The label mapping must be explicit and recorded.** External datasets use
their own label values, and the mapping onto this project's five classes is a
scientific choice, not a detail. It lives in
``models.sources.<name>.label_map`` in config and is applied by
:func:`map_labels`, which **refuses an unmapped value** rather than silently
treating it as background. A source label that nobody has decided about is a
gap in the documentation, and guessing it would quietly mislabel real ground.

**3. The channel stack is the contract.** A patch holds its channels in the
order of ``models.channels``, and the model's input width is the length of
that list. :func:`PatchDataset` verifies every patch against the configured
stack on load, so a stack change and a stale patch directory produce an
immediate, named error instead of a shape failure deep in training.

Patches are stored as compressed ``.npz`` with an ``x`` array of shape
``(channels, size, size)``, a ``y`` label array of ``(size, size)``, and the
channel names, so a patch is self-describing and can be checked rather than
trusted.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import TYPE_CHECKING, Any, Iterable, Sequence

import numpy as np

from utils.logging import get_logger

if TYPE_CHECKING:  # pragma: no cover
    from config.schema import Config, ModelsConfig

log = get_logger(__name__)

#: Partition names, in the order they are reported.
SPLITS = ("train", "val", "test")


class DatasetError(RuntimeError):
    """A patch set that cannot be used as configured."""


# --------------------------------------------------------------------------- #
# Label mapping
# --------------------------------------------------------------------------- #


def map_labels(
    source_labels: np.ndarray,
    label_map: dict[str, int | None],
    *,
    ignore_index: int,
    source_name: str = "source",
) -> np.ndarray:
    """Translate one dataset's label values onto this project's classes.

    Args:
        source_labels: the external dataset's own label raster.
        label_map: ``{"<source value>": our class int or None}``. ``None``
            maps to ``ignore_index``, which is the honest handling of a
            source's own no-data marker.
        ignore_index: the value excluded from loss and metrics.

    Returns:
        A ``uint8`` label array in this project's class space.

    Raises:
        DatasetError: if the source contains a value the map does not cover.
            This is deliberate. Defaulting an unknown label to background
            would turn an undocumented class into training signal for "land",
            and the brief requires the complete mapping to be documented.
    """
    labels = np.asarray(source_labels)
    present = {int(v) for v in np.unique(labels)}
    mapped_from = {int(k) for k in label_map}

    unmapped = sorted(present - mapped_from)
    if unmapped:
        raise DatasetError(
            f"{source_name} contains label value(s) {unmapped} with no entry "
            f"in label_map (which covers {sorted(mapped_from)}). Add them to "
            f"models.sources.{source_name}.label_map and document the choice "
            f"in docs/labelling.md -- an unmapped label must not be guessed."
        )

    out = np.full(labels.shape, ignore_index, dtype=np.uint8)
    for raw, target in label_map.items():
        if target is None:
            continue
        out[labels == int(raw)] = int(target)
    return out


# --------------------------------------------------------------------------- #
# Splits
# --------------------------------------------------------------------------- #


@dataclass(frozen=True)
class PatchRef:
    """One patch on disk, with the ground it came from."""

    path: Path
    #: Projected coordinates of the patch's top-left corner, in metres.
    x_m: float
    y_m: float
    #: Which labelled event it belongs to, when the source records one.
    event: str | None = None

    def block(self, block_m: float) -> tuple[int, int]:
        """The geographic block this patch sits in."""
        return (int(np.floor(self.x_m / block_m)), int(np.floor(self.y_m / block_m)))


def _partition_keys(
    keys: Sequence[Any], settings: "ModelsConfig"
) -> dict[Any, str]:
    """Assign whole blocks or events to partitions, reproducibly."""
    ordered = sorted(keys, key=repr)
    rng = np.random.default_rng(settings.split.seed)
    # Permute indices, not the keys themselves: a block key is a tuple, and
    # numpy would turn it into an unhashable array.
    shuffled = [ordered[i] for i in rng.permutation(len(ordered))]

    n = len(shuffled)
    n_train = int(round(n * settings.split.train_fraction))
    n_val = int(round(n * settings.split.val_fraction))

    # With few keys, rounding can starve a partition. An empty test set makes
    # evaluation vacuous, and an empty validation set leaves early stopping
    # and checkpoint selection with nothing to follow -- so when there is
    # enough to go round, every partition gets at least one key, and training
    # gives up the surplus rather than val or test.
    if n >= 3:
        n_val = max(1, n_val)
        n_train = min(n_train, n - n_val - 1)
        n_train = max(1, n_train)
        n_val = min(n_val, n - n_train - 1)
    elif n == 2:
        n_train, n_val = 1, 0  # one train, one test; no validation is possible
    else:
        n_train, n_val = n, 0

    assignment: dict[Any, str] = {}
    for i, key in enumerate(shuffled):
        if i < n_train:
            assignment[key] = "train"
        elif i < n_train + n_val:
            assignment[key] = "val"
        else:
            assignment[key] = "test"
    return assignment


def assign_splits(
    patches: Sequence[PatchRef], cfg: "Config"
) -> dict[str, list[PatchRef]]:
    """Partition patches without leaking adjacent ground.

    Blocks of ground (or whole events) are assigned to partitions, never
    individual patches, and patches near a block boundary are then dropped so
    that no retained patch spans two partitions.

    Returns:
        ``{"train": [...], "val": [...], "test": [...]}``.

    Raises:
        DatasetError: if the strategy is ``event`` but patches carry no event.
    """
    settings = cfg.models
    block_m = settings.split.block_km * 1000.0

    if settings.split.strategy == "event":
        missing = [p for p in patches if p.event is None]
        if missing:
            raise DatasetError(
                f"split.strategy is 'event' but {len(missing)} patch(es) carry "
                "no event label; either record events when building patches or "
                "use the 'geographic' strategy"
            )
        keyed = [(p, p.event) for p in patches]
    else:
        keyed = [(p, p.block(block_m)) for p in patches]

    # The buffer is applied FIRST, and only the blocks that still hold a patch
    # are partitioned.
    #
    # Assigning blocks before dropping patches makes the guarantee in
    # _partition_keys empty: a block can be given to "test" and then lose
    # every one of its patches to the buffer, leaving a partition with nothing
    # in it and no warning that the assignment ever intended otherwise.
    buffer_m = settings.split.buffer_px * settings.patch.scale_m
    retained: list[tuple[PatchRef, Any]] = []
    dropped = 0
    for patch, key in keyed:
        if settings.split.strategy == "geographic" and buffer_m > 0.0:
            # Distance from the patch origin to the nearest block edge. A
            # patch closer than the buffer could overlap ground assigned
            # elsewhere, so it belongs to no partition.
            near_x = min(patch.x_m % block_m, block_m - (patch.x_m % block_m))
            near_y = min(patch.y_m % block_m, block_m - (patch.y_m % block_m))
            if min(near_x, near_y) < buffer_m:
                dropped += 1
                continue
        retained.append((patch, key))

    assignment = _partition_keys({k for _, k in retained}, settings)

    out: dict[str, list[PatchRef]] = {name: [] for name in SPLITS}
    for patch, key in retained:
        out[assignment[key]].append(patch)

    log.info(
        "%s split: %d train, %d val, %d test patch(es); %d dropped within "
        "%.0f m of a block boundary",
        settings.split.strategy,
        len(out["train"]), len(out["val"]), len(out["test"]), dropped, buffer_m,
    )
    # The buffer is a band around every block edge, so its cost grows as the
    # buffer approaches the block size. Losing most of a hand-labelled set to
    # it is a configuration problem, not a safety feature, and it is quiet
    # enough to miss.
    if patches and dropped / len(patches) > 0.5:
        log.warning(
            "the split buffer discarded %d of %d patch(es) (%.0f%%): a %.0f m "
            "buffer against %.1f km blocks leaves little interior. Widen "
            "split.block_km or narrow split.buffer_px",
            dropped, len(patches), 100 * dropped / len(patches),
            buffer_m, settings.split.block_km,
        )
    empty = [name for name in SPLITS if not out[name]]
    if empty:
        log.warning(
            "partition(s) %s are empty: %d patch(es) over %d %s. Metrics on "
            "an empty partition are undefined, not zero",
            ", ".join(empty), len(retained), len(assignment),
            "event(s)" if settings.split.strategy == "event" else "block(s)",
        )
        if len(assignment) < len(SPLITS):
            log.warning(
                "only %d %s survived the buffer, and %d partitions are "
                "needed: there is not enough SEPARATED ground to split. "
                "Label in more, widely spaced areas rather than more "
                "thoroughly in one",
                len(assignment),
                "event(s)" if settings.split.strategy == "event" else "block(s)",
                len(SPLITS),
            )
    return out


def split_summary(splits: dict[str, list[PatchRef]]) -> dict[str, Any]:
    """Counts and block membership per partition, for the write-up."""
    return {
        name: {
            "patches": len(refs),
            "events": sorted({r.event for r in refs if r.event}) or None,
        }
        for name, refs in splits.items()
    }


# --------------------------------------------------------------------------- #
# Patch IO
# --------------------------------------------------------------------------- #


def write_patch(
    path: str | Path,
    x: np.ndarray,
    y: np.ndarray,
    channels: Sequence[str],
    *,
    x_m: float,
    y_m: float,
    crs: str | None = None,
    event: str | None = None,
) -> Path:
    """Write one self-describing patch.

    The channel names travel with the data so a patch can be *checked* against
    the configured stack rather than assumed to match it.
    """
    x = np.asarray(x, dtype=np.float32)
    y = np.asarray(y, dtype=np.uint8)
    if x.ndim != 3:
        raise DatasetError(f"x must be (channels, h, w), got {x.shape}")
    if x.shape[0] != len(channels):
        raise DatasetError(
            f"x has {x.shape[0]} channel(s) but {len(channels)} name(s) were "
            "given; a patch must describe every channel it holds"
        )
    if y.shape != x.shape[1:]:
        raise DatasetError(f"y {y.shape} does not match x {x.shape[1:]}")

    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    np.savez_compressed(
        path,
        x=x,
        y=y,
        channels=np.array(list(channels), dtype=object),
        meta=np.array(
            [json.dumps({"x_m": x_m, "y_m": y_m, "crs": crs, "event": event})],
            dtype=object,
        ),
    )
    return path


def read_patch_meta(path: str | Path) -> dict[str, Any]:
    """The georeference and event of a patch, without loading its arrays."""
    with np.load(path, allow_pickle=True) as data:
        if "meta" not in data:
            raise DatasetError(
                f"{path} has no meta array; it predates the self-describing "
                "patch format and cannot be placed on the ground, so it cannot "
                "be assigned to a geographic split"
            )
        return json.loads(str(data["meta"][0]))


def discover_patches(directory: str | Path) -> list[PatchRef]:
    """Every patch under ``directory``, with its position on the ground."""
    directory = Path(directory)
    if not directory.is_dir():
        raise DatasetError(f"patch directory not found: {directory}")
    refs: list[PatchRef] = []
    for path in sorted(directory.rglob("*.npz")):
        meta = read_patch_meta(path)
        refs.append(
            PatchRef(
                path=path,
                x_m=float(meta["x_m"]),
                y_m=float(meta["y_m"]),
                event=meta.get("event"),
            )
        )
    if not refs:
        raise DatasetError(f"no .npz patches under {directory}")
    log.info("found %d patch(es) under %s", len(refs), directory)
    return refs


# --------------------------------------------------------------------------- #
# Dataset
# --------------------------------------------------------------------------- #


@dataclass(frozen=True)
class ChannelStatistics:
    """Per-channel mean and standard deviation, with the channels they describe.

    The channel names travel with the numbers so a mismatch is caught rather
    than silently applying the wrong scaling to each slot.
    """

    channels: tuple[str, ...]
    mean: tuple[float, ...]
    sd: tuple[float, ...]
    patches: int

    def as_dict(self) -> dict[str, Any]:
        return {
            "channels": list(self.channels),
            "mean": list(self.mean),
            "sd": list(self.sd),
            "patches": self.patches,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "ChannelStatistics":
        return cls(
            channels=tuple(data["channels"]),
            mean=tuple(float(v) for v in data["mean"]),
            sd=tuple(float(v) for v in data["sd"]),
            patches=int(data.get("patches", 0)),
        )

    def apply(self, x: np.ndarray) -> np.ndarray:
        """Standardise a ``(channels, h, w)`` array."""
        mean = np.asarray(self.mean, dtype=np.float32)[:, None, None]
        sd = np.asarray(self.sd, dtype=np.float32)[:, None, None]
        return ((np.asarray(x, dtype=np.float32) - mean) / sd).astype(np.float32)


def channel_statistics(
    refs: Sequence[PatchRef], cfg: "Config"
) -> ChannelStatistics:
    """Per-channel mean and sd over the given patches.

    **Pass the TRAINING split only.** Computing these over every patch would
    carry the test split's distribution into the model, which is the same
    class of leak as a random patch split and just as invisible in the output.

    A zero standard deviation -- a constant channel -- is replaced by 1.0 so
    the channel passes through as a constant rather than producing NaN. A NaN
    input silently poisons every gradient in the batch.
    """
    channels = list(cfg.models.channels)
    total = np.zeros(len(channels), dtype=np.float64)
    total_sq = np.zeros(len(channels), dtype=np.float64)
    pixels = 0
    for ref in refs:
        with np.load(ref.path, allow_pickle=True) as data:
            x = np.asarray(data["x"], dtype=np.float64)
            names = [str(c) for c in data["channels"]]
        if names != channels:
            raise DatasetError(
                f"{ref.path.name} holds channels {names} but models.channels "
                f"is {channels}; statistics would describe the wrong slots"
            )
        finite = np.isfinite(x)
        total += np.where(finite, x, 0.0).sum(axis=(1, 2))
        total_sq += np.where(finite, x * x, 0.0).sum(axis=(1, 2))
        pixels += int(finite[0].size)
    if not pixels:
        raise DatasetError("no patches supplied, so no statistics exist")

    mean = total / pixels
    variance = np.maximum(total_sq / pixels - mean ** 2, 0.0)
    sd = np.sqrt(variance)
    constant = sd < 1e-9
    if constant.any():
        log.warning(
            "channel(s) %s are constant across the training split; their "
            "scaling is set to 1.0 so they pass through rather than "
            "producing NaN, but a constant channel carries no information",
            ", ".join(c for c, flag in zip(channels, constant) if flag),
        )
    sd = np.where(constant, 1.0, sd)

    stats = ChannelStatistics(
        channels=tuple(channels),
        mean=tuple(float(v) for v in mean),
        sd=tuple(float(v) for v in sd),
        patches=len(refs),
    )
    spread = float(np.max(np.abs(mean)) / max(np.min(np.abs(mean)), 1e-12))
    log.info(
        "channel statistics from %d training patch(es); the raw channel means "
        "span %.0fx, which is why they are standardised",
        len(refs), spread,
    )
    return stats


class PatchDataset:
    """A ``torch`` dataset over prepared patches.

    Deliberately not subclassing ``torch.utils.data.Dataset`` at import time,
    so this module can be imported, and its splitting and mapping logic
    tested, without torch present. It implements the same protocol
    (``__len__`` and ``__getitem__``), which is all a ``DataLoader`` requires.

    Every patch is verified against ``models.channels`` on load. A stale patch
    directory then fails by name on the first batch rather than as an opaque
    shape error part-way through an epoch.
    """

    def __init__(
        self,
        refs: Sequence[PatchRef],
        cfg: "Config",
        *,
        verify_channels: bool = True,
        statistics: "ChannelStatistics | None" = None,
    ) -> None:
        self.refs = list(refs)
        self.settings = cfg.models
        self.verify_channels = verify_channels
        self._expected = list(self.settings.channels)
        self.statistics = statistics
        if (
            statistics is not None
            and list(statistics.channels) != self._expected
        ):
            raise DatasetError(
                f"statistics describe channels {list(statistics.channels)} "
                f"but models.channels is {self._expected}; each slot would be "
                "scaled by the wrong numbers"
            )
        if statistics is None and self.settings.normalisation != "none":
            log.warning(
                "no channel statistics supplied while normalisation is %r, so "
                "patches are fed RAW. This stack spans four orders of "
                "magnitude and a raw run collapses to the majority class",
                self.settings.normalisation,
            )

    def __len__(self) -> int:
        return len(self.refs)

    def _check(self, path: Path, channels: Sequence[str], x: np.ndarray) -> None:
        if list(channels) != self._expected:
            raise DatasetError(
                f"{path.name} holds channels {list(channels)} but "
                f"models.channels is {self._expected}. Rebuild the patches or "
                "restore the stack; training on a mismatched stack silently "
                "feeds the model the wrong band in each slot."
            )
        size = self.settings.patch.size_px
        if x.shape[1:] != (size, size):
            raise DatasetError(
                f"{path.name} is {x.shape[1]}x{x.shape[2]} but "
                f"models.patch.size_px is {size}"
            )

    def __getitem__(self, index: int) -> tuple[Any, Any]:
        import torch

        ref = self.refs[index]
        with np.load(ref.path, allow_pickle=True) as data:
            x = np.asarray(data["x"], dtype=np.float32)
            y = np.asarray(data["y"])
            channels = [str(c) for c in data["channels"]]
        if self.verify_channels:
            self._check(ref.path, channels, x)
        if self.statistics is not None and self.settings.normalisation != "none":
            x = self.statistics.apply(x)
        return torch.from_numpy(x), torch.from_numpy(y.astype(np.int64))

    # -- reporting ---------------------------------------------------------- #

    def class_pixel_counts(self) -> dict[str, int]:
        """Labelled pixels per class across the partition.

        Reported because Section 7.5's metrics cannot be read without it: a
        per-class IoU of 0.0 means something different for a class with a
        million pixels than for one with none.
        """
        counts = np.zeros(self.settings.num_classes + 1, dtype=np.int64)
        ignored = 0
        for ref in self.refs:
            with np.load(ref.path, allow_pickle=True) as data:
                y = np.asarray(data["y"])
            ignored += int(np.count_nonzero(y == self.settings.ignore_index))
            for class_id in range(self.settings.num_classes):
                counts[class_id] += int(np.count_nonzero(y == class_id))
        out = {
            name: int(counts[i])
            for i, name in enumerate(self.settings.classes)
        }
        out["ignored"] = int(ignored)
        return out


def labelled_fraction(y: np.ndarray, ignore_index: int) -> float:
    """Share of a patch that carries a usable label."""
    y = np.asarray(y)
    if y.size == 0:
        return 0.0
    return float(np.count_nonzero(y != ignore_index) / y.size)


def keep_patch(y: np.ndarray, cfg: "Config") -> bool:
    """Whether a patch clears ``patch.min_labelled_fraction``."""
    return labelled_fraction(y, cfg.models.ignore_index) >= (
        cfg.models.patch.min_labelled_fraction
    )
