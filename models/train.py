"""Training for Phase 6, runnable locally or on Colab.

Brief, Section 3: training happens on Colab, and **model logic must never live
only in the notebook**. ``notebooks/colab_train.ipynb`` mounts Drive, clones
the repository and calls :func:`run` here; everything that decides what the
model learns is in this file and in config.

Brief, Section 7.5: the plain-U-Net versus Attention-U-Net comparison is a
required result, so :func:`compare_models` trains both under one call and
reports them side by side through :mod:`models.evaluate`.

Three choices worth stating, because each one is a place where a training
script can quietly produce a flattering number.

**Early stopping never follows accuracy.** ``models.training.monitor_metric``
offers macro IoU, water IoU or validation loss. Overall accuracy is not an
option: on this class distribution a model that never predicts terrain shadow
can score above 0.9, and Section 7.5 explicitly forbids relying on it. The
same metric drives checkpoint selection, so the saved weights are the ones
that were best by the stated measure rather than the last epoch's.

**The test split is not touched during training.** It is evaluated once, by
:func:`evaluate_split`, after the run. A test set consulted for early
stopping is a validation set with an optimistic name.

**Class imbalance is reported, not hidden.** ``class_weights`` defaults to
null, and the run records the per-class pixel counts it trained on, so a
per-class IoU of zero can be read against the support behind it.
"""

from __future__ import annotations

import json
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import TYPE_CHECKING, Any, Sequence

import numpy as np

from models.dataset import (
    PatchDataset,
    PatchRef,
    assign_splits,
    discover_patches,
    split_summary,
)
from models.evaluate import IGNORE_INDEX, Evaluation, compare, evaluate
from utils.logging import get_logger

if TYPE_CHECKING:  # pragma: no cover
    import torch

    from config.schema import Config

log = get_logger(__name__)

#: Model names accepted by :func:`build_model`.
MODEL_ATTENTION = "attention_unet"
MODEL_PLAIN = "plain_unet"
MODEL_BASELINE = "smp_unet"
MODELS = (MODEL_ATTENTION, MODEL_PLAIN, MODEL_BASELINE)


class TrainingError(RuntimeError):
    """A training run that cannot proceed as configured."""


@dataclass
class EpochRecord:
    """One epoch's numbers, kept so the curve can be inspected afterwards."""

    epoch: int
    train_loss: float
    val_loss: float
    monitored: float | None
    seconds: float

    def as_dict(self) -> dict[str, Any]:
        return {
            "epoch": self.epoch,
            "train_loss": round(self.train_loss, 6),
            "val_loss": round(self.val_loss, 6),
            "monitored": None if self.monitored is None else round(self.monitored, 6),
            "seconds": round(self.seconds, 1),
        }


@dataclass
class TrainingRun:
    """Everything one trained model produced."""

    model_name: str
    epochs_run: int
    best_epoch: int
    best_monitored: float | None
    monitor_metric: str
    history: list[EpochRecord] = field(default_factory=list)
    checkpoint: Path | None = None
    parameters: int = 0
    class_pixels: dict[str, int] = field(default_factory=dict)
    stopped_early: bool = False

    def as_dict(self) -> dict[str, Any]:
        return {
            "model": self.model_name,
            "epochs_run": self.epochs_run,
            "best_epoch": self.best_epoch,
            "best_monitored": self.best_monitored,
            "monitor_metric": self.monitor_metric,
            "stopped_early": self.stopped_early,
            "parameters": self.parameters,
            "class_pixels_trained_on": self.class_pixels,
            "checkpoint": None if self.checkpoint is None else str(self.checkpoint),
            "history": [r.as_dict() for r in self.history],
        }


# --------------------------------------------------------------------------- #
# Model construction
# --------------------------------------------------------------------------- #


def build_model(cfg: "Config", name: str) -> "torch.nn.Module":
    """One of the three models, sized from the configured stack.

    Raises:
        TrainingError: on an unknown name, listing the valid ones.
    """
    if name not in MODELS:
        raise TrainingError(
            f"unknown model {name!r}; choose from {', '.join(MODELS)}"
        )
    channels, classes = cfg.models.in_channels, cfg.models.num_classes

    if name == MODEL_BASELINE:
        from models.unet import baseline_unet

        return baseline_unet(cfg)

    from models.attention_unet import AttentionUNet, plain_unet

    if name == MODEL_PLAIN:
        return plain_unet(in_channels=channels, num_classes=classes)
    return AttentionUNet(in_channels=channels, num_classes=classes)


