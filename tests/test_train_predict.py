"""Phase 6 training and inference wiring.

These tests do not measure whether the models are any good -- that needs
labels and a GPU, and is the Phase 6 gate. They check the things that would
otherwise produce a confident, wrong answer:

* the test split is never consulted during training;
* early stopping and checkpoint selection never follow overall accuracy;
* a checkpoint cannot be applied to a channel stack it was not trained on;
* inference never classifies a pixel it had no observation for.

All arrays are synthetic.
"""

from __future__ import annotations

import numpy as np
import pytest

torch = pytest.importorskip("torch")

from config.schema import Config  # noqa: E402
from models.dataset import write_patch  # noqa: E402
from models.predict import (  # noqa: E402
    PredictionError,
    load_checkpoint,
    predict_stack,
)
from models.train import (  # noqa: E402
    MODEL_ATTENTION,
    MODEL_BASELINE,
    MODEL_PLAIN,
    MODELS,
    TrainingError,
    build_model,
    compare_models,
)

pytestmark = pytest.mark.synthetic


def tiny(cfg: Config, **training) -> Config:
    """A config small enough to train in a test."""
    data = cfg.model_dump(mode="python")
    data["models"]["patch"].update(size_px=32, stride_px=32)
    data["models"]["split"].update(buffer_px=0, block_km=2.0)
    data["models"]["training"].update(
        dict(epochs=1, batch_size=2, num_workers=0, early_stopping_patience=0,
             **training)
    )
    return Config.model_validate(data)


