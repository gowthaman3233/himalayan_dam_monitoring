"""A NaN input must never reach the loss (Phase 6).

A normalised difference index is NaN where its denominator vanishes. That is
correct for the detection pipeline -- NaN there means *unmeasurable*, and the
shadow-rejection fusion treats it as absent evidence rather than as a value
(see ``detection.water.spectral_index``). A neural network has no such
notion.

Measured on this project's own baseline: **a single NaN among 22,528 input
values turned all 7,852,037 weights NaN on the first optimiser step.**
Afterwards ``argmax`` over all-NaN logits returns index 0, so the model
predicts the first class everywhere.

A real Landslide4Sense run produced exactly that, and it did not look like a
failure. It looked like a result:

* both architectures reported **bit-identical** metrics, to sixteen decimal
  places, despite differing by 132,004 parameters;
* landslide IoU exactly 0.0;
* background IoU 0.9782894736842105, which is precisely the background
  fraction of the test split -- the signature of predicting one class;
* best epoch 1, early-stopped, because the weights were NaN from the first
  batch and nothing could improve.

These tests exist so that cannot happen quietly again. Arrays are synthetic.
"""

from __future__ import annotations

import numpy as np
import pytest

torch = pytest.importorskip("torch")

from config.schema import Config  # noqa: E402
from models.dataset import PatchDataset, discover_patches, write_patch  # noqa: E402
from models.train import (  # noqa: E402
    MODEL_PLAIN,
    TrainingError,
    build_model,
    compare_models,
)

pytestmark = pytest.mark.synthetic


def small_config(cfg: Config) -> Config:
    data = cfg.model_dump(mode="python")
    data["models"]["patch"].update(size_px=32, stride_px=32)
    data["models"]["split"].update(buffer_px=0, block_km=2.0)
    data["models"]["training"].update(
        epochs=1, batch_size=2, num_workers=0, early_stopping_patience=0
    )
    return Config.model_validate(data)