def _loss_fn(
    cfg: "Config", device: "torch.device | None" = None
) -> "torch.nn.Module":
    """The loss, with any class weights built on the training device.

    ``device`` is not optional in practice. A weight tensor left on the CPU
    while the model and batches are on CUDA raises mid-epoch with "Expected
    all tensors to be on the same device", which is a confusing way to
    discover a one-line omission -- and it only happens when class_weights is
    set, so an unweighted run passes and a weighted one fails.
    """
    import torch
    import torch.nn as nn

    weights = cfg.models.training.class_weights
    if weights is not None:
        if len(weights) != cfg.models.num_classes:
            raise TrainingError(
                f"class_weights has {len(weights)} entries but there are "
                f"{cfg.models.num_classes} classes"
            )
        tensor = torch.tensor(weights, dtype=torch.float32, device=device)
        log.info("loss is class-weighted: %s", weights)
    else:
        tensor = None
        log.info(
            "loss is UNWEIGHTED; rare classes (terrain shadow, snow) can be "
            "ignored by the model while the loss still falls -- read the "
            "per-class metrics, not the loss"
        )
    return nn.CrossEntropyLoss(weight=tensor, ignore_index=cfg.models.ignore_index)


def _device(prefer: str | None = None) -> "torch.device":
    import torch

    if prefer:
        return torch.device(prefer)
    return torch.device("cuda" if torch.cuda.is_available() else "cpu")


# --------------------------------------------------------------------------- #
# Evaluation
# --------------------------------------------------------------------------- #


def predict_split(
    model: "torch.nn.Module",
    dataset: PatchDataset,
    cfg: "Config",
    *,
    device: "torch.device | None" = None,
    batch_size: int | None = None,
) -> tuple[np.ndarray, np.ndarray]:
    """Reference and predicted labels over a whole partition, flattened.

    Returns:
        ``(reference, prediction)``, both 1-D, suitable for
        :func:`models.evaluate.evaluate`.
    """
    import torch
    from torch.utils.data import DataLoader

    if len(dataset) == 0:
        return np.empty(0, dtype=np.int64), np.empty(0, dtype=np.int64)

    device = device or _device()
    loader = DataLoader(
        dataset,
        batch_size=batch_size or cfg.models.training.batch_size,
        shuffle=False,
        num_workers=cfg.models.training.num_workers,
    )
    model.eval()
    refs: list[np.ndarray] = []
    preds: list[np.ndarray] = []
    with torch.no_grad():
        for x, y in loader:
            logits = model(x.to(device))
            pred = logits.argmax(dim=1).cpu().numpy()
            refs.append(y.numpy().reshape(-1))
            preds.append(pred.reshape(-1))
    return np.concatenate(refs), np.concatenate(preds)


def evaluate_split(
    model: "torch.nn.Module",
    dataset: PatchDataset,
    cfg: "Config",
    *,
    device: "torch.device | None" = None,
) -> Evaluation:
    """Section 7.5's metrics over a partition, water/shadow block included."""
    reference, prediction = predict_split(model, dataset, cfg, device=device)
    return evaluate(
        reference,
        prediction,
        class_ids=list(range(cfg.models.num_classes)),
        ignore_index=cfg.models.ignore_index,
    )


def _monitored_value(
    metric: str, evaluation: Evaluation, val_loss: float
) -> float | None:
    """The quantity early stopping follows. Higher is better except the loss."""
    if metric == "val_loss":
        return -val_loss
    if metric == "macro_iou":
        return evaluation.macro("iou")
    if metric == "water_iou":
        from models.evaluate import CLASS_WATER

        found = evaluation.metrics_for(CLASS_WATER)
        return None if found is None else found.iou
    raise TrainingError(f"unsupported monitor_metric {metric!r}")


# --------------------------------------------------------------------------- #
# Training
# --------------------------------------------------------------------------- #