def patch_set(directory, cfg: Config, *, blocks=5, per_block=3):
    """Patches spread over several geographic blocks."""
    rng = np.random.default_rng(0)
    size = cfg.models.patch.size_px
    for b in range(blocks):
        for k in range(per_block):
            y = np.zeros((size, size), dtype=np.uint8)
            y[: size // 4] = 1
            y[size // 4 : size // 2] = 2
            y[size // 2 : size // 2 + 4] = 3
            write_patch(
                directory / f"b{b}_{k}.npz",
                rng.normal(size=(cfg.models.in_channels, size, size)).astype(
                    "float32"
                ),
                y,
                cfg.models.channels,
                x_m=float(b * 2000 + 500 + k * 100),
                y_m=500.0,
                crs="EPSG:32645",
            )
    return directory


class TestModelConstruction:
    def test_every_named_model_is_buildable_or_says_why(self, cfg: Config) -> None:
        from models.unet import BaselineUNetError

        for name in MODELS:
            try:
                model = build_model(cfg, name)
            except BaselineUNetError as exc:
                # The smp baseline is an optional dependency; absence must be
                # reported clearly rather than crashing on import.
                assert name == MODEL_BASELINE
                assert "segmentation_models_pytorch" in str(exc)
                continue
            assert isinstance(model, torch.nn.Module)

    def test_an_unknown_model_lists_the_valid_names(self, cfg: Config) -> None:
        with pytest.raises(TrainingError, match="attention_unet"):
            build_model(cfg, "not_a_model")

    def test_the_input_width_comes_from_the_channel_stack(self, cfg: Config) -> None:
        """The stack is the single source of truth for model width."""
        size = 32
        model = build_model(cfg, MODEL_PLAIN)
        x = torch.zeros(1, cfg.models.in_channels, size, size)
        out = model(x)
        assert out.shape == (1, cfg.models.num_classes, size, size)

    def test_a_narrower_stack_builds_a_narrower_model(self, cfg: Config) -> None:
        data = cfg.model_dump(mode="python")
        data["models"]["channels"] = ["S2_B3", "S2_B8", "S2_B11"]
        narrow = Config.model_validate(data)
        model = build_model(narrow, MODEL_PLAIN)
        assert model(torch.zeros(1, 3, 32, 32)).shape[1] == narrow.models.num_classes

    def test_attention_costs_parameters(self, cfg: Config) -> None:
        """The gates are the only difference between the two."""
        from models.unet import parameter_count

        plain = parameter_count(build_model(cfg, MODEL_PLAIN))
        gated = parameter_count(build_model(cfg, MODEL_ATTENTION))
        assert gated > plain


class TestTrainingWiring:
    def test_a_run_trains_both_models_and_writes_a_comparison(
        self, cfg: Config, tmp_path
    ) -> None:
        small = tiny(cfg)
        patch_set(tmp_path / "patches", small)
        report = compare_models(
            small, tmp_path / "patches", out_dir=tmp_path / "out",
            model_names=(MODEL_PLAIN, MODEL_ATTENTION), device="cpu",
        )
        assert set(report["runs"]) == {MODEL_PLAIN, MODEL_ATTENTION}
        assert (tmp_path / "out" / "comparison.json").is_file()
        assert report["comparison_iou"]["models"]

    def test_the_water_shadow_confusion_is_reported_for_each_model(
        self, cfg: Config, tmp_path
    ) -> None:
        """Section 7.5 requires it explicitly, so it must never be absent."""
        small = tiny(cfg)
        patch_set(tmp_path / "patches", small)
        report = compare_models(
            small, tmp_path / "patches", out_dir=tmp_path / "out",
            model_names=(MODEL_PLAIN,), device="cpu",
        )
        assert report["water_vs_shadow"][MODEL_PLAIN] is not None

    def test_no_accuracy_is_reported_as_a_metric(
        self, cfg: Config, tmp_path
    ) -> None:
        """Only as a note explaining its absence."""
        small = tiny(cfg)
        patch_set(tmp_path / "patches", small)
        report = compare_models(
            small, tmp_path / "patches", out_dir=tmp_path / "out",
            model_names=(MODEL_PLAIN,), device="cpu",
        )
        evaluation = report["test_evaluations"][MODEL_PLAIN]
        assert "accuracy" not in evaluation
        for row in evaluation.get("per_class", []):
            assert "accuracy" not in row

    def test_accuracy_is_not_a_selectable_monitor_metric(self, cfg: Config) -> None:
        data = cfg.model_dump(mode="python")
        data["models"]["training"]["monitor_metric"] = "accuracy"
        with pytest.raises(Exception):
            Config.model_validate(data)

    def test_the_split_is_recorded_with_the_result(
        self, cfg: Config, tmp_path
    ) -> None:
        """A result without its split cannot be judged for leakage."""
        small = tiny(cfg)
        patch_set(tmp_path / "patches", small)
        report = compare_models(
            small, tmp_path / "patches", out_dir=tmp_path / "out",
            model_names=(MODEL_PLAIN,), device="cpu",
        )
        assert report["split_strategy"] == small.models.split.strategy
        assert report["split"]["test"]["patches"] > 0
        assert report["channels"] == list(small.models.channels)

    def test_an_empty_test_split_is_refused(self, cfg: Config, tmp_path) -> None:
        """A run with nothing to report on must fail, not report nothing."""
        small = tiny(cfg)
        patch_set(tmp_path / "patches", small, blocks=1, per_block=2)
        with pytest.raises(TrainingError, match="test partition is empty"):
            compare_models(
                small, tmp_path / "patches", out_dir=tmp_path / "out",
                model_names=(MODEL_PLAIN,), device="cpu",
            )

    def test_mismatched_class_weights_are_refused(
        self, cfg: Config, tmp_path
    ) -> None:
        small = tiny(cfg, class_weights=[1.0, 2.0])
        patch_set(tmp_path / "patches", small)
        with pytest.raises(TrainingError, match="class_weights"):
            compare_models(
                small, tmp_path / "patches", out_dir=tmp_path / "out",
                model_names=(MODEL_PLAIN,), device="cpu",
            )


class TestCheckpointGuards:
    def _trained(self, cfg: Config, tmp_path):
        small = tiny(cfg)
        patch_set(tmp_path / "patches", small)
        report = compare_models(
            small, tmp_path / "patches", out_dir=tmp_path / "out",
            model_names=(MODEL_PLAIN,), device="cpu",
        )
        return small, report["runs"][MODEL_PLAIN]["checkpoint"]

    def test_a_checkpoint_reloads(self, cfg: Config, tmp_path) -> None:
        small, path = self._trained(cfg, tmp_path)
        model, payload = load_checkpoint(path, small, device="cpu")
        assert payload["model_name"] == MODEL_PLAIN
        assert payload["channels"] == list(small.models.channels)

    def test_a_checkpoint_is_refused_against_a_different_stack(
        self, cfg: Config, tmp_path
    ) -> None:
        """The guard that matters: same width, different order, wrong answer."""
        small, path = self._trained(cfg, tmp_path)
        data = small.model_dump(mode="python")
        swapped = list(small.models.channels)
        swapped[0], swapped[1] = swapped[1], swapped[0]
        data["models"]["channels"] = swapped
        with pytest.raises(PredictionError, match="trained on channels"):
            load_checkpoint(path, Config.model_validate(data), device="cpu")

    def test_a_missing_checkpoint_says_so(self, cfg: Config, tmp_path) -> None:
        with pytest.raises(PredictionError, match="checkpoint not found"):
            load_checkpoint(tmp_path / "nope.pt", cfg, device="cpu")


class TestInferenceNeverInventsObservations:
    def test_nodata_is_ignore_index_not_a_class(self, cfg: Config) -> None:
        """A model will happily call an all-zero patch water at high confidence.

        That is how the Phase 4 fusion came to report water over scene edges
        (docs/methods.md 10.13.2), so inference must not repeat it.
        """
        small = tiny(cfg)
        model = build_model(small, MODEL_PLAIN)
        rng = np.random.default_rng(0)
        stack = rng.normal(size=(small.models.in_channels, 70, 80)).astype(
            "float32"
        )
        stack[:, :20, :] = 0.0

        result = predict_stack(model, stack, small, tile_px=32, overlap_px=8,
                               device="cpu")
        assert (result.classes[:20, :] == small.models.ignore_index).all()
        assert (result.classes[20:, :] != small.models.ignore_index).all()
        assert result.unseen_pixels == 20 * 80

    def test_probabilities_are_nan_where_nothing_was_seen(
        self, cfg: Config
    ) -> None:
        small = tiny(cfg)
        model = build_model(small, MODEL_PLAIN)
        stack = np.ones((small.models.in_channels, 40, 40), dtype="float32")
        stack[:, :8, :] = 0.0
        result = predict_stack(model, stack, small, tile_px=32, overlap_px=8,
                               device="cpu")
        assert np.isnan(result.probabilities[:, :8, :]).all()
        assert not np.isnan(result.probabilities[:, 8:, :]).any()

    def test_probabilities_sum_to_one_where_classified(self, cfg: Config) -> None:
        small = tiny(cfg)
        model = build_model(small, MODEL_PLAIN)
        rng = np.random.default_rng(1)
        stack = rng.normal(size=(small.models.in_channels, 40, 48)).astype(
            "float32"
        )
        result = predict_stack(model, stack, small, tile_px=32, overlap_px=8,
                               device="cpu")
        totals = result.probabilities.sum(axis=0)
        np.testing.assert_allclose(totals, 1.0, atol=1e-4)

    def test_a_wrong_channel_count_is_refused(self, cfg: Config) -> None:
        small = tiny(cfg)
        model = build_model(small, MODEL_PLAIN)
        with pytest.raises(PredictionError, match="models.channels declares"):
            predict_stack(model, np.zeros((3, 40, 40), "float32"), small,
                          device="cpu")

    def test_every_pixel_is_covered_by_tiling(self, cfg: Config) -> None:
        """A raster not a multiple of the tile must still be fully classified."""
        small = tiny(cfg)
        model = build_model(small, MODEL_PLAIN)
        rng = np.random.default_rng(2)
        stack = rng.normal(size=(small.models.in_channels, 77, 93)).astype(
            "float32"
        )
        result = predict_stack(model, stack, small, tile_px=32, overlap_px=8,
                               device="cpu")
        assert result.classes.shape == (77, 93)
        assert (result.classes != small.models.ignore_index).all()


# --------------------------------------------------------------------------- #
# Class weights must live on the training device
# --------------------------------------------------------------------------- #
class TestLossIsOnTheTrainingDevice:
    """A CPU weight tensor against CUDA batches fails mid-epoch.

    This escaped every earlier test because it needs TWO conditions at once:
    `class_weights` set, and a non-CPU device. The default config has
    `class_weights: null`, and the tests run on CPU, so neither alone trips
    it. It surfaced on the first real GPU run, from the Landslide4Sense
    overlay, as "Expected all tensors to be on the same device" after the
    download, conversion and split had all succeeded.

    These tests need no GPU: they assert the weight tensor lands on whatever
    device was asked for, which is the property that was missing.
    """

    def _weighted(self, cfg: Config) -> Config:
        data = cfg.model_dump(mode="python")
        data["models"]["training"]["class_weights"] = [
            1.0, 1.0, 5.0, 1.0, 1.0
        ]
        return Config.model_validate(data)

    def test_the_weight_tensor_follows_the_requested_device(
        self, cfg: Config
    ) -> None:
        from models.train import _loss_fn

        device = torch.device("cpu")
        criterion = _loss_fn(self._weighted(cfg), device)
        assert criterion.weight is not None
        assert criterion.weight.device == device

    def test_an_unweighted_loss_carries_no_tensor(self, cfg: Config) -> None:
        """Nothing to misplace, which is why the bug hid for so long."""
        from models.train import _loss_fn

        criterion = _loss_fn(cfg, torch.device("cpu"))
        assert criterion.weight is None

    def test_a_weighted_run_trains(self, cfg: Config, tmp_path) -> None:
        """End to end with weights set, which is the Route A configuration."""
        small = tiny(self._weighted(cfg))
        patch_set(tmp_path / "patches", small)
        report = compare_models(
            small, tmp_path / "patches", out_dir=tmp_path / "out",
            model_names=(MODEL_PLAIN,), device="cpu",
        )
        assert report["runs"][MODEL_PLAIN]["epochs_run"] >= 1

    @pytest.mark.skipif(
        not torch.cuda.is_available(), reason="no CUDA device available here"
    )
    def test_a_weighted_run_trains_on_cuda(self, cfg: Config, tmp_path) -> None:
        """The exact combination that failed. Skipped without a GPU."""
        small = tiny(self._weighted(cfg))
        patch_set(tmp_path / "patches", small)
        compare_models(
            small, tmp_path / "patches", out_dir=tmp_path / "out",
            model_names=(MODEL_PLAIN,), device="cuda",
        )