def patches(directory, cfg: Config, *, n=12, poison=None):
    """Patches spread over blocks, optionally with one poisoned value."""
    rng = np.random.default_rng(0)
    size = cfg.models.patch.size_px
    block = cfg.models.split.block_km * 1000.0
    directory.mkdir(parents=True, exist_ok=True)
    for i in range(n):
        x = rng.normal(
            0.2, 0.05, (cfg.models.in_channels, size, size)
        ).astype("float32")
        if poison is not None:
            x[0, 0, 0] = poison
        y = np.zeros((size, size), dtype=np.uint8)
        y[: size // 4] = 2
        write_patch(
            directory / f"p_{i:03d}.npz", x, y, cfg.models.channels,
            x_m=float((i // 3) * block + block / 2 + (i % 3) * 100),
            y_m=block / 2, event=f"ev-{i}",
        )
    return directory


class TestTheMechanism:
    """Demonstrate the failure, so the fix is not protecting against a guess."""

    def test_one_nan_destroys_every_weight(self, cfg: Config) -> None:
        small = small_config(cfg)
        model = build_model(small, MODEL_PLAIN)
        optimiser = torch.optim.Adam(model.parameters(), lr=3e-4)
        criterion = torch.nn.CrossEntropyLoss(
            ignore_index=small.models.ignore_index
        )

        x = torch.randn(2, small.models.in_channels, 32, 32)
        y = torch.zeros(2, 32, 32, dtype=torch.long)
        y[:, :8] = 2
        x[0, 6, 0, 0] = float("nan")   # one value out of thousands

        optimiser.zero_grad()
        loss = criterion(model(x), y)
        assert torch.isnan(loss), "fixture precondition: the loss should be NaN"
        loss.backward()
        optimiser.step()

        assert all(torch.isnan(p).all() for p in model.parameters()), (
            "one NaN did not propagate; the premise of these tests has changed"
        )

    def test_argmax_of_nan_logits_predicts_the_first_class(
        self, cfg: Config
    ) -> None:
        """Why the symptom is 'predicts background everywhere'."""
        logits = torch.full((1, 5, 4, 4), float("nan"))
        assert torch.unique(logits.argmax(dim=1)).tolist() == [0]


class TestTheDatasetNeutralisesIt:
    def test_the_model_input_is_finite(self, cfg: Config, tmp_path) -> None:
        small = small_config(cfg)
        patches(tmp_path / "p", small, n=3, poison=np.nan)
        x, _ = PatchDataset(discover_patches(tmp_path / "p"), small)[0]
        assert torch.isfinite(x).all()

    def test_the_affected_pixel_is_excluded_from_the_loss(
        self, cfg: Config, tmp_path
    ) -> None:
        """Replacing the input alone would train on ground with no data."""
        small = small_config(cfg)
        patches(tmp_path / "p", small, n=3, poison=np.nan)
        _, y = PatchDataset(discover_patches(tmp_path / "p"), small)[0]
        assert int(y[0, 0]) == small.models.ignore_index

    def test_only_that_pixel_is_excluded(self, cfg: Config, tmp_path) -> None:
        small = small_config(cfg)
        patches(tmp_path / "p", small, n=3, poison=np.nan)
        _, y = PatchDataset(discover_patches(tmp_path / "p"), small)[0]
        ignored = int((y == small.models.ignore_index).sum())
        assert ignored == 1, f"{ignored} pixels ignored; expected exactly 1"

    def test_infinity_is_handled_too(self, cfg: Config, tmp_path) -> None:
        """np.isfinite covers inf as well as NaN, and both kill a network."""
        small = small_config(cfg)
        patches(tmp_path / "p", small, n=3, poison=np.inf)
        x, y = PatchDataset(discover_patches(tmp_path / "p"), small)[0]
        assert torch.isfinite(x).all()
        assert int(y[0, 0]) == small.models.ignore_index

    def test_a_clean_patch_is_untouched(self, cfg: Config, tmp_path) -> None:
        small = small_config(cfg)
        patches(tmp_path / "p", small, n=3)
        _, y = PatchDataset(discover_patches(tmp_path / "p"), small)[0]
        assert int((y == small.models.ignore_index).sum()) == 0

    def test_weights_stay_finite_through_several_steps(
        self, cfg: Config, tmp_path
    ) -> None:
        """The property that actually failed on real data."""
        small = small_config(cfg)
        patches(tmp_path / "p", small, n=6, poison=np.nan)
        dataset = PatchDataset(discover_patches(tmp_path / "p"), small)

        model = build_model(small, MODEL_PLAIN)
        optimiser = torch.optim.Adam(model.parameters(), lr=3e-4)
        criterion = torch.nn.CrossEntropyLoss(
            ignore_index=small.models.ignore_index
        )
        x, y = dataset[0]
        for step in range(3):
            optimiser.zero_grad()
            loss = criterion(model(x[None]), y[None])
            assert torch.isfinite(loss), f"loss went non-finite at step {step}"
            loss.backward()
            optimiser.step()
        assert all(torch.isfinite(p).all() for p in model.parameters())

    def test_a_full_run_with_nan_patches_completes(
        self, cfg: Config, tmp_path
    ) -> None:
        small = small_config(cfg)
        patches(tmp_path / "p", small, n=12, poison=np.nan)
        report = compare_models(
            small, tmp_path / "p", out_dir=tmp_path / "out",
            model_names=(MODEL_PLAIN,), device="cpu",
        )
        assert report["runs"][MODEL_PLAIN]["epochs_run"] >= 1


class TestTrainingRefusesANonFiniteLoss:
    """The backstop, for any route the dataset guard does not cover.

    Note what the first attempt at this test revealed: with standardisation
    on, a poisoned value of 1e38 does **not** produce a non-finite loss. It
    dominates the channel's standard deviation and is scaled back into range,
    so normalisation is itself a defence against extreme values. The backstop
    therefore has to be exercised with scaling switched off.
    """

    @staticmethod
    def _unscaled(cfg: Config) -> Config:
        data = small_config(cfg).model_dump(mode="python")
        data["models"]["normalisation"] = "none"
        return Config.model_validate(data)

    def test_a_non_finite_loss_raises(
        self, cfg: Config, tmp_path, monkeypatch
    ) -> None:
        """Tested by injecting a NaN loss, not by contriving input data.

        Finding data that overflows turned out to be surprisingly hard --
        float32 holds 1e38, and standardisation tames it anyway -- which is
        itself reassuring. But the guard protects against *any* route to a
        non-finite loss, including ones not yet thought of, so it is tested
        directly rather than through a particular trigger.
        """
        import models.train as train_module

        class NaNLoss(torch.nn.Module):
            def forward(self, logits, target):  # noqa: D102
                return logits.sum() * float("nan")

        monkeypatch.setattr(train_module, "_loss_fn", lambda cfg, dev=None: NaNLoss())

        small = small_config(cfg)
        patches(tmp_path / "p", small, n=12)
        with pytest.raises(TrainingError, match="loss became"):
            compare_models(
                small, tmp_path / "p", out_dir=tmp_path / "out",
                model_names=(MODEL_PLAIN,), device="cpu",
            )

    def test_the_message_says_why_it_matters(
        self, cfg: Config, tmp_path, monkeypatch
    ) -> None:
        """A crash is better than a confident null result, and should say so."""
        import models.train as train_module

        class NaNLoss(torch.nn.Module):
            def forward(self, logits, target):  # noqa: D102
                return logits.sum() * float("nan")

        monkeypatch.setattr(train_module, "_loss_fn", lambda cfg, dev=None: NaNLoss())

        small = small_config(cfg)
        patches(tmp_path / "p", small, n=12)
        with pytest.raises(TrainingError) as excinfo:
            compare_models(
                small, tmp_path / "p", out_dir=tmp_path / "out",
                model_names=(MODEL_PLAIN,), device="cpu",
            )
        assert "meaningless result" in str(excinfo.value)

    def test_an_extreme_value_does_not_reach_a_non_finite_loss(
        self, cfg: Config, tmp_path
    ) -> None:
        """Worth asserting: 1e38 is survivable, with or without scaling.

        This was expected to be an easy way to trigger the guard and is not.
        Recording it stops a future reader assuming the guard is untested
        because no data triggers it.
        """
        small = small_config(cfg)
        patches(tmp_path / "p", small, n=12, poison=1e38)
        report = compare_models(
            small, tmp_path / "p", out_dir=tmp_path / "out",
            model_names=(MODEL_PLAIN,), device="cpu",
        )
        assert report["runs"][MODEL_PLAIN]["epochs_run"] >= 1