def train(
    cfg: "Config",
    model_name: str,
    splits: dict[str, list[PatchRef]],
    *,
    out_dir: str | Path,
    device: str | None = None,
) -> TrainingRun:
    """Train one model, selecting the checkpoint by the configured metric."""
    import torch
    from torch.utils.data import DataLoader

    settings = cfg.models.training
    if not splits.get("train"):
        raise TrainingError("the train partition is empty; nothing to learn from")
    if not splits.get("val"):
        raise TrainingError(
            "the val partition is empty; early stopping and checkpoint "
            "selection would have nothing to follow"
        )

    torch.manual_seed(settings.seed)
    np.random.seed(settings.seed)

    out_dir = Path(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    dev = _device(device)

    train_set = PatchDataset(splits["train"], cfg)
    val_set = PatchDataset(splits["val"], cfg)
    class_pixels = train_set.class_pixel_counts()
    log.info("training on class pixels: %s", class_pixels)
    missing = [
        name for name, count in class_pixels.items()
        if name != "ignored" and count == 0
    ]
    if missing:
        log.warning(
            "class(es) %s have NO pixels in the training split: the model "
            "cannot learn them, and their IoU will be 0.0 for that reason "
            "rather than through any failure of the architecture",
            ", ".join(missing),
        )

    model = build_model(cfg, model_name).to(dev)
    criterion = _loss_fn(cfg, dev).to(dev)
    optimiser = torch.optim.Adam(
        model.parameters(),
        lr=settings.learning_rate,
        weight_decay=settings.weight_decay,
    )
    loader = DataLoader(
        train_set,
        batch_size=settings.batch_size,
        shuffle=True,
        num_workers=settings.num_workers,
        drop_last=False,
    )
    val_loader = DataLoader(
        val_set,
        batch_size=settings.batch_size,
        shuffle=False,
        num_workers=settings.num_workers,
    )

    checkpoint = out_dir / f"{model_name}.pt"
    history: list[EpochRecord] = []
    best: float | None = None
    best_epoch = 0
    since_improved = 0
    stopped_early = False

    for epoch in range(1, settings.epochs + 1):
        started = time.monotonic()
        model.train()
        total = 0.0
        batches = 0
        for x, y in loader:
            optimiser.zero_grad()
            loss = criterion(model(x.to(dev)), y.to(dev))
            loss.backward()
            optimiser.step()
            total += float(loss.item())
            batches += 1
        train_loss = total / max(batches, 1)

        model.eval()
        val_total = 0.0
        val_batches = 0
        with torch.no_grad():
            for x, y in val_loader:
                val_total += float(
                    criterion(model(x.to(dev)), y.to(dev)).item()
                )
                val_batches += 1
        val_loss = val_total / max(val_batches, 1)

        evaluation = evaluate_split(model, val_set, cfg, device=dev)
        monitored = _monitored_value(settings.monitor_metric, evaluation, val_loss)
        record = EpochRecord(
            epoch=epoch,
            train_loss=train_loss,
            val_loss=val_loss,
            monitored=monitored,
            seconds=time.monotonic() - started,
        )
        history.append(record)
        log.info(
            "epoch %d/%d: train %.4f, val %.4f, %s %s (%.0fs)",
            epoch, settings.epochs, train_loss, val_loss,
            settings.monitor_metric,
            "n/a" if monitored is None else f"{monitored:.4f}",
            record.seconds,
        )

        improved = monitored is not None and (best is None or monitored > best)
        if improved:
            best, best_epoch, since_improved = monitored, epoch, 0
            torch.save(
                {
                    "model_name": model_name,
                    "state_dict": model.state_dict(),
                    "epoch": epoch,
                    "monitor_metric": settings.monitor_metric,
                    "monitored": monitored,
                    "channels": list(cfg.models.channels),
                    "classes": list(cfg.models.classes),
                },
                checkpoint,
            )
        else:
            since_improved += 1
            if (
                settings.early_stopping_patience
                and since_improved >= settings.early_stopping_patience
            ):
                log.info(
                    "stopping early: %d epoch(s) without improvement in %s",
                    since_improved, settings.monitor_metric,
                )
                stopped_early = True
                break

    from models.unet import parameter_count

    return TrainingRun(
        model_name=model_name,
        epochs_run=len(history),
        best_epoch=best_epoch,
        best_monitored=best,
        monitor_metric=settings.monitor_metric,
        history=history,
        checkpoint=checkpoint if checkpoint.is_file() else None,
        parameters=parameter_count(model),
        class_pixels=class_pixels,
        stopped_early=stopped_early,
    )


def compare_models(
    cfg: "Config",
    patch_dir: str | Path,
    *,
    out_dir: str | Path,
    model_names: Sequence[str] = (MODEL_PLAIN, MODEL_ATTENTION),
    device: str | None = None,
) -> dict[str, Any]:
    """Train each model and report them side by side on the test split.

    Section 7.5's required result. The default pair is the **controlled**
    ablation: ``plain_unet`` is the Attention U-Net with the gates removed, so
    a difference between them is attributable to the gates. Add
    ``smp_unet`` to also place the pair against the brief's external baseline.

    The test split is evaluated here, once, and was not consulted during
    training.
    """
    import torch

    out_dir = Path(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)

    splits = assign_splits(discover_patches(patch_dir), cfg)
    if not splits.get("test"):
        raise TrainingError(
            "the test partition is empty, so no reportable result exists. "
            "Widen models.split.block_km or add labelled ground"
        )

    runs: dict[str, TrainingRun] = {}
    evaluations: dict[str, Evaluation] = {}
    for name in model_names:
        log.info("=== training %s ===", name)
        run = train(cfg, name, splits, out_dir=out_dir, device=device)
        runs[name] = run

        model = build_model(cfg, name)
        if run.checkpoint is not None:
            model.load_state_dict(
                torch.load(run.checkpoint, map_location="cpu")["state_dict"]
            )
        model.to(_device(device))
        evaluations[name] = evaluate_split(
            model, PatchDataset(splits["test"], cfg), cfg, device=_device(device)
        )
        log.info("%s on the test split:\n%s", name, evaluations[name].report())

    report = {
        "config_hash": cfg.config_hash() if hasattr(cfg, "config_hash") else None,
        "channels": list(cfg.models.channels),
        "classes": list(cfg.models.classes),
        "split": split_summary(splits),
        "split_strategy": cfg.models.split.strategy,
        "runs": {name: run.as_dict() for name, run in runs.items()},
        "test_evaluations": {
            name: ev.as_dict() for name, ev in evaluations.items()
        },
        "comparison_iou": compare(evaluations, metric="iou"),
        "comparison_f1": compare(evaluations, metric="f1"),
        "water_vs_shadow": {
            name: (
                None if ev.water_shadow is None else ev.water_shadow.as_dict()
            )
            for name, ev in evaluations.items()
        },
        "note": (
            "Overall accuracy is deliberately absent: Section 7.5 forbids "
            "relying on it, and a model that never predicts terrain shadow "
            "scores well on it."
        ),
    }
    path = out_dir / "comparison.json"
    path.write_text(json.dumps(report, indent=2, default=str), encoding="utf-8")
    log.info("wrote %s", path)
    return report


def run(
    config_path: str | Path | None = None,
    patch_dir: str | Path | None = None,
    out_dir: str | Path | None = None,
    *,
    model_names: Sequence[str] = (MODEL_PLAIN, MODEL_ATTENTION),
    device: str | None = None,
) -> dict[str, Any]:
    """Entry point for the Colab notebook and the command line.

    Keeps the notebook to a few lines, as Section 3 requires: nothing here
    decides anything the notebook could not show the reader in config.
    """
    from config.loader import load_config

    cfg = load_config(config_path, load_env=False) if config_path else load_config(
        load_env=False
    )
    patches = Path(patch_dir) if patch_dir else Path(cfg.paths.training)
    output = Path(out_dir) if out_dir else Path(cfg.paths.outputs) / "phase6"
    return compare_models(
        cfg, patches, out_dir=output, model_names=model_names, device=device
    )


if __name__ == "__main__":  # pragma: no cover
    import argparse

    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--config", default=None)
    parser.add_argument("--patches", default=None)
    parser.add_argument("--out", default=None)
    parser.add_argument("--models", nargs="+", default=[MODEL_PLAIN, MODEL_ATTENTION])
    parser.add_argument("--device", default=None)
    args = parser.parse_args()
    run(
        args.config,
        args.patches,
        args.out,
        model_names=args.models,
        device=args.device,
    )
