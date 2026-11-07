"""Inference: apply a trained model to a co-registered stack (Phase 6).

Takes the stack Phase 2 produces and writes a classified raster plus per-class
probabilities, so Phase 4's fusion and the dashboard can consume model output
the same way they consume the rule-based masks.

Two things this module refuses to do.

**It will not run a model against a stack it was not trained on.** The
checkpoint records the channel names it was trained with, and
:func:`load_checkpoint` compares them to the stack's. A model fed the right
number of channels in the wrong order produces a plausible-looking raster that
is wrong everywhere, and nothing downstream could detect it.

**It will not classify pixels it cannot see.** Where the stack is nodata the
output is ``ignore_index``, not a class. A segmentation model will happily
return "water" with high confidence for an all-zero patch -- which is exactly
how the Phase 4 fusion came to report water over scene edges
(docs/methods.md 10.13.2).

Tiling: large rasters are processed in overlapping tiles and only each tile's
interior is kept, because a convolutional network has less context at a tile
edge and the seams are otherwise visible as straight lines in the output.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import TYPE_CHECKING, Any, Sequence

import numpy as np

from utils.logging import get_logger

if TYPE_CHECKING:  # pragma: no cover
    import torch

    from config.schema import Config

log = get_logger(__name__)


class PredictionError(RuntimeError):
    """Inference that cannot be performed safely."""


@dataclass(frozen=True)
class Prediction:
    """A classified raster and its per-class probabilities."""

    classes: np.ndarray
    probabilities: np.ndarray
    class_names: list[str]
    ignore_index: int
    unseen_pixels: int

    def fraction(self, class_id: int) -> float:
        """Share of *classified* pixels given to one class."""
        valid = int(np.count_nonzero(self.classes != self.ignore_index))
        if not valid:
            return 0.0
        return float(np.count_nonzero(self.classes == class_id) / valid)

    def summary(self) -> dict[str, Any]:
        return {
            "class_fractions": {
                name: round(self.fraction(i), 5)
                for i, name in enumerate(self.class_names)
            },
            "unseen_pixels": self.unseen_pixels,
            "classified_pixels": int(
                np.count_nonzero(self.classes != self.ignore_index)
            ),
        }


def load_checkpoint(
    path: str | Path, cfg: "Config", *, device: str | None = None
) -> tuple["torch.nn.Module", dict[str, Any]]:
    """Rebuild a trained model and verify it matches the configured stack.

    Raises:
        PredictionError: if the checkpoint's channel list differs from
            ``models.channels``, in order or in content.
    """
    import torch

    from models.train import build_model

    path = Path(path)
    if not path.is_file():
        raise PredictionError(f"checkpoint not found: {path}")

    payload = torch.load(path, map_location="cpu")
    trained_channels = [str(c) for c in payload.get("channels", [])]
    configured = list(cfg.models.channels)
    if trained_channels and trained_channels != configured:
        raise PredictionError(
            f"{path.name} was trained on channels {trained_channels} but "
            f"models.channels is {configured}. Running it anyway would feed "
            "the model a different band in each slot and produce a raster "
            "that is wrong everywhere without looking wrong."
        )

    # Inference must scale its input exactly as training did. A checkpoint
    # trained on standardised patches applied to raw ones sees a completely
    # different distribution and returns confident nonsense, with nothing in
    # the output to show it.
    if payload.get("normalisation", "none") != "none" and not payload.get(
        "statistics"
    ):
        raise PredictionError(
            f"{path.name} was trained with normalisation "
            f"{payload.get('normalisation')!r} but carries no channel "
            f"statistics, so its input scaling cannot be reproduced. Retrain "
            f"with a current version rather than running it unscaled."
        )

    model = build_model(cfg, payload["model_name"])
    model.load_state_dict(payload["state_dict"])
    model.to(torch.device(device) if device else torch.device("cpu"))
    model.eval()
    log.info(
        "loaded %s from epoch %s (%s %.4f)",
        payload["model_name"],
        payload.get("epoch", "?"),
        payload.get("monitor_metric", "?"),
        payload.get("monitored", float("nan")),
    )
    return model, payload


def predict_stack(
    model: "torch.nn.Module",
    stack: np.ndarray,
    cfg: "Config",
    *,
    unseen: np.ndarray | None = None,
    tile_px: int | None = None,
    overlap_px: int | None = None,
    device: str | None = None,
    statistics: Any | None = None,
) -> Prediction:
    """Classify a ``(channels, height, width)`` stack.

    Args:
        stack: channels in the order of ``models.channels``.
        unseen: where the stack holds no observation. Those pixels are
            returned as ``ignore_index`` rather than classified. If omitted,
            pixels whose every channel is exactly zero are treated as unseen,
            which is the nodata convention of this project's own exports.
        tile_px: tile edge, defaulting to the training patch size.
        overlap_px: context discarded at each tile edge, defaulting to a
            quarter of the tile.
        statistics: the :class:`~models.dataset.ChannelStatistics` the model
            was trained with, from its checkpoint. Omitting them while the
            config asks for normalisation feeds the model a distribution it
            never saw, so it is refused rather than guessed.

    Returns:
        A :class:`Prediction`.
    """
    import torch

    stack = np.asarray(stack, dtype=np.float32)
    if stack.ndim != 3:
        raise PredictionError(f"stack must be (channels, h, w), got {stack.shape}")
    expected = cfg.models.in_channels
    if stack.shape[0] != expected:
        raise PredictionError(
            f"stack has {stack.shape[0]} channel(s) but models.channels "
            f"declares {expected}: {list(cfg.models.channels)}"
        )

    _, height, width = stack.shape
    tile = int(tile_px or cfg.models.patch.size_px)
    halo = int(overlap_px if overlap_px is not None else max(1, tile // 4))
    step = max(1, tile - 2 * halo)
    classes_n = cfg.models.num_classes
    dev = torch.device(device) if device else torch.device("cpu")

    # Nodata is detected on the RAW stack, BEFORE any scaling.
    #
    # Standardising maps an all-zero pixel to -mean/sd, which is not zero, so
    # detecting nodata afterwards would find nothing and the scene edge would
    # be classified instead of marked unseen -- the exact failure recorded in
    # docs/validation.md 24, Finding 4a.
    if unseen is None:
        unseen = np.all(stack == 0.0, axis=0)
    else:
        unseen = np.asarray(unseen, dtype=bool)
        if unseen.shape != (height, width):
            raise PredictionError(
                f"unseen {unseen.shape} does not match the stack {(height, width)}"
            )

    if cfg.models.normalisation != "none":
        if statistics is None:
            raise PredictionError(
                f"models.normalisation is {cfg.models.normalisation!r} but no "
                f"channel statistics were supplied. Pass the ones from the "
                f"checkpoint (load_checkpoint returns them): a model trained "
                f"on standardised input and applied to raw input returns "
                f"confident nonsense, with nothing in the output to show it."
            )
        if list(statistics.channels) != list(cfg.models.channels):
            raise PredictionError(
                f"statistics describe {list(statistics.channels)} but the "
                f"configured stack is {list(cfg.models.channels)}"
            )
        stack = statistics.apply(stack)

    probabilities = np.zeros((classes_n, height, width), dtype=np.float32)

    with torch.no_grad():
        for row in range(0, height, step):
            for col in range(0, width, step):
                r1, c1 = min(row + tile, height), min(col + tile, width)
                r0, c0 = max(0, r1 - tile), max(0, c1 - tile)
                patch = stack[:, r0:r1, c0:c1]

                pad_r, pad_c = tile - patch.shape[1], tile - patch.shape[2]
                if pad_r or pad_c:
                    patch = np.pad(
                        patch, ((0, 0), (0, pad_r), (0, pad_c)), mode="reflect"
                    )

                logits = model(torch.from_numpy(patch[None]).to(dev))
                probs = (
                    torch.softmax(logits, dim=1)[0].cpu().numpy()[:, :tile, :tile]
                )
                probs = probs[:, : r1 - r0, : c1 - c0]

                # Keep only the interior, except at the raster's own edges,
                # where there is no neighbouring tile to supply context.
                ir0 = r0 + (halo if r0 > 0 else 0)
                ic0 = c0 + (halo if c0 > 0 else 0)
                ir1 = r1 - (halo if r1 < height else 0)
                ic1 = c1 - (halo if c1 < width else 0)
                if ir1 <= ir0 or ic1 <= ic0:
                    continue
                probabilities[:, ir0:ir1, ic0:ic1] = probs[
                    :, ir0 - r0 : ir1 - r0, ic0 - c0 : ic1 - c0
                ]

    classes = probabilities.argmax(axis=0).astype(np.uint8)
    classes[unseen] = cfg.models.ignore_index
    probabilities[:, unseen] = np.nan

    unseen_count = int(np.count_nonzero(unseen))
    if unseen_count:
        log.info(
            "%d pixel(s) (%.1f%%) had no observation and are %d, not a class",
            unseen_count,
            100 * unseen_count / unseen.size,
            cfg.models.ignore_index,
        )
    return Prediction(
        classes=classes,
        probabilities=probabilities,
        class_names=list(cfg.models.classes),
        ignore_index=cfg.models.ignore_index,
        unseen_pixels=unseen_count,
    )


def write_prediction(
    prediction: Prediction,
    path: str | Path,
    *,
    transform: Any,
    crs: Any,
    write_probabilities: bool = True,
) -> dict[str, Path]:
    """Write the classified raster, and optionally the probabilities.

    Returns:
        ``{"classes": path, "probabilities": path}`` for what was written.
    """
    import rasterio

    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    written: dict[str, Path] = {}

    profile = {
        "driver": "GTiff",
        "height": prediction.classes.shape[0],
        "width": prediction.classes.shape[1],
        "count": 1,
        "dtype": "uint8",
        "crs": crs,
        "transform": transform,
        "compress": "lzw",
        "nodata": prediction.ignore_index,
    }
    with rasterio.open(path, "w", **profile) as dst:
        dst.write(prediction.classes, 1)
        dst.set_band_description(1, "class")
        dst.update_tags(
            classes=json.dumps(
                {i: n for i, n in enumerate(prediction.class_names)}
            ),
            ignore_index=str(prediction.ignore_index),
            value_type="classified",
        )
    written["classes"] = path

    if write_probabilities:
        prob_path = path.with_name(f"{path.stem}_probabilities.tif")
        profile.update(
            count=len(prediction.class_names), dtype="float32", nodata=None
        )
        with rasterio.open(prob_path, "w", **profile) as dst:
            for i, name in enumerate(prediction.class_names):
                dst.write(prediction.probabilities[i], i + 1)
                dst.set_band_description(i + 1, name)
            dst.update_tags(value_type="classified")
        written["probabilities"] = prob_path

    log.info("wrote %s", ", ".join(str(p) for p in written.values()))
    return written
